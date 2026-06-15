# /// script
# requires-python = ">=3.10"
# dependencies = ["ffmpeg-python>=0.2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Show key information about a video/audio file using ffprobe.

A friendlier replacement for::

    ffprobe -v error -show_format -show_streams input.mp4 2>&1 \\
      | grep -E "duration|codec_name|width|height|codec_type|r_frame_rate"

Accepts a local path or a remote URL (anything ffprobe understands: ``http(s)``,
``ftp``, ``rtmp``, ``rtsp``, ...). Two integrity checks are available:
``--check`` is a fast, remote-cheap structural check from the metadata, while
``--deep-check`` fully decodes the file to surface frame-level corruption that
the metadata-only read cannot see.

Run it self-contained with ``uv``::

    uv run scripts/probe_media.py input.mp4
    uv run scripts/probe_media.py https://example.com/video.mp4
    uv run scripts/probe_media.py input.mp4 --json
    uv run scripts/probe_media.py input.mp4 --check
    uv run scripts/probe_media.py input.mp4 --deep-check
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import ffmpeg
import typer
from loguru import logger

app = typer.Typer(
    add_completion=False,
    help="Show key information about a video/audio file using ffprobe.",
)


REMOTE_SCHEMES = frozenset(
    {"http", "https", "ftp", "ftps", "rtmp", "rtmps", "rtsp", "tcp", "udp", "srt"}
)


def is_remote_input(value: str) -> bool:
    """Report whether ``value`` is a remote URL rather than a local path.

    Args:
        value: The input source given on the command line.

    Returns:
        ``True`` if ``value`` starts with a known remote URL scheme that
        ffprobe can read directly; ``False`` for local paths (including
        Windows drive paths like ``C:\\clip.mp4``).

    Examples:
        >>> is_remote_input("https://example.com/v.mp4")
        True
        >>> is_remote_input("rtmp://host/live/stream")
        True
        >>> is_remote_input("/Users/me/clip.mp4")
        False
        >>> is_remote_input("clip.mp4")
        False
    """
    scheme = value.split("://", 1)[0].lower() if "://" in value else ""
    return scheme in REMOTE_SCHEMES


def parse_decode_errors(stderr: str) -> list[str]:
    """Split ffmpeg decode-pass stderr into a list of non-empty error lines.

    Args:
        stderr: The captured stderr from an ``ffmpeg -v error ... -f null -``
            integrity pass. Empty when the file decoded cleanly.

    Returns:
        One trimmed string per non-blank stderr line (empty list means no
        errors were reported).

    Examples:
        >>> parse_decode_errors("")
        []
        >>> parse_decode_errors("[h264] error\\n\\n  decode_slice_header error\\n")
        ['[h264] error', 'decode_slice_header error']
    """
    return [line.strip() for line in stderr.splitlines() if line.strip()]


def format_frame_rate(rate: Optional[str]) -> str:
    """Convert an ffprobe ``r_frame_rate`` fraction into a readable fps string.

    Args:
        rate: A fraction string like ``"30000/1001"`` or ``"30/1"``. ffprobe
            reports ``"0/0"`` when a stream has no meaningful frame rate.

    Returns:
        The frame rate rounded to two decimals with trailing zeros trimmed
        (e.g. ``"29.97"``, ``"30"``), or ``""`` when it is unknown or the
        denominator is zero.

    Examples:
        >>> format_frame_rate("30000/1001")
        '29.97'
        >>> format_frame_rate("30/1")
        '30'
        >>> format_frame_rate("0/0")
        ''
        >>> format_frame_rate(None)
        ''
    """
    if not rate or "/" not in rate:
        return ""
    num_str, den_str = rate.split("/", 1)
    try:
        num, den = float(num_str), float(den_str)
    except ValueError:
        return ""
    if den == 0:
        return ""
    fps = num / den
    return f"{fps:.2f}".rstrip("0").rstrip(".")


