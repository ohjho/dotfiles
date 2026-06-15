"""Unit tests for :mod:`convert_media`.

Run with::

    uv run --with ffmpeg-python --with typer --with loguru --with pytest \\
        pytest scripts/ --doctest-modules -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

import convert_media as cm


def test_normalize_format_strips_dot_and_lowercases() -> None:
    assert cm.normalize_format(".MP4") == "mp4"
    assert cm.normalize_format("WAV") == "wav"


def test_build_output_path_swaps_extension() -> None:
    assert cm.build_output_path(Path("clip.mov"), "mp4") == Path("clip.mp4")


def test_build_output_path_into_directory(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = cm.build_output_path(Path("a.wav"), "mp3", out_dir)
    assert result == out_dir / "a.mp3"


def test_build_output_path_no_suffix_is_dir() -> None:
    result = cm.build_output_path(Path("x/a.wav"), "mp3", Path("out"))
    assert result == Path("out/a.mp3")


def test_build_output_path_explicit_file() -> None:
    result = cm.build_output_path(Path("a.wav"), "flac", Path("y/song.flac"))
    assert result == Path("y/song.flac")


def test_build_output_kwargs_omits_unset() -> None:
    assert cm.build_output_kwargs() == {}
    assert cm.build_output_kwargs(audio_bitrate="192k", audio_codec="aac") == {
        "audio_bitrate": "192k",
        "acodec": "aac",
    }
    assert cm.build_output_kwargs(video_codec="libx264") == {"vcodec": "libx264"}


def _touch(path: Path) -> Path:
    path.write_bytes(b"")
    return path


def test_iter_input_files_single_file(tmp_path: Path) -> None:
    f = _touch(tmp_path / "a.wav")
    assert cm.iter_input_files(str(f)) == [f]


def test_iter_input_files_directory_non_recursive(tmp_path: Path) -> None:
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "b.wav")
    sub = tmp_path / "sub"
    sub.mkdir()
    _touch(sub / "c.wav")
    files = cm.iter_input_files(str(tmp_path))
    assert [f.name for f in files] == ["a.wav", "b.wav"]


def test_iter_input_files_directory_recursive(tmp_path: Path) -> None:
    _touch(tmp_path / "a.wav")
    sub = tmp_path / "sub"
    sub.mkdir()
    _touch(sub / "c.wav")
    files = cm.iter_input_files(str(tmp_path), recursive=True)
    assert {f.name for f in files} == {"a.wav", "c.wav"}


def test_iter_input_files_glob(tmp_path: Path) -> None:
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "b.mp3")
    files = cm.iter_input_files(str(tmp_path / "*.wav"))
    assert [f.name for f in files] == ["a.wav"]


def test_iter_input_files_no_match_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cm.iter_input_files(str(tmp_path / "nope.xyz"))


def test_convert_calls_convert_fn_per_file(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a.wav")
    b = _touch(tmp_path / "b.wav")
    calls: list[tuple[Path, Path]] = []

    def fake(src, dst, **_kwargs):
        calls.append((src, dst))

    succeeded, failed = cm.convert(str(tmp_path), "mp3", convert_fn=fake)
    assert (succeeded, failed) == (2, 0)
    assert sorted(c[0].name for c in calls) == ["a.wav", "b.wav"]
    assert {c[1].suffix for c in calls} == {".mp3"}
    assert {a, b} == {c[0] for c in calls}


def test_convert_dry_run_makes_no_calls(tmp_path: Path) -> None:
    _touch(tmp_path / "a.wav")
    called = False

    def fake(*_args, **_kwargs):
        nonlocal called
        called = True

    succeeded, failed = cm.convert(str(tmp_path), "mp3", dry_run=True, convert_fn=fake)
    assert (succeeded, failed) == (1, 0)
    assert called is False


def test_convert_skips_existing_without_overwrite(tmp_path: Path) -> None:
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "a.mp3")  # pre-existing output
    calls: list[Path] = []

    def fake(src, dst, **_kwargs):
        calls.append(src)

    succeeded, failed = cm.convert(str(tmp_path), "mp3", convert_fn=fake)
    # a.mp3 already exists -> a.wav skipped; a.mp3 -> a.mp3 is identical -> skipped
    assert (succeeded, failed) == (0, 0)
    assert calls == []


def test_convert_overwrite_runs(tmp_path: Path) -> None:
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "a.mp3")
    calls: list[Path] = []

    def fake(src, dst, **_kwargs):
        calls.append(src)

    succeeded, failed = cm.convert(
        str(tmp_path / "a.wav"), "mp3", overwrite=True, convert_fn=fake
    )
    assert (succeeded, failed) == (1, 0)
    assert [c.name for c in calls] == ["a.wav"]


def test_convert_counts_failures(tmp_path: Path) -> None:
    import ffmpeg

    _touch(tmp_path / "a.wav")

    def boom(src, dst, **_kwargs):
        raise ffmpeg.Error("ffmpeg", b"", b"boom")

    succeeded, failed = cm.convert(str(tmp_path), "mp3", convert_fn=boom)
    assert (succeeded, failed) == (0, 1)
