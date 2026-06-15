# /// script
# requires-python = ">=3.10"
# dependencies = ["ffmpeg-python>=0.2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Convert audio/video files between formats using ffmpeg-python.

Supports a single input file or batch conversion of a directory/glob. Run it
self-contained with ``uv``::

    uv run scripts/convert_media.py input.mov --to mp4
    uv run scripts/convert_media.py ./clips --to mp3 --recursive
    uv run scripts/convert_media.py "*.wav" --to flac --dry-run
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path
from typing import Optional

import ffmpeg
import typer
from loguru import logger

app = typer.Typer(
    add_completion=False,
    help="Convert audio/video files between formats using ffmpeg.",
)


def normalize_format(target_format: str) -> str:
    """Normalize a target format string into a bare extension.

    Args:
        target_format: Desired output format, with or without a leading dot
            (e.g. ``"mp4"`` or ``".mp4"``).

    Returns:
        The format lowercased and stripped of any leading dot.

    Examples:
        >>> normalize_format("MP4")
        'mp4'
        >>> normalize_format(".MkV")
        'mkv'
    """
    return target_format.lower().lstrip(".")


def build_output_path(
    src: Path, target_format: str, output: Optional[Path] = None
) -> Path:
    """Compute the destination path for a converted file.

    Args:
        src: Source media file.
        target_format: Desired output format/extension (dot optional).
        output: Optional explicit output. If it is an existing directory, or a
            path with no file extension, the converted file is placed inside it
            using the source stem. If it has an extension, it is treated as the
            exact output file. When ``None``, the output sits beside ``src``
            with the new extension.

    Returns:
        The resolved output path.

    Examples:
        >>> build_output_path(Path("clip.mov"), "mp4")
        PosixPath('clip.mp4')
        >>> build_output_path(Path("a.wav"), "mp3", Path("out"))
        PosixPath('out/a.mp3')
        >>> build_output_path(Path("x/a.wav"), ".flac", Path("y/song.flac"))
        PosixPath('y/song.flac')
    """
    ext = normalize_format(target_format)
    if output is None:
        return src.with_suffix(f".{ext}")
    # Treat as a directory if it exists as one, or has no file extension.
    looks_like_dir = output.is_dir() or output.suffix == ""
    if looks_like_dir:
        return output / src.with_suffix(f".{ext}").name
    return output


def build_output_kwargs(
    audio_bitrate: Optional[str] = None,
    video_codec: Optional[str] = None,
    audio_codec: Optional[str] = None,
) -> dict[str, str]:
    """Assemble ffmpeg output keyword arguments, omitting unset options.

    Args:
        audio_bitrate: Target audio bitrate (e.g. ``"192k"``).
        video_codec: Video codec name (e.g. ``"libx264"``).
        audio_codec: Audio codec name (e.g. ``"aac"``).

    Returns:
        A mapping suitable for ``ffmpeg.output(**kwargs)`` containing only the
        options that were provided.

    Examples:
        >>> build_output_kwargs()
        {}
        >>> build_output_kwargs(audio_bitrate="192k", audio_codec="aac")
        {'audio_bitrate': '192k', 'acodec': 'aac'}
        >>> build_output_kwargs(video_codec="libx264")
        {'vcodec': 'libx264'}
    """
    kwargs: dict[str, str] = {}
    if audio_bitrate:
        kwargs["audio_bitrate"] = audio_bitrate
    if video_codec:
        kwargs["vcodec"] = video_codec
    if audio_codec:
        kwargs["acodec"] = audio_codec
    return kwargs


def iter_input_files(input_path: str, recursive: bool = False) -> list[Path]:
    """Expand a file, directory, or glob pattern into a sorted list of files.

    Args:
        input_path: A path to a single file, a directory, or a glob pattern.
        recursive: When ``input_path`` is a directory, recurse into
            subdirectories.

    Returns:
        A sorted list of existing files. Directories are expanded to the files
        they contain (non-recursively unless ``recursive`` is set).

    Raises:
        FileNotFoundError: If nothing matches ``input_path``.
    """
    path = Path(input_path)
    if path.is_file():
        return [path]
    if path.is_dir():
        candidates = path.rglob("*") if recursive else path.iterdir()
        files = sorted(p for p in candidates if p.is_file())
    else:
        files = sorted(Path(p) for p in glob.glob(input_path, recursive=recursive))
        files = [p for p in files if p.is_file()]
    if not files:
        raise FileNotFoundError(f"No input files matched: {input_path!r}")
    return files