def format_duration(seconds: Optional[str]) -> str:
    """Convert a float-seconds string into an ``H:MM:SS`` duration.

    Args:
        seconds: Duration in seconds as reported by ffprobe (e.g. ``"123.45"``),
            or ``None`` when unavailable.

    Returns:
        An ``H:MM:SS`` string, or ``"unknown"`` when the value is missing or
        not parseable.

    Examples:
        >>> format_duration("123.45")
        '0:02:03'
        >>> format_duration("3661")
        '1:01:01'
        >>> format_duration(None)
        'unknown'
        >>> format_duration("nope")
        'unknown'
    """
    if seconds is None:
        return "unknown"
    try:
        total = int(float(seconds))
    except ValueError:
        return "unknown"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def extract_stream_info(stream: dict) -> dict:
    """Pluck the fields of interest from a single ffprobe stream entry.

    Args:
        stream: One element of ffprobe's ``streams`` list.

    Returns:
        A dict containing only the present keys among ``codec_type``,
        ``codec_name``, ``width``, ``height``, ``r_frame_rate`` and
        ``duration``.

    Examples:
        >>> info = extract_stream_info(
        ...     {"codec_type": "video", "codec_name": "h264",
        ...      "width": 1920, "height": 1080, "r_frame_rate": "30/1",
        ...      "profile": "High"}
        ... )
        >>> sorted(info.items())
        [('codec_name', 'h264'), ('codec_type', 'video'), ('height', 1080), ('r_frame_rate', '30/1'), ('width', 1920)]
    """
    keys = ("codec_type", "codec_name", "width", "height", "r_frame_rate", "duration")
    return {key: stream[key] for key in keys if key in stream}


def build_summary(probe: dict) -> str:
    """Build a human-readable summary from ffprobe's parsed output.

    Args:
        probe: The dict returned by :func:`ffmpeg.probe` (``format`` plus
            ``streams``).

    Returns:
        A multi-line report: a format/container line followed by one labeled
        block per stream.

    Examples:
        >>> probe = {
        ...     "format": {"format_name": "mov,mp4", "duration": "123.45"},
        ...     "streams": [
        ...         {"codec_type": "video", "codec_name": "h264",
        ...          "width": 1920, "height": 1080, "r_frame_rate": "30/1"},
        ...         {"codec_type": "audio", "codec_name": "aac",
        ...          "sample_rate": "48000", "channels": 2},
        ...     ],
        ... }
        >>> print(build_summary(probe))
        Container: mov,mp4
        Duration:  0:02:03
        Stream #0 (video): h264, 1920x1080, 30 fps
        Stream #1 (audio): aac, 48000 Hz, 2 ch
    """
    fmt = probe.get("format", {})
    lines = [f"Container: {fmt.get('format_name', 'unknown')}"]
    lines.append(f"Duration:  {format_duration(fmt.get('duration'))}")
    if fmt.get("bit_rate"):
        lines.append(f"Bitrate:   {fmt['bit_rate']} bps")
    if fmt.get("size"):
        lines.append(f"Size:      {fmt['size']} bytes")

    for index, stream in enumerate(probe.get("streams", [])):
        info = extract_stream_info(stream)
        codec_type = info.get("codec_type", "?")
        parts = [info.get("codec_name", "?")]
        if codec_type == "video":
            if "width" in info and "height" in info:
                parts.append(f"{info['width']}x{info['height']}")
            fps = format_frame_rate(info.get("r_frame_rate"))
            if fps:
                parts.append(f"{fps} fps")
        elif codec_type == "audio":
            if stream.get("sample_rate"):
                parts.append(f"{stream['sample_rate']} Hz")
            if stream.get("channels"):
                parts.append(f"{stream['channels']} ch")
        lines.append(f"Stream #{index} ({codec_type}): {', '.join(parts)}")

    return "\n".join(lines)


