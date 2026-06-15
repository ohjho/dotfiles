# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This is a **dotfiles repository** in its initial state. As of this writing it contains only `README.md`, `LICENSE`, and a `.gitignore`. There is no source code, build system, test suite, or tooling configuration committed yet.

Per `README.md`, the repo is intended to hold **configs, scripts, and tools** — i.e. personal environment configuration and helper scripts, not a deployable application.

## Conventions to expect

- The `.gitignore` is the standard GitHub Python template (covers `__pycache__/`, virtualenvs, `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`, build artifacts, etc.). This signals the toolchain to use when adding scripts here: **Python**, with `ruff`, `pytest`, and `mypy` as the implied lint/test/type tools.
- There are no Cursor rules, Copilot instructions, or other agent config files in the repo.

## Working in this repo

Because the repo is essentially empty, there are no project-specific build/lint/test commands to document yet. When the user adds content:

- If they add Python scripts, prefer `ruff` for linting/formatting, `pytest` for tests, and `mypy` for type checking (consistent with the `.gitignore`).
- For a dotfiles repo, files often need to be **symlinked into `$HOME`** (e.g. `ln -s "$PWD/<file>" ~/.<file>`) rather than copied. Confirm the user's preferred install/link mechanism before scripting it, and update this file once that mechanism exists.

## Scripts

- **`scripts/convert_media.py`** — Audio/video format converter built on `ffmpeg-python` (requires `ffmpeg` on `PATH`). Uses `typer` for the CLI and `loguru` for logging, with PEP 723 inline deps so it runs self-contained: `uv run scripts/convert_media.py INPUT --to FORMAT`. Accepts a single file, a directory, or a glob; `--output` is treated as a directory when it has no extension and a target file otherwise. Flags: `--to/-t` (required), `--output/-o`, `--recursive/-r`, `--audio-bitrate`, `--video-codec`, `--audio-codec`, `--dry-run/-n`, `--overwrite/-f`, `--verbose/-v`. Exit codes: `0` ok, `1` if any file failed, `2` if no inputs matched. Pure helpers (`normalize_format`, `build_output_path`, `build_output_kwargs`) carry doctests; per-file ffmpeg work is isolated in `convert_one` so `convert` is testable via an injected `convert_fn`.
  - Tests: `uv run --with ffmpeg-python --with typer --with loguru --with pytest pytest scripts/ --doctest-modules` (covers unit tests + doctests, no real ffmpeg needed).

# Guidelines
- update CLAUDE.md for each new features
- keep code modular to ensure ease in future refactoring
- use python and typer and loguru when writing scripts and make sure that it can be `uv run`
- use Google-style docstring for new functions and add a doctest compatible unit test if possible
