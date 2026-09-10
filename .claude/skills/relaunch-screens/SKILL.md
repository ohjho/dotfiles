---
name: relaunch-screens
description: >-
  Recreate, inspect, snapshot, or stop the user's GNU screen sessions and the
  long-running processes inside them (streamlit apps, jupyter lab, ollama serve,
  project shells for claude) from the declarative manifest configs/screens.yaml.
  Use this whenever the user mentions rebooting or having rebooted, or says
  anything like "relaunch my screens", "bring back my screen sessions",
  "restart my servers after reboot", "is streamlit/jupyter/ollama running in
  screen", "what's running in my screens", "which screens are up", "snapshot
  my screens", "save my screen layout", "stop my screen sessions", or refers to
  one of the sessions by name (scripts, claude, jupyter, ollama, streamlit).
  Prefer it over hand-typing `screen -dmS` / `screen -X` commands, even when
  the user only asks about a single session.
---

# Relaunch Screens

Manage the user's GNU `screen` sessions from `configs/screens.yaml`, which lists
each session, its windows, their working directories, and the command to type
into each window.

## Command

Run from the repository root so the local manifest is picked up:

```bash
uv run scripts/screen_sessions.py <subcommand> [flags]
```

From anywhere else the script and manifest are both fetched from GitHub Pages:

```bash
uv run https://ohjho.github.io/dotfiles/scripts/screen_sessions.py <subcommand>
```

Subcommands:

- `status` — compare the manifest with `screen -ls` and the processes inside
  each session. Prints `[running]`, `[missing]`, or `[dead]` per session, then
  `#N OK` / `#N MISSING` per manifest window and `EXTRA` for unmanaged windows.
  Exits `1` when anything is missing.
- `launch` — create every manifest session that is not already running. A
  session that exists is **skipped wholesale**, even if some of its windows are
  missing; this keeps launch safe to rerun.
- `snapshot` — dump every live session and window (idle shells included) as
  manifest YAML to stdout, or to a file with `--output/-o`.
- `stop` — kill the selected sessions after a confirmation prompt.

Flags shared by all: `--only/-s NAME` (repeatable) to restrict to some sessions,
`--manifest/-m PATH_OR_URL`, `--verbose/-v`. `launch` and `stop` accept
`--dry-run/-n`; `launch` accepts `--settle SECONDS`; `stop` accepts `--yes/-y`.

## Workflow

1. **Start with `status`.** It is read-only and tells you what is actually
   missing. Relay the result plainly; do not assume a session is down because
   the user said so.
2. **Launch what is missing.** Run `launch` (with `-s` for specific sessions if
   the user named them). If the user seems unsure, or a directory in the
   manifest may have moved, run `launch --dry-run` first and show the printed
   `screen` commands before the real run.
3. **Confirm with `status` again.** Servers take a moment to boot, so a window
   whose command is `OK` may still be starting; that is fine. A `MISSING` line
   after a launch means the command was not typed or exited immediately: attach
   with `screen -r <name>` and look at the window.
4. **Snapshot only on request, and review before writing.** `snapshot` includes
   every idle shell and every unmanaged session, so pipe it to stdout, show the
   user how it differs from `configs/screens.yaml`, and only then write it with
   `-o configs/screens.yaml` if they want to keep it.

## What to know about the environment

- macOS ships GNU screen 4.00.03 (2006) with no `-Q` query flag, so the script
  discovers windows by walking the process tree (screen → login → zsh →
  command) with psutil. Window discovery therefore reflects what is running,
  not window titles; windows are addressed by index.
- Commands are typed into a fresh interactive zsh window so they see the user's
  normal PATH and the window drops back to a prompt if the command exits.
- `launch` never modifies a running session. To rebuild one, the user must
  `stop` it first, and that kills everything inside it.

## Guardrails

- Never run `stop` unless the user explicitly asked to stop or restart a
  session. Show the confirmation list (it marks the session you are currently
  inside) and never pass `--yes` for the session named in `$STY`.
- Do not hand-edit `configs/screens.yaml` to make `status` come out clean. If
  the manifest and reality disagree, tell the user and let them decide which is
  right.
- Exit codes: `0` ok; `1` something failed or is missing; `2` usage problem
  (bad manifest, unknown `--only` name, manifest unreachable). Report the
  script's stderr rather than retrying blindly.