def find_structural_issues(probe: dict) -> list[str]:
    """Find structural problems in ffprobe output (a fast, metadata-only check).

    This reuses the data already returned by :func:`ffmpeg.probe`, so it adds no
    extra I/O and is cheap even for remote URLs. It validates that the container
    parsed into something sensible but, by design, cannot detect frame-level
    corruption — that requires a full decode (see :func:`run_integrity_check`).

    Args:
        probe: The dict returned by :func:`ffmpeg.probe`.

    Returns:
        A list of human-readable problem descriptions; empty when the file's
        structure looks intact.

    Examples:
        >>> ok = {
        ...     "format": {"duration": "12.0"},
        ...     "streams": [{"codec_type": "video", "width": 640, "height": 480}],
        ... }
        >>> find_structural_issues(ok)
        []
        >>> find_structural_issues({"format": {}, "streams": []})
        ['no media streams found', 'missing or zero duration']
        >>> find_structural_issues(
        ...     {"format": {"duration": "5"},
        ...      "streams": [{"codec_type": "video", "width": 640}]}
        ... )
        ['stream #0: missing video dimensions']
    """
    issues: list[str] = []
    streams = probe.get("streams", [])
    if not streams:
        issues.append("no media streams found")

    duration = probe.get("format", {}).get("duration")
    try:
        if duration is None or float(duration) <= 0:
            issues.append("missing or zero duration")
    except (TypeError, ValueError):
        issues.append("missing or zero duration")

    for index, stream in enumerate(streams):
        if stream.get("codec_type") == "video" and (
            "width" not in stream or "height" not in stream
        ):
            issues.append(f"stream #{index}: missing video dimensions")

    return issues


def probe_file(source: str) -> dict:
    """Run ffprobe on ``source`` and return its parsed output.

    Args:
        source: Media file path or remote URL to inspect.

    Returns:
        The dict returned by :func:`ffmpeg.probe`.

    Raises:
        ffmpeg.Error: If ffprobe fails (e.g. corrupt or invalid file).
    """
    return ffmpeg.probe(source)


def run_integrity_check(source: str) -> str:
    """Fully decode ``source`` and return any decode errors ffmpeg reports.

    Runs ``ffmpeg -v error -i <source> -f null -``, which reads and decodes the
    entire input (downloading it first for remote URLs) while discarding the
    output. Anything ffmpeg writes to stderr at the ``error`` log level signals
    corruption or a damaged stream.

    Args:
        source: Media file path or remote URL to verify.

    Returns:
        The captured stderr text (empty when the file decoded cleanly). Use
        :func:`parse_decode_errors` to turn it into a list of error lines.
    """
    stream = ffmpeg.input(source).output("pipe:", format="null").global_args(
        "-v", "error"
    )
    try:
        _, stderr = stream.run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as exc:
        # A non-zero exit (fatal error) still carries the diagnostics on stderr.
        stderr = getattr(exc, "stderr", b"") or b""
    return stderr.decode("utf-8", "replace")


@app.command()
def main(
    input_source: str = typer.Argument(
        ..., metavar="INPUT", help="Media file path or remote URL to inspect."
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emit the full raw ffprobe JSON instead of a summary.",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        "-c",
        help="Quick structural check from metadata (fast, remote-cheap).",
    ),
    deep_check: bool = typer.Option(
        False,
        "--deep-check",
        help="Fully decode to catch frame corruption (slow; downloads remote).",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show debug-level logging."
    ),
) -> None:
    """Show key information about a video/audio file."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{message}")

    if not is_remote_input(input_source) and not Path(input_source).is_file():
        logger.error("No such file: {}", input_source)
        raise typer.Exit(code=2)

    try:
        probe = probe_file(input_source)
    except ffmpeg.Error as exc:
        detail = (
            exc.stderr.decode("utf-8", "replace").strip()
            if getattr(exc, "stderr", None)
            else str(exc)
        )
        logger.error("Failed to probe {}: {}", input_source, detail)
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(json.dumps(probe, indent=2))
    else:
        typer.echo(build_summary(probe))

    # Deep supersedes quick: a full decode is a strict superset of the
    # structural check, so only run one.
    if deep_check:
        logger.info("Running deep check (decoding {})...", input_source)
        errors = parse_decode_errors(run_integrity_check(input_source))
        if errors:
            logger.error(
                "Deep check FAILED: {} decode error line(s) reported", len(errors)
            )
            for line in errors:
                logger.error("  {}", line)
            raise typer.Exit(code=1)
        logger.success("Deep check passed: no decode errors")
    elif check:
        issues = find_structural_issues(probe)
        if issues:
            logger.error("Quick check FAILED: {} issue(s) found", len(issues))
            for issue in issues:
                logger.error("  {}", issue)
            raise typer.Exit(code=1)
        logger.success(
            "Quick check passed: structure looks intact "
            "(use --deep-check to verify frame integrity)"
        )


if __name__ == "__main__":
    app()
