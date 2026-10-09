# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "boto3>=1.34",
#   "typer>=0.12",
#   "loguru>=0.7",
#   "multiprocess>=0.70",
#   "p_tqdm>=1.4",
# ]
# ///
"""Upload local files to S3 in parallel, optionally writing a CSV of the results.

The inverse of ``dl_s3_csv.py``: that script reads ``s3://`` URIs out of a CSV
column and downloads them to a local directory; this one takes local files (a
directory, an explicit list, or a CSV column of paths), uploads them under an
``s3://bucket/prefix``, and can write a CSV mapping each local file to its new
object. The two round-trip::

    uv run upload_s3.py ./images s3://my-bucket/photos/ --out-csv up.csv
    uv run dl_s3_csv.py --csv up.csv --url-col s3_uri --images-dir ./back

Keys are flattened to the file's basename (``<prefix>/<filename>``), matching
``dl_s3_csv.py``'s ``images_dir / Path(key).name`` destination. Because
flattening can map two local files onto one key, duplicate basenames abort the
run before anything is uploaded.

Usage::

    uv run upload_s3.py ./images s3://my-bucket/photos/
    uv run upload_s3.py a.jpg b.png s3://my-bucket --acl public-read -P
    uv run upload_s3.py ./shots s3://bkt/pfx -r -s .jpg,.png --out-csv out.csv
    uv run upload_s3.py --csv in.csv --path-col local_file_path s3://bkt/pfx \\
        --out-csv out.csv --s3-col s3_uri

Credentials and region resolve through boto3's normal chain (env vars,
``~/.aws/config``, profiles); ``--profile`` and ``--region`` override them.
"""

from __future__ import annotations

import csv as csv_module
import mimetypes
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import boto3
import multiprocess
import typer
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger
from p_tqdm import p_map

app = typer.Typer(
    add_completion=False,
    help="Upload local files to S3 in parallel, optionally emitting a CSV.",
)

# Extensions the stdlib ``mimetypes`` table still misses on some platforms.
EXTRA_CONTENT_TYPES: Dict[str, str] = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".webp": "image/webp",
}

# Process-local lazy singleton. Each worker process in the p_tqdm pool
# initializes this once on its first call, then reuses the connection pool for
# every subsequent upload it handles — avoiding per-file TLS handshake overhead.
_S3_CLIENT: object = None


class OutputFormat(str, Enum):
    """How an uploaded object is identified on stdout and in the CSV."""

    uri = "uri"
    url = "url"
    key = "key"


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def parse_location(location: str) -> Tuple[str, str]:
    """Split an S3 location into its bucket and key prefix.

    Args:
        location: Either an ``s3://bucket/prefix`` URI or a bare bucket name.
            A trailing slash and any ``s3://`` scheme are handled; the prefix
            may be empty.

    Returns:
        A ``(bucket, prefix)`` tuple. ``prefix`` is ``""`` when the location
        names only a bucket.

    Examples:
        >>> parse_location("s3://my-bucket/photos/2026/")
        ('my-bucket', 'photos/2026/')
        >>> parse_location("my-bucket")
        ('my-bucket', '')
        >>> parse_location("s3://my-bucket")
        ('my-bucket', '')
        >>> parse_location("my-bucket/photos")
        ('my-bucket', 'photos')
    """
    stripped = location[5:] if location.startswith("s3://") else location
    stripped = stripped.lstrip("/")
    bucket, _, prefix = stripped.partition("/")
    return bucket, prefix


def normalize_suffix(value: str) -> str:
    """Lowercase a suffix and ensure it has a single leading dot.

    Args:
        value: A file extension with or without a leading dot
            (e.g. ``"JPG"`` or ``".jpg"``).

    Returns:
        The suffix lowercased with exactly one leading dot, or ``""`` when
        ``value`` is blank.

    Examples:
        >>> normalize_suffix("JPG")
        '.jpg'
        >>> normalize_suffix(".PnG")
        '.png'
        >>> normalize_suffix("  ")
        ''
    """
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith(".") else "." + cleaned