def convert_one(
    src: Path,
    dst: Path,
    *,
    overwrite: bool = False,
    output_kwargs: Optional[dict[str, str]] = None,
    quiet: bool = True,
) -> None:
    """Convert a single media file using ffmpeg.

    Args:
        src: Source media file.
        dst: Destination path. Parent directories are created as needed.
        overwrite: Pass ``-y`` to ffmpeg to overwrite an existing output.
        output_kwargs: Extra keyword arguments forwarded to ``ffmpeg.output``.
        quiet: Suppress ffmpeg's own stdout/stderr.

    Raises:
        ffmpeg.Error: If the underlying ffmpeg invocation fails.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    stream = ffmpeg.input(str(src)).output(str(dst), **(output_kwargs or {}))
    stream.run(
        overwrite_output=overwrite,
        quiet=quiet,
        capture_stdout=quiet,
        capture_stderr=quiet,
    )


def convert(
    input_path: str,
    target_format: str,
    *,
    output: Optional[Path] = None,
    recursive: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
    output_kwargs: Optional[dict[str, str]] = None,
    quiet: bool = True,
    convert_fn=convert_one,
) -> tuple[int, int]:
    """Convert one or many media files to ``target_format``.

    Args:
        input_path: File, directory, or glob pattern to convert.
        target_format: Desired output format/extension (dot optional).
        output: Optional output file (single input) or directory (batch).
        recursive: Recurse into subdirectories for directory inputs.
        overwrite: Overwrite existing outputs instead of skipping them.
        dry_run: Log the planned conversions without running ffmpeg.
        output_kwargs: Extra ffmpeg output options (see
            :func:`build_output_kwargs`).
        quiet: Suppress ffmpeg's own output.
        convert_fn: Injectable per-file conversion function (used for testing).

    Returns:
        A ``(succeeded, failed)`` count tuple.
    """
    files = iter_input_files(input_path, recursive=recursive)
    logger.info("Found {} input file(s)", len(files))
    succeeded = 0
    failed = 0
    for src in files:
        dst = build_output_path(src, target_format, output)
        if src.resolve() == dst.resolve():
            logger.warning("Skipping {}: source and destination are identical", src)
            continue
        if dst.exists() and not overwrite:
            logger.warning("Skipping {}: {} exists (use --overwrite)", src, dst)
            continue
        if dry_run:
            logger.info("[dry-run] {} -> {}", src, dst)
            succeeded += 1
            continue
        try:
            convert_fn(
                src,
                dst,
                overwrite=overwrite,
                output_kwargs=output_kwargs,
                quiet=quiet,
            )
            logger.success("{} -> {}", src, dst)
            succeeded += 1
        except ffmpeg.Error as exc:  # pragma: no cover - exercised via mocks
            detail = (
                exc.stderr.decode("utf-8", "replace").strip()
                if getattr(exc, "stderr", None)
                else str(exc)
            )
            logger.error("Failed to convert {}: {}", src, detail)
            failed += 1
    return succeeded, failed


@app.command()
def main(
    input_path: str = typer.Argument(
        ..., metavar="INPUT", help="Input file, directory, or glob pattern."
    ),
    target_format: str = typer.Option(
        ..., "--to", "-t", help="Target format/extension, e.g. mp4, mp3, wav."
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (single input) or directory (batch).",
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Recurse into subdirectories."
    ),
    audio_bitrate: Optional[str] = typer.Option(
        None, "--audio-bitrate", help="Audio bitrate, e.g. 192k."
    ),
    video_codec: Optional[str] = typer.Option(
        None, "--video-codec", help="Video codec, e.g. libx264."
    ),
    audio_codec: Optional[str] = typer.Option(
        None, "--audio-codec", help="Audio codec, e.g. aac."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show planned conversions without running."
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", "-f", help="Overwrite existing outputs."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show ffmpeg's own output."
    ),
) -> None:
    """Convert audio/video files between formats."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{message}")

    output_kwargs = build_output_kwargs(audio_bitrate, video_codec, audio_codec)
    try:
        succeeded, failed = convert(
            input_path,
            target_format,
            output=output,
            recursive=recursive,
            overwrite=overwrite,
            dry_run=dry_run,
            output_kwargs=output_kwargs,
            quiet=not verbose,
        )
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=2) from exc

    logger.info("Done: {} succeeded, {} failed", succeeded, failed)
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
