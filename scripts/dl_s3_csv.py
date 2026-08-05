# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "boto3>=1.34",
#   "typer>=0.12",
#   "loguru>=0.7",
#   "pandas>=2.0",
#   "p_tqdm>=1.4",
# ]
# ///
"""Download s3:// images listed in a CSV column to a local directory.

Reads an input CSV that contains a column of ``s3://`` URIs, downloads each
object to a local images directory in parallel, and (optionally) writes an
output CSV that adds a new column with the corresponding local file path.

Usage:
    uv run dl_s3_csv.py \\
        --csv <input.csv> \\
        --url-col image_url \\
        --images-dir ./images \\
        [--out-csv <output.csv>] \\
        [--local-fp-col-name local_file_path] \\
        [--workers 64] \\
        [--limit 1000] \\
        [--overwrite]
"""
from __future__ import annotations

import os
from pathlib import Path

import boto3
import pandas as pd
import typer
from botocore.config import Config
from loguru import logger
from p_tqdm import p_map

app = typer.Typer(add_completion=False)

# Process-local lazy singleton. Each worker process in the p_tqdm pool initializes
# this once on its first call, then reuses the connection pool for every subsequent
# download it handles — avoiding per-file TLS handshake overhead.
_S3_CLIENT: object = None


def _get_s3_client():
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


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """``s3://bucket/key`` -> ``(bucket, key)``."""
    if not uri.startswith("s3://"):
        raise ValueError(f"expected s3:// URI, got {uri!r}")
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"malformed s3 URI (missing bucket or key): {uri!r}")
    return bucket, key


def _download_one(
    args: tuple[str, str, bool],
) -> tuple[str, str, str | None]:
    """Download a single object. Returns ``(status, s3_uri, local_path_str)``.

    ``status`` is one of ``"ok"``, ``"skip"``, or ``"err:..."``.
    Creates its own boto3 client (required for multiprocessing compatibility).
    """
    s3_uri, images_dir_str, overwrite = args
    images_dir = Path(images_dir_str)
    bucket, key = _parse_s3_uri(s3_uri)
    dest = images_dir / Path(key).name
    if not overwrite and dest.exists() and dest.stat().st_size > 0:
        return "skip", s3_uri, str(dest)
    try:
        _get_s3_client().download_file(bucket, key, str(dest))
        return "ok", s3_uri, str(dest)
    except Exception as e:
        return f"err:{type(e).__name__}", s3_uri, None


@app.command()
def main(
    csv: Path = typer.Option(..., "--csv", help="Input CSV with s3:// URIs."),
    url_col: str = typer.Option(..., "--url-col", help="Column with s3:// URIs."),
    images_dir: Path = typer.Option(
        ..., "--images-dir", help="Local destination directory."
    ),
    out_csv: Path | None = typer.Option(
        None, "--out-csv", help="If set, write a new CSV with the local-path column."
    ),
    local_fp_col_name: str = typer.Option(
        "local_file_path",
        "--local-fp-col-name",
        help="Name of the new column with local paths.",
    ),
    workers: int = typer.Option(64, "--workers", min=1, help="Parallel workers."),
    limit: int | None = typer.Option(
        None, "--limit", min=1, help="Cap on rows to download (default: all)."
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Re-download even if file exists."
    ),
) -> None:
    """Download s3:// images listed in CSV column to a local directory."""
    if not csv.exists():
        logger.error("input CSV not found: {}", csv)
        raise typer.Exit(code=2)
    if out_csv is not None and out_csv == csv:
        logger.error("--out-csv must differ from --csv")
        raise typer.Exit(code=2)

    images_dir.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("AWS_PROFILE"):
        logger.warning(
            "AWS_PROFILE is not set; falling back to the default credential chain"
        )

    logger.info("loading CSV: {}", csv)
    df = pd.read_csv(csv)
    if url_col not in df.columns:
        logger.error(
            "column {!r} not in CSV (available columns: {})",
            url_col,
            list(df.columns),
        )
        raise typer.Exit(code=2)
    if local_fp_col_name in df.columns:
        logger.error(
            "refusing to overwrite existing column {!r}; pick a different --local-fp-col-name",
            local_fp_col_name,
        )
        raise typer.Exit(code=2)

    n_total = len(df)
    if limit is not None:
        df = df.head(limit)
        logger.info("limiting to first {} of {} rows", len(df), n_total)

    uris = df[url_col].astype(str).tolist()
    if not uris:
        logger.info("no rows to process; exiting")
        raise typer.Exit(code=0)

    if not overwrite:
        n_existing = sum(
            1 for uri in uris
            if (images_dir / Path(uri.rsplit("/", 1)[-1])).exists()
            and (images_dir / Path(uri.rsplit("/", 1)[-1])).stat().st_size > 0
        )
        if n_existing:
            logger.info(
                "{} of {} files already exist locally and will be skipped (use --overwrite to re-download)",
                n_existing,
                len(uris),
            )

    logger.info("downloading {} files with {} workers", len(uris), workers)

    args_list = [(uri, str(images_dir), overwrite) for uri in uris]

    # p_map preserves input order; num_cpus sets the process pool size.
    results = p_map(_download_one, args_list, num_cpus=workers)

    statuses = [r[0] for r in results]
    n_ok = sum(1 for s in statuses if s == "ok")
    n_skip = sum(1 for s in statuses if s == "skip")
    n_err = sum(1 for s in statuses if s.startswith("err"))
    logger.success("done: ok={} skip={} err={}", n_ok, n_skip, n_err)
    if n_err:
        err_samples = [
            (uri, status) for status, uri, _ in results if status.startswith("err")
        ][:10]
        for uri, status in err_samples:
            logger.error("{} -> {}", uri, status)

    if out_csv is not None:
        df[local_fp_col_name] = [p if p is not None else "" for _, _, p in results]
        df.to_csv(out_csv, index=False)
        logger.info("wrote output CSV: {}", out_csv)


if __name__ == "__main__":
    app()