def normalize_suffixes(values: Optional[List[str]]) -> Tuple[str, ...]:
    """Normalize a list of ``--suffix`` values into a deduped tuple.

    Each value may itself be comma-separated (``-s .jpg,.png``), so this
    flattens, normalizes (see :func:`normalize_suffix`), drops blanks, and
    removes duplicates while preserving first-seen order.

    Args:
        values: The raw ``--suffix`` option values, or ``None`` when the flag
            was not given.

    Returns:
        A tuple of normalized suffixes; empty when no filtering is requested.

    Examples:
        >>> normalize_suffixes(None)
        ()
        >>> normalize_suffixes([".jpg", "PNG"])
        ('.jpg', '.png')
        >>> normalize_suffixes(["jpg,.JPG", " png "])
        ('.jpg', '.png')
    """
    if not values:
        return ()
    seen: Dict[str, None] = {}
    for raw in values:
        for part in raw.split(","):
            suffix = normalize_suffix(part)
            if suffix:
                seen.setdefault(suffix, None)
    return tuple(seen)


def matches_suffix(name: str, suffixes: Tuple[str, ...]) -> bool:
    """Report whether ``name`` ends with one of ``suffixes`` (case-insensitive).

    Args:
        name: A file name or path.
        suffixes: Normalized suffixes from :func:`normalize_suffixes`. An empty
            tuple matches every name (no filtering).

    Returns:
        ``True`` if the file should be included.

    Examples:
        >>> matches_suffix("a/b/shot.JPG", (".jpg", ".png"))
        True
        >>> matches_suffix("a/b/notes.txt", (".jpg", ".png"))
        False
        >>> matches_suffix("anything", ())
        True
    """
    return not suffixes or name.lower().endswith(suffixes)


def normalize_region(location: Optional[str]) -> str:
    """Coalesce a ``get_bucket_location`` result into a usable region name.

    Args:
        location: The ``LocationConstraint`` value from
            ``get_bucket_location``. S3 returns ``None``/``""`` for us-east-1
            and the legacy alias ``"EU"`` for eu-west-1.

    Returns:
        A concrete region name.

    Examples:
        >>> normalize_region(None)
        'us-east-1'
        >>> normalize_region("")
        'us-east-1'
        >>> normalize_region("EU")
        'eu-west-1'
        >>> normalize_region("ap-southeast-2")
        'ap-southeast-2'
    """
    if not location:
        return "us-east-1"
    if location == "EU":
        return "eu-west-1"
    return location


def build_object_url(bucket: str, key: str, region: str, style: str = "auto") -> str:
    """Build a public HTTPS URL for an S3 object.

    Uses virtual-hosted-style (``https://BUCKET.s3.REGION.amazonaws.com/KEY``)
    by default. Buckets whose name contains a dot fall back to path-style
    (``https://s3.REGION.amazonaws.com/BUCKET/KEY``) because the wildcard TLS
    certificate ``*.s3.REGION.amazonaws.com`` matches only one label and would
    otherwise mismatch over HTTPS. Only the key is URL-encoded.

    Args:
        bucket: Bucket name.
        key: Object key.
        region: Bucket region (see :func:`normalize_region`).
        style: ``"auto"`` (default), ``"virtual"``, or ``"path"``.

    Returns:
        The object URL.

    Examples:
        >>> build_object_url("my-bucket", "photos/a.jpg", "us-east-1")
        'https://my-bucket.s3.us-east-1.amazonaws.com/photos/a.jpg'
        >>> build_object_url("my.dotted.bucket", "c.jpg", "eu-west-1")
        'https://s3.eu-west-1.amazonaws.com/my.dotted.bucket/c.jpg'
        >>> build_object_url("b", "a b/c+d.jpg", "us-east-1")
        'https://b.s3.us-east-1.amazonaws.com/a%20b/c%2Bd.jpg'
    """
    import urllib.parse

    encoded_key = urllib.parse.quote(key, safe="/")
    use_path = style == "path" or (style == "auto" and "." in bucket)
    if use_path:
        return f"https://s3.{region}.amazonaws.com/{bucket}/{encoded_key}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"


