# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3>=1.34", "typer>=0.12", "loguru>=0.7"]
# ///
"""List S3 objects filtered by file suffix, as keys, URLs, or ``s3://`` URIs.

A friendlier, paginated replacement for::

    aws s3api list-objects-v2 --bucket BUCKET --prefix "your/folder/" \\
      --query "Contents[?ends_with(Key,'.mp4')||ends_with(Key,'.mov')].Key" \\
      --output text | tr '\\t' '\\n' \\
      | sed 's#^#https://BUCKET.s3.REGION.amazonaws.com/#'

Unlike the one-liner above it paginates past the first 1000 keys, auto-detects
the bucket region for URLs, and can emit raw keys, HTTPS URLs, or ``s3://``
URIs. Credentials and region resolve through boto3's normal chain (env vars,
``~/.aws/config``, profiles); ``--profile`` and ``--region`` override them.

Run it self-contained with ``uv``::

    uv run scripts/list_s3.py s3://BUCKET/your/folder/ -s .mp4 -s .mov
    uv run scripts/list_s3.py BUCKET --prefix your/folder/ -s mp4,mov -f url
    uv run scripts/list_s3.py s3://BUCKET/clips/ -f uri -n 5
"""

from __future__ import annotations

import sys
import urllib.parse
from enum import Enum
from typing import Callable, Iterable, Iterator, List, Optional

import boto3
import typer
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger

app = typer.Typer(
    add_completion=False,
    help="List S3 objects filtered by file suffix, as keys, URLs, or s3:// URIs.",
)


class OutputFormat(str, Enum):
    """What to print for each matching object."""

    key = "key"
    url = "url"
    uri = "uri"


def parse_location(location: str) -> tuple[str, str]:
    """Split an S3 location into its bucket and key prefix.

    Args:
        location: Either an ``s3://bucket/prefix`` URI or a bare bucket name.
            A trailing slash and any ``s3://`` scheme are handled; the prefix
            may be empty.

    Returns:
        A ``(bucket, prefix)`` tuple. ``prefix`` is ``""`` when the location
        names only a bucket.

    Examples:
        >>> parse_location("s3://my-bucket/your/folder/")
        ('my-bucket', 'your/folder/')
        >>> parse_location("my-bucket")
        ('my-bucket', '')
        >>> parse_location("s3://my-bucket")
        ('my-bucket', '')
        >>> parse_location("my-bucket/clips")
        ('my-bucket', 'clips')
    """
    stripped = location[5:] if location.startswith("s3://") else location
    stripped = stripped.lstrip("/")
    bucket, _, prefix = stripped.partition("/")
    return bucket, prefix


def normalize_suffix(value: str) -> str:
    """Lowercase a suffix and ensure it has a single leading dot.

    Args:
        value: A file extension with or without a leading dot
            (e.g. ``"MP4"`` or ``".mp4"``).

    Returns:
        The suffix lowercased with exactly one leading dot, or ``""`` when
        ``value`` is blank.

    Examples:
        >>> normalize_suffix("MP4")
        '.mp4'
        >>> normalize_suffix(".MoV")
        '.mov'
        >>> normalize_suffix("  ")
        ''
    """
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith(".") else "." + cleaned


def normalize_suffixes(values: Optional[List[str]]) -> tuple[str, ...]:
    """Normalize a list of ``--suffix`` values into a deduped tuple.

    Each value may itself be comma-separated (``-s .mp4,.mov``), so this
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
        >>> normalize_suffixes([".mp4", "MOV"])
        ('.mp4', '.mov')
        >>> normalize_suffixes(["mp4,.MP4", " mov "])
        ('.mp4', '.mov')
    """
    if not values:
        return ()
    seen: dict[str, None] = {}
    for raw in values:
        for part in raw.split(","):
            suffix = normalize_suffix(part)
            if suffix:
                seen.setdefault(suffix, None)
    return tuple(seen)