def render_target(bucket: str, key: str, region: str, fmt: OutputFormat) -> str:
    """Render one uploaded object as a single identifier string.

    Args:
        bucket: Bucket name.
        key: Object key.
        region: Bucket region (only used for ``url``).
        fmt: The desired output format.

    Returns:
        The line to print / store for this object.

    Examples:
        >>> render_target("my-bucket", "photos/a.jpg", "us-east-1", OutputFormat.uri)
        's3://my-bucket/photos/a.jpg'
        >>> render_target("my-bucket", "photos/a.jpg", "us-east-1", OutputFormat.key)
        'photos/a.jpg'
        >>> render_target("my-bucket", "photos/a.jpg", "us-east-1", OutputFormat.url)
        'https://my-bucket.s3.us-east-1.amazonaws.com/photos/a.jpg'
    """
    if fmt is OutputFormat.key:
        return key
    if fmt is OutputFormat.uri:
        return f"s3://{bucket}/{key}"
    return build_object_url(bucket, key, region)


def default_column_name(fmt: OutputFormat) -> str:
    """Name the CSV column that holds the uploaded object's identifier.

    Args:
        fmt: The output format the column will contain.

    Returns:
        The default column name for that format.

    Examples:
        >>> default_column_name(OutputFormat.uri)
        's3_uri'
        >>> default_column_name(OutputFormat.url)
        's3_url'
        >>> default_column_name(OutputFormat.key)
        's3_key'
    """
    return {"uri": "s3_uri", "url": "s3_url", "key": "s3_key"}[fmt.value]


def join_key(prefix: str, name: str) -> str:
    """Join a key prefix and a file name into an S3 key.

    Stray leading/trailing slashes and duplicated separators in ``prefix`` are
    normalized away, so ``s3://bkt/pfx`` and ``s3://bkt/pfx/`` behave the same.

    Args:
        prefix: The key prefix from the destination (may be empty).
        name: The object's base name.

    Returns:
        The full object key.

    Examples:
        >>> join_key("photos/2026/", "a.jpg")
        'photos/2026/a.jpg'
        >>> join_key("photos", "a.jpg")
        'photos/a.jpg'
        >>> join_key("", "a.jpg")
        'a.jpg'
        >>> join_key("/photos//", "a.jpg")
        'photos/a.jpg'
    """
    cleaned = prefix.strip("/")
    return f"{cleaned}/{name}" if cleaned else name


def plan_uploads(paths: Sequence[Path], prefix: str) -> List[Tuple[Path, str]]:
    """Pair every local path with the flattened key it will be uploaded to.

    Args:
        paths: Local file paths, in the order they should be uploaded.
        prefix: The destination key prefix.

    Returns:
        A list of ``(path, key)`` pairs, in input order.

    Examples:
        >>> plan_uploads([Path("a/01.jpg"), Path("b/02.png")], "pfx/")
        [(PosixPath('a/01.jpg'), 'pfx/01.jpg'), (PosixPath('b/02.png'), 'pfx/02.png')]
        >>> plan_uploads([Path("/tmp/c.jpg")], "")
        [(PosixPath('/tmp/c.jpg'), 'c.jpg')]
    """
    return [(path, join_key(prefix, path.name)) for path in paths]


def find_collisions(plan: Sequence[Tuple[Path, str]]) -> Dict[str, List[str]]:
    """Find keys that more than one distinct local file would be written to.

    Flattening to the basename means ``a/01.jpg`` and ``b/01.jpg`` both target
    ``<prefix>/01.jpg``; the second upload would silently replace the first, so
    the caller aborts instead.

    Args:
        plan: ``(path, key)`` pairs from :func:`plan_uploads`.

    Returns:
        A mapping of each colliding key to the sorted distinct local paths that
        claim it. Empty when the plan is collision-free.

    Examples:
        >>> plan = plan_uploads([Path("a/01.jpg"), Path("b/01.jpg")], "pfx")
        >>> find_collisions(plan)
        {'pfx/01.jpg': ['a/01.jpg', 'b/01.jpg']}
        >>> find_collisions(plan_uploads([Path("a/01.jpg")], "pfx"))
        {}
        >>> find_collisions(plan_uploads([Path("a.jpg"), Path("a.jpg")], ""))
        {}
    """
    claims: Dict[str, List[str]] = {}
    for path, key in plan:
        claims.setdefault(key, [])
        text = str(path)
        if text not in claims[key]:
            claims[key].append(text)
    return {key: sorted(paths) for key, paths in claims.items() if len(paths) > 1}


def guess_content_type(name: str) -> Optional[str]:
    """Guess an object's ``Content-Type`` from its file extension.

    Without this S3 stores uploads as ``binary/octet-stream``, which makes a
    browser download an image instead of rendering it inline.

    Args:
        name: A file name or path.

    Returns:
        The MIME type, or ``None`` when the extension is unknown.

    Examples:
        >>> guess_content_type("a/b/shot.JPG")
        'image/jpeg'
        >>> guess_content_type("notes.txt")
        'text/plain'
        >>> guess_content_type("photo.heic")
        'image/heic'
        >>> guess_content_type("mystery.zzz") is None
        True
    """
    suffix = Path(name).suffix.lower()
    if suffix in EXTRA_CONTENT_TYPES:
        return EXTRA_CONTENT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(name)
    return guessed


def build_extra_args(
    content_type: Optional[str] = None,
    acl: Optional[str] = None,
    storage_class: Optional[str] = None,
) -> Dict[str, str]:
    """Assemble the ``ExtraArgs`` dict for a single ``upload_file`` call.

    Args:
        content_type: MIME type to store, or ``None`` to let S3 default it.
        acl: Canned ACL such as ``"public-read"``, or ``None``.
        storage_class: Storage class such as ``"STANDARD_IA"``, or ``None``.

    Returns:
        A dict of boto3 ``ExtraArgs``; empty when nothing is set.

    Examples:
        >>> build_extra_args("image/jpeg")
        {'ContentType': 'image/jpeg'}
        >>> build_extra_args(None, "public-read", "STANDARD_IA")
        {'ACL': 'public-read', 'StorageClass': 'STANDARD_IA'}
        >>> build_extra_args()
        {}
    """
    extra: Dict[str, str] = {}
    if content_type:
        extra["ContentType"] = content_type
    if acl:
        extra["ACL"] = acl
    if storage_class:
        extra["StorageClass"] = storage_class
    return extra


def summarize(statuses: Iterable[str]) -> Tuple[int, int, int]:
    """Count ``ok`` / ``skip`` / ``err`` outcomes.

    Args:
        statuses: The status strings returned by :func:`upload_one`.

    Returns:
        An ``(n_ok, n_skip, n_err)`` tuple.

    Examples:
        >>> summarize(["ok", "ok", "skip", "err:ClientError"])
        (2, 1, 1)
        >>> summarize([])
        (0, 0, 0)
    """
    statuses = list(statuses)
    n_ok = sum(1 for s in statuses if s == "ok")
    n_skip = sum(1 for s in statuses if s == "skip")
    n_err = sum(1 for s in statuses if s.startswith("err"))
    return n_ok, n_skip, n_err


def dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    """Drop repeated paths while preserving first-seen order.

    A CSV may name the same local file on several rows; it only needs to be
    uploaded once, with every row mapped back to that one result.

    Args:
        paths: Local paths, possibly with duplicates.

    Returns:
        The deduped paths in first-seen order.

    Examples:
        >>> dedupe_paths([Path("a.jpg"), Path("b.jpg"), Path("a.jpg")])
        [PosixPath('a.jpg'), PosixPath('b.jpg')]
        >>> dedupe_paths([])
        []
    """
    seen: Dict[str, None] = {}
    out: List[Path] = []
    for path in paths:
        text = str(path)
        if text not in seen:
            seen[text] = None
            out.append(path)
    return out


# --------------------------------------------------------------------------- #
# Filesystem / S3 adapters (the only side-effecting code)
# --------------------------------------------------------------------------- #


def collect_files(
    sources: Sequence[Path], recursive: bool, suffixes: Tuple[str, ...]
) -> Tuple[List[Path], List[Path]]:
    """Expand the positional sources into a concrete list of files.

    A source that is a directory is scanned (top level only unless
    ``recursive``), skipping hidden files such as ``.DS_Store`` and applying the
    suffix filter. A source that is a file is taken as-is — an explicitly named
    file is never filtered out by ``--suffix``.

    Args:
        sources: Positional source paths (files and/or directories).
        recursive: Whether directory scans descend into subdirectories.
        suffixes: Normalized suffixes used to filter directory scans.

    Returns:
        A ``(files, missing)`` tuple: the files to upload (directory scans
        sorted by path) and any source paths that do not exist.
    """
    files: List[Path] = []
    missing: List[Path] = []
    for src in sources:
        if src.is_dir():
            walker = src.rglob("*") if recursive else src.iterdir()
            found = sorted(
                p
                for p in walker
                if p.is_file()
                and not p.name.startswith(".")
                and matches_suffix(p.name, suffixes)
            )
            logger.debug("{}: {} file(s) matched", src, len(found))
            files.extend(found)
        elif src.exists():
            files.append(src)
        else:
            missing.append(src)
    return files, missing


def resolve_region(session: "boto3.Session", bucket: str, region: Optional[str]) -> str:
    """Determine the bucket's region, honouring an explicit override.

    Args:
        session: A configured :class:`boto3.Session`.
        bucket: Bucket name.
        region: An explicit region from ``--region``; when set it is returned
            as-is and no API call is made.

    Returns:
        The resolved region name (see :func:`normalize_region`).
    """
    if region:
        return region
    location = session.client("s3").get_bucket_location(Bucket=bucket)
    return normalize_region(location.get("LocationConstraint"))