def matches_suffix(key: str, suffixes: tuple[str, ...]) -> bool:
    """Report whether ``key`` ends with one of ``suffixes`` (case-insensitive).

    Args:
        key: The S3 object key.
        suffixes: Normalized suffixes from :func:`normalize_suffixes`. An empty
            tuple matches every key (no filtering).

    Returns:
        ``True`` if the key should be included.

    Examples:
        >>> matches_suffix("a/b/clip.MP4", (".mp4", ".mov"))
        True
        >>> matches_suffix("a/b/notes.txt", (".mp4", ".mov"))
        False
        >>> matches_suffix("anything", ())
        True
    """
    return not suffixes or key.lower().endswith(suffixes)


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
        >>> build_object_url("my-bucket", "a/b/clip.mp4", "us-east-1")
        'https://my-bucket.s3.us-east-1.amazonaws.com/a/b/clip.mp4'
        >>> build_object_url("my.dotted.bucket", "c.mp4", "eu-west-1")
        'https://s3.eu-west-1.amazonaws.com/my.dotted.bucket/c.mp4'
        >>> build_object_url("b", "a b/c+d.mp4", "us-east-1")
        'https://b.s3.us-east-1.amazonaws.com/a%20b/c%2Bd.mp4'
    """
    encoded_key = urllib.parse.quote(key, safe="/")
    use_path = style == "path" or (style == "auto" and "." in bucket)
    if use_path:
        return f"https://s3.{region}.amazonaws.com/{bucket}/{encoded_key}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"


def render(obj: dict, bucket: str, region: str, fmt: OutputFormat) -> str:
    """Render one S3 object dict as a single output line.

    Args:
        obj: An object entry from ``list_objects_v2`` (must contain ``"Key"``).
        bucket: Bucket name.
        region: Bucket region (only used for ``url``).
        fmt: The desired output format.

    Returns:
        The line to print for this object.

    Examples:
        >>> obj = {"Key": "clips/a.mp4"}
        >>> render(obj, "my-bucket", "us-east-1", OutputFormat.key)
        'clips/a.mp4'
        >>> render(obj, "my-bucket", "us-east-1", OutputFormat.uri)
        's3://my-bucket/clips/a.mp4'
        >>> render(obj, "my-bucket", "us-east-1", OutputFormat.url)
        'https://my-bucket.s3.us-east-1.amazonaws.com/clips/a.mp4'
    """
    key = obj["Key"]
    if fmt is OutputFormat.key:
        return key
    if fmt is OutputFormat.uri:
        return f"s3://{bucket}/{key}"
    return build_object_url(bucket, key, region)


def iter_objects(
    list_pages: Callable[[str, str], Iterable[dict]],
    bucket: str,
    prefix: str = "",
    suffixes: tuple[str, ...] = (),
    limit: Optional[int] = None,
) -> Iterator[dict]:
    """Yield matching S3 object dicts across all pages.

    This is boto3-free: ``list_pages`` is injected so the listing logic can be
    tested without a live S3 (the real adapter is :func:`s3_pages`). Full object
    dicts are yielded (not just keys) so future metadata output is a pure
    formatting add-on rather than a re-plumb of this path.

    Args:
        list_pages: Callable ``(bucket, prefix) -> iterable of page dicts``,
            each shaped like a ``list_objects_v2`` response.
        bucket: Bucket name (passed through to ``list_pages``).
        prefix: Key prefix to list under.
        suffixes: Normalized suffixes to filter by (empty = no filter).
        limit: Stop after yielding this many objects (``None`` = no limit).

    Yields:
        Matching object dicts, in listing order.

    Examples:
        >>> pages = [{"Contents": [{"Key": "a.mp4"}, {"Key": "b.txt"}]},
        ...          {"Contents": [{"Key": "c.MP4"}]}, {}]
        >>> got = iter_objects(lambda b, p: pages, "bk", suffixes=(".mp4",))
        >>> [o["Key"] for o in got]
        ['a.mp4', 'c.MP4']
        >>> got = iter_objects(lambda b, p: pages, "bk", limit=2)
        >>> [o["Key"] for o in got]
        ['a.mp4', 'b.txt']
    """
    count = 0
    for page in list_pages(bucket, prefix):
        for obj in page.get("Contents", []):
            if matches_suffix(obj["Key"], suffixes):
                yield obj
                count += 1
                if limit is not None and count >= limit:
                    return


def s3_pages(session: "boto3.Session", bucket: str, prefix: str) -> Iterable[dict]:
    """Yield ``list_objects_v2`` pages for ``bucket``/``prefix`` (boto3 adapter).

    The single place the S3 paginator is touched, so :func:`iter_objects` stays
    testable. The paginator transparently follows continuation tokens, so this
    streams every key, not just the first 1000.

    Args:
        session: A configured :class:`boto3.Session`.
        bucket: Bucket name.
        prefix: Key prefix to list under.

    Returns:
        An iterable of page dicts.
    """
    paginator = session.client("s3").get_paginator("list_objects_v2")
    return paginator.paginate(Bucket=bucket, Prefix=prefix)


def resolve_region(
    session: "boto3.Session", bucket: str, region: Optional[str]
) -> str:
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


@app.command()
def main(
    location: str = typer.Argument(
        ...,
        metavar="LOCATION",
        help="s3://bucket/prefix or a bare bucket name.",
    ),
    prefix: Optional[str] = typer.Option(
        None,
        "--prefix",
        "-p",
        help="Key prefix; overrides any prefix in LOCATION.",
    ),
    suffix: Optional[List[str]] = typer.Option(
        None,
        "--suffix",
        "-s",
        help="Filter by extension(s); repeat or comma-separate. Omit = all.",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.key,
        "--format",
        "-f",
        case_sensitive=False,
        help="What to print per object.",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-n", min=1, help="Max objects to return."
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="Bucket region for url format; auto-detected if omitted.",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="AWS profile name."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show debug-level logging."
    ),
) -> None:
    """List S3 objects filtered by file suffix."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{message}")

    bucket, loc_prefix = parse_location(location)
    if not bucket:
        logger.error("No bucket name in LOCATION: {!r}", location)
        raise typer.Exit(code=2)

    if prefix is not None and loc_prefix and prefix != loc_prefix:
        logger.warning(
            "Prefix {!r} from LOCATION overridden by --prefix {!r}",
            loc_prefix,
            prefix,
        )
    eff_prefix = prefix if prefix is not None else loc_prefix
    suffixes = normalize_suffixes(suffix)
    logger.debug(
        "bucket={} prefix={!r} suffixes={} format={}",
        bucket,
        eff_prefix,
        suffixes,
        output_format.value,
    )

    session = boto3.Session(
        profile_name=profile or None, region_name=region or None
    )

    try:
        eff_region = (
            resolve_region(session, bucket, region)
            if output_format is OutputFormat.url
            else ""
        )
        count = 0
        for obj in iter_objects(
            lambda b, p: s3_pages(session, b, p),
            bucket,
            eff_prefix,
            suffixes,
            limit,
        ):
            typer.echo(render(obj, bucket, eff_region, output_format))
            count += 1
    except (ClientError, BotoCoreError) as exc:
        logger.error("S3 request failed: {}", exc)
        raise typer.Exit(code=1) from exc

    logger.info("Listed {} object(s)", count)


if __name__ == "__main__":
    app()