def _get_s3_client():
    """Return this worker process's lazily built S3 client."""
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client(
            "s3",
            config=Config(
                max_pool_connections=10,
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )
    return _S3_CLIENT


def upload_one(
    args: Tuple[str, str, str, bool, Dict[str, str]],
) -> Tuple[str, str, str]:
    """Upload a single file. Returns ``(status, local_path, key)``.

    ``status`` is ``"ok"``, ``"skip"`` (the key already exists and
    ``overwrite`` is false), or ``"err:<ExceptionName>"``. Runs inside a
    ``p_tqdm`` worker process, so it takes one picklable tuple and reuses the
    process-local client from :func:`_get_s3_client`.

    Args:
        args: ``(local_path, bucket, key, overwrite, extra_args)``.

    Returns:
        A ``(status, local_path, key)`` tuple.
    """
    path_str, bucket, key, overwrite, extra = args
    if not Path(path_str).is_file():
        return "err:FileNotFoundError", path_str, key
    try:
        client = _get_s3_client()
        if not overwrite:
            try:
                client.head_object(Bucket=bucket, Key=key)
                return "skip", path_str, key
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code not in ("404", "NoSuchKey", "NotFound"):
                    raise
        client.upload_file(path_str, bucket, key, ExtraArgs=extra or None)
        return "ok", path_str, key
    except Exception as exc:  # noqa: BLE001 - reported per file, never fatal
        return f"err:{type(exc).__name__}", path_str, key


def extract_paths(rows: Sequence[Dict[str, str]], path_col: str) -> List[Path]:
    """Pull the local paths out of one column of the parsed CSV rows.

    ``~`` is expanded so a CSV written by hand can use ``~/Pictures/a.jpg``.

    Args:
        rows: Rows as parsed by :func:`read_csv_rows`.
        path_col: The column holding local file paths.

    Returns:
        One path per row, duplicates included, in row order.

    Examples:
        >>> rows = [{"fp": "a.jpg"}, {"fp": "b/c.png"}, {"fp": "a.jpg"}]
        >>> extract_paths(rows, "fp")
        [PosixPath('a.jpg'), PosixPath('b/c.png'), PosixPath('a.jpg')]
    """
    return [Path(str(row.get(path_col) or "")).expanduser() for row in rows]


def add_column(
    rows: Sequence[Dict[str, str]], column: str, values: Sequence[str]
) -> List[Dict[str, str]]:
    """Return the rows with one extra column appended.

    Args:
        rows: The parsed input rows.
        column: Name of the column to add.
        values: One value per row, in row order.

    Returns:
        New row dicts with ``column`` set.

    Examples:
        >>> rows = [{"id": "1"}, {"id": "2"}]
        >>> add_column(rows, "s3_uri", ["s3://b/1.jpg", ""])
        [{'id': '1', 's3_uri': 's3://b/1.jpg'}, {'id': '2', 's3_uri': ''}]
    """
    return [{**row, column: value} for row, value in zip(rows, values)]


def build_result_rows(
    paths: Sequence[Path], targets: Sequence[str], column: str
) -> List[Dict[str, str]]:
    """Build the two-column rows emitted for directory / file-list input.

    Args:
        paths: The local paths that were uploaded.
        targets: The rendered identifier per path (``""`` when it failed).
        column: Name of the identifier column.

    Returns:
        Rows of ``local_path`` + ``column``.

    Examples:
        >>> build_result_rows([Path("a.jpg")], ["s3://b/a.jpg"], "s3_uri")
        [{'local_path': 'a.jpg', 's3_uri': 's3://b/a.jpg'}]
    """
    return [
        {"local_path": str(path), column: target}
        for path, target in zip(paths, targets)
    ]


def read_csv_rows(
    csv_path: Path, limit: Optional[int]
) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read the input CSV with the stdlib reader, keeping every value verbatim.

    ``csv`` rather than ``pandas`` on purpose: every cell stays the string it
    was (no NaN, no lost leading zeros), there is no heavy import, and — the
    reason it matters here — importing numpy/pandas before ``p_map`` forks
    deadlocks the workers on macOS inside botocore's proxy lookup.

    Args:
        csv_path: The input CSV.
        limit: Keep only the first N rows, or ``None`` for all.

    Returns:
        A ``(fieldnames, rows)`` tuple.
    """
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv_module.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    if limit is not None:
        rows = rows[:limit]
    return fieldnames, rows


def write_csv_rows(
    out_csv: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, str]]
) -> None:
    """Write ``rows`` to ``out_csv`` with a header line.

    Args:
        out_csv: Destination path.
        fieldnames: Column order for the header.
        rows: The rows to write.
    """
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


@app.command()
def main(
    sources: Optional[List[Path]] = typer.Argument(
        None,
        metavar="[SOURCE]...",
        help="Files and/or directories to upload. Omit when using --csv.",
    ),
    destination: str = typer.Argument(
        ...,
        metavar="DESTINATION",
        help="s3://bucket/prefix or a bare bucket name.",
    ),
    csv: Optional[Path] = typer.Option(
        None, "--csv", help="Input CSV whose --path-col holds local file paths."
    ),
    path_col: str = typer.Option(
        "local_file_path",
        "--path-col",
        help="Column of local paths to upload (with --csv).",
    ),
    out_csv: Optional[Path] = typer.Option(
        None, "--out-csv", help="Write a CSV of the results here."
    ),
    s3_col: Optional[str] = typer.Option(
        None,
        "--s3-col",
        help="Name of the result column; defaults to s3_uri/s3_url/s3_key.",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.uri,
        "--format",
        "-f",
        case_sensitive=False,
        help="How to identify each uploaded object.",
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Descend into subdirectories."
    ),
    suffix: Optional[List[str]] = typer.Option(
        None,
        "--suffix",
        "-s",
        help="Filter directory scans by extension; repeat or comma-separate.",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-n", min=1, help="Cap on files (or CSV rows) to upload."
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Upload even if the key already exists."
    ),
    content_type: bool = typer.Option(
        True,
        "--content-type/--no-content-type",
        help="Set Content-Type from the file extension.",
    ),
    acl: Optional[str] = typer.Option(
        None,
        "--acl",
        help="Canned ACL, e.g. public-read (rejected by buckets with ACLs disabled).",
    ),
    storage_class: Optional[str] = typer.Option(
        None, "--storage-class", help="e.g. STANDARD_IA, INTELLIGENT_TIERING."
    ),
    workers: int = typer.Option(64, "--workers", min=1, help="Parallel workers."),
    print_targets: bool = typer.Option(
        False, "--print", "-P", help="Print each uploaded object on stdout."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the local -> s3 plan and exit."
    ),
    region: Optional[str] = typer.Option(
        None, "--region", help="Bucket region; auto-detected if omitted."
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile name."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show debug-level logging."
    ),
) -> None:
    """Upload local files to S3, optionally writing a CSV of the results."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{message}")

    bucket, prefix = parse_location(destination)
    if not bucket:
        logger.error("No bucket name in DESTINATION: {!r}", destination)
        raise typer.Exit(code=2)

    sources = list(sources or [])
    if csv is None and not sources:
        logger.error("Nothing to upload: pass SOURCE paths or --csv.")
        raise typer.Exit(code=2)
    if csv is not None and sources:
        logger.error("Pass either SOURCE paths or --csv, not both.")
        raise typer.Exit(code=2)
    if csv is not None and not csv.exists():
        logger.error("Input CSV not found: {}", csv)
        raise typer.Exit(code=2)
    if out_csv is not None and csv is not None and out_csv == csv:
        logger.error("--out-csv must differ from --csv")
        raise typer.Exit(code=2)

    column = s3_col or default_column_name(output_format)

    # ---- gather the files -------------------------------------------------- #
    fieldnames: List[str] = []
    rows: List[Dict[str, str]] = []
    row_paths: List[Path] = []
    if csv is not None:
        fieldnames, rows = read_csv_rows(csv, limit)
        if path_col not in fieldnames:
            logger.error(
                "column {!r} not in CSV (available columns: {})", path_col, fieldnames
            )
            raise typer.Exit(code=2)
        if column in fieldnames:
            logger.error(
                "refusing to overwrite existing column {!r}; pick a different --s3-col",
                column,
            )
            raise typer.Exit(code=2)
        row_paths = extract_paths(rows, path_col)
        files = dedupe_paths(row_paths)
        logger.info("{} row(s), {} unique file(s) from {}", len(rows), len(files), csv)
    else:
        suffixes = normalize_suffixes(suffix)
        files, missing = collect_files(sources, recursive, suffixes)
        if missing:
            for path in missing:
                logger.error("source not found: {}", path)
            raise typer.Exit(code=2)
        files = dedupe_paths(files)
        if limit is not None and len(files) > limit:
            logger.info("limiting to first {} of {} files", limit, len(files))
            files = files[:limit]

    if not files:
        logger.error("No files matched.")
        raise typer.Exit(code=2)

    # ---- plan, and refuse to clobber ---------------------------------------- #
    plan = plan_uploads(files, prefix)
    collisions = find_collisions(plan)
    if collisions:
        logger.error(
            "{} key(s) would be written by more than one file (keys are flattened "
            "to the basename); nothing was uploaded:",
            len(collisions),
        )
        for key, paths in list(collisions.items())[:10]:
            logger.error("  s3://{}/{} <- {}", bucket, key, ", ".join(paths))
        raise typer.Exit(code=2)

    if dry_run:
        for path, key in plan:
            typer.echo(f"{path} -> s3://{bucket}/{key}")
        logger.info("dry run: {} file(s) would be uploaded", len(plan))
        raise typer.Exit(code=0)

    # ---- resolve credentials / region --------------------------------------- #
    if profile:
        # Exported so the spawned p_tqdm workers build their clients the same way.
        os.environ["AWS_PROFILE"] = profile
    elif not os.environ.get("AWS_PROFILE"):
        logger.warning(
            "AWS_PROFILE is not set; falling back to the default credential chain"
        )

    session = boto3.Session(profile_name=profile or None, region_name=region or None)
    try:
        eff_region = resolve_region(session, bucket, region)
        os.environ["AWS_DEFAULT_REGION"] = eff_region
    except (ClientError, BotoCoreError) as exc:
        eff_region = region or session.region_name or "us-east-1"
        logger.warning(
            "could not detect the region of {} ({}); assuming {}",
            bucket,
            type(exc).__name__,
            eff_region,
        )
    logger.debug("bucket={} prefix={!r} region={}", bucket, prefix, eff_region)

    # ---- upload -------------------------------------------------------------- #
    args_list = [
        (
            str(path),
            bucket,
            key,
            overwrite,
            build_extra_args(
                guess_content_type(path.name) if content_type else None,
                acl,
                storage_class,
            ),
        )
        for path, key in plan
    ]
    logger.info(
        "uploading {} file(s) to s3://{}/{} with {} workers",
        len(args_list),
        bucket,
        prefix.strip("/"),
        workers,
    )
    # "spawn", not the platform default: forking a process that has already
    # touched the network stack deadlocks the pool on macOS (the workers sit in
    # sem_wait while the parent blocks reading the empty result pipe, and
    # botocore's proxy lookup calls fork-unsafe SystemConfiguration APIs).
    try:
        multiprocess.set_start_method("spawn", force=True)
    except RuntimeError:  # already set by an embedding process
        pass
    # p_map preserves input order; num_cpus sets the process pool size.
    results = p_map(upload_one, args_list, num_cpus=workers)

    n_ok, n_skip, n_err = summarize(status for status, _, _ in results)
    logger.success("done: ok={} skip={} err={}", n_ok, n_skip, n_err)
    if n_err:
        for status, path_str, _ in [r for r in results if r[0].startswith("err")][:10]:
            logger.error("{} -> {}", path_str, status)
    if n_skip and not overwrite:
        logger.info("{} key(s) already existed (use --overwrite to replace)", n_skip)

    # ---- report -------------------------------------------------------------- #
    by_path: Dict[str, str] = {
        path_str: (
            ""
            if status.startswith("err")
            else render_target(bucket, key, eff_region, output_format)
        )
        for status, path_str, key in results
    }
    targets = [by_path.get(str(path), "") for path in files]

    if print_targets:
        for target in targets:
            if target:
                typer.echo(target)

    if out_csv is not None:
        if csv is not None:
            write_csv_rows(
                out_csv,
                [*fieldnames, column],
                add_column(rows, column, [by_path.get(str(p), "") for p in row_paths]),
            )
        else:
            write_csv_rows(
                out_csv,
                ["local_path", column],
                build_result_rows(files, targets, column),
            )
        logger.info("wrote output CSV: {}", out_csv)

    if n_err:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
