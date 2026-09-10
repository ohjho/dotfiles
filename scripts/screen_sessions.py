# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "psutil>=5.9", "typer>=0.12", "loguru>=0.7"]
# ///
"""Recreate, inspect, snapshot, or stop GNU ``screen`` sessions from a manifest.

After a reboot every long-lived ``screen`` session (streamlit dev servers,
jupyter labs, ``ollama serve``, project shells) is gone and has to be rebuilt by
hand. This script replaces that ritual with a declarative YAML manifest
(``configs/screens.yaml`` by default) listing each session, its windows, their
working directories, and the command to type into each one::

    uv run scripts/screen_sessions.py status      # manifest vs. what is running
    uv run scripts/screen_sessions.py launch -n   # dry run: print the screen commands
    uv run scripts/screen_sessions.py launch      # create whatever is missing
    uv run scripts/screen_sessions.py snapshot    # dump the live layout as YAML
    uv run scripts/screen_sessions.py stop -s streamlit

Design notes, all driven by macOS shipping GNU screen 4.00.03 (2006):

* There is no ``-Q`` (query) option, so windows cannot be listed via screen.
  ``status`` and ``snapshot`` instead walk the process tree under each screen
  PID with ``psutil``: ``SCREEN`` -> ``login`` (one per window on macOS) ->
  ``zsh`` -> the running command. On Linux the ``login`` layer is absent.
* ``screen -ls`` exits non-zero even on success, so only its stdout is parsed.
* ``screen -S NAME`` prefix-matches (``-S scri`` finds ``scripts``), so live
  sessions are always addressed as ``PID.NAME`` taken from ``screen -ls``.
* ``-p`` prefix-matches window titles too, so windows carry no titles and are
  addressed by index, which is deterministic in a session this script created.
* Commands are typed into an interactive login shell with ``-X stuff`` rather
  than run via ``zsh -c``: the shell has the user's full PATH (``uv``,
  ``ollama``, ``claude``), the command lands in history, and when it exits or
  crashes the window drops back to a prompt instead of closing. Text stuffed
  this way reaches the shell verbatim (no ``$``, ``^`` or backslash escaping).
  Input typed before zsh finishes starting is buffered by the tty and still
  arrives, but ``defaults.settle`` (1s) keeps a margin so the prompt is ready.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence

import psutil
import typer
import yaml
from loguru import logger

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Recreate, inspect, snapshot, or stop GNU screen sessions from a YAML manifest.",
)

DEFAULT_MANIFEST = "configs/screens.yaml"
REMOTE_MANIFEST_URL = "https://ohjho.github.io/dotfiles/configs/screens.yaml"
SESSION_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SCREEN_LS_RE = re.compile(r"^\s*(\d+)\.(\S+)\s+\((.*?)\)\s*$", re.MULTILINE)
STUFF_MAX_LEN = 400
DEFAULT_SETTLE = 1.0


class ManifestError(ValueError):
    """Raised when the manifest is malformed or a selection refers to an unknown session."""


# --------------------------------------------------------------------------- models


@dataclass(frozen=True)
class Window:
    """One window of a session: a working directory and an optional command.

    Attributes:
        cwd: Working directory, kept in its ``~`` form as written in the manifest.
        command: Shell command to type into the window, or ``None`` for an idle shell.
    """

    cwd: str = "~"
    command: Optional[str] = None


@dataclass(frozen=True)
class Session:
    """A named screen session and its ordered windows."""

    name: str
    windows: tuple[Window, ...]


@dataclass(frozen=True)
class Manifest:
    """The parsed manifest: sessions plus defaults."""

    sessions: tuple[Session, ...]
    settle: float = DEFAULT_SETTLE


@dataclass(frozen=True)
class LiveSession:
    """A session reported by ``screen -ls``."""

    name: str
    pid: int
    state: str

    @property
    def sock(self) -> str:
        """The unambiguous ``PID.NAME`` handle to pass to ``screen -S``."""
        return f"{self.pid}.{self.name}"

    @property
    def is_dead(self) -> bool:
        """Whether screen flagged the socket as dead (``Dead ???``)."""
        return self.state.lower().startswith("dead")


@dataclass(frozen=True)
class LiveWindow:
    """A window discovered by walking a screen session's process tree."""

    shell_pid: int
    cwd: Optional[str]
    command: Optional[str]


@dataclass(frozen=True)
class ScreenStep:
    """One ``screen`` invocation: the unit of side effect (and of dry-run output)."""

    argv: tuple[str, ...]
    cwd: Optional[str] = None
    sleep_after: float = 0.0


@dataclass
class SessionStatus:
    """Result of comparing one manifest session against the live state."""

    session: Session
    live: list[LiveSession] = field(default_factory=list)
    windows: list[LiveWindow] = field(default_factory=list)
    matches: list[Optional[LiveWindow]] = field(default_factory=list)
    extras: list[LiveWindow] = field(default_factory=list)

    @property
    def running(self) -> list[LiveSession]:
        """Live sessions with this name that are not dead."""
        return [s for s in self.live if not s.is_dead]

    @property
    def ok(self) -> bool:
        """``True`` when the session is up and every manifest window was found."""
        return bool(self.running) and all(m is not None for m in self.matches)


# --------------------------------------------------------------------------- pure helpers


def parse_screen_ls(text: str) -> list[LiveSession]:
    r"""Parse the stdout of ``screen -ls`` into live sessions.

    ``screen -ls`` prints one ``\t<pid>.<name>\t(<state>)`` line per socket
    between a header and a footer; on macOS the lines end in ``\r\n``. Its exit
    code is non-zero even on success, so callers should parse stdout and ignore
    the return code.

    Args:
        text: Raw ``screen -ls`` output.

    Returns:
        Sessions in the order listed. Empty when no sockets exist.

    Examples:
        >>> out = ("There are screens on:\r\n"
        ...        "\t36047.scripts\t(Detached)\r\n"
        ...        "\t5765.claude\t(Attached)\r\n"
        ...        "\t123.old\t(Dead ???)\r\n"
        ...        "\t77.multi\t(Multi, attached)\r\n"
        ...        "4 Sockets in /var/folders/x/T/.screen.\r\n")
        >>> [(s.name, s.pid, s.state) for s in parse_screen_ls(out)]
        [('scripts', 36047, 'Detached'), ('claude', 5765, 'Attached'), ('old', 123, 'Dead ???'), ('multi', 77, 'Multi, attached')]
        >>> parse_screen_ls(out)[2].is_dead, parse_screen_ls(out)[0].sock
        (True, '36047.scripts')
        >>> parse_screen_ls("There is a screen on:\n\t42.solo\t(Detached)\n1 Socket in /tmp/.screen.\n")
        [LiveSession(name='solo', pid=42, state='Detached')]
        >>> parse_screen_ls("No Sockets found in /var/folders/x/T/.screen.\n")
        []
    """
    return [
        LiveSession(name=name, pid=int(pid), state=state)
        for pid, name, state in SCREEN_LS_RE.findall(text)
    ]


def find_live(name: str, live: Iterable[LiveSession]) -> list[LiveSession]:
    """Return the live sessions whose name matches ``name`` exactly.

    ``screen -S`` itself prefix-matches, which is why this exists: ``claude``
    must not be confused with ``claude2``.

    Examples:
        >>> live = [LiveSession("claude", 1, "Attached"), LiveSession("claude2", 2, "Detached")]
        >>> [s.pid for s in find_live("claude", live)]
        [1]
        >>> find_live("cla", live)
        []
    """
    return [s for s in live if s.name == name]


def expand_path(path: str, home: Optional[str] = None) -> str:
    """Expand a leading ``~`` and normalize the path.

    Args:
        path: A path that may start with ``~``.
        home: Home directory to substitute; defaults to the real one. Injected
            so doctests are deterministic.

    Examples:
        >>> expand_path("~/Documents/Git//proj/", home="/Users/me")
        '/Users/me/Documents/Git/proj'
        >>> expand_path("~", home="/Users/me")
        '/Users/me'
        >>> expand_path("/opt/data", home="/Users/me")
        '/opt/data'
    """
    home = home or os.path.expanduser("~")
    if path == "~":
        expanded = home
    elif path.startswith("~/"):
        expanded = os.path.join(home, path[2:])
    else:
        expanded = path
    return os.path.normpath(expanded)


def contract_home(path: str, home: Optional[str] = None) -> str:
    """Replace a leading home directory with ``~`` (inverse of :func:`expand_path`).

    Examples:
        >>> contract_home("/Users/me/Documents/Git", home="/Users/me")
        '~/Documents/Git'
        >>> contract_home("/Users/me", home="/Users/me")
        '~'
        >>> contract_home("/Users/meow/x", home="/Users/me")
        '/Users/meow/x'
    """
    home = home or os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home.rstrip("/") + "/"):
        return "~/" + path[len(home.rstrip("/")) + 1 :]
    return path


def parse_manifest(data: Any) -> Manifest:
    """Validate a loaded YAML document and build a :class:`Manifest`.

    Rules: ``version`` must be ``1``; ``sessions`` is a non-empty list; each
    session ``name`` matches ``^[A-Za-z][A-Za-z0-9_-]*$`` (dots are forbidden
    because screen uses ``.`` to separate the PID from the name); each window is
    a mapping with optional ``cwd`` (defaults to ``~``; YAML reads a bare ``~``
    as null, which also means home) and optional string ``command``.

    Raises:
        ManifestError: On any schema violation, with a message naming the culprit.

    Examples:
        >>> m = parse_manifest({"version": 1, "sessions": [
        ...     {"name": "web", "windows": [{"cwd": "~/proj", "command": "uv run app.py"}, {"cwd": None}]}]})
        >>> m.settle, m.sessions[0].name, m.sessions[0].windows
        (1.0, 'web', (Window(cwd='~/proj', command='uv run app.py'), Window(cwd='~', command=None)))
        >>> parse_manifest({"version": 1, "defaults": {"settle": 0.5}, "sessions": [{"name": "a", "windows": [{}]}]}).settle
        0.5
        >>> def bad(data):
        ...     try:
        ...         parse_manifest(data)
        ...     except ManifestError as exc:
        ...         print(exc)
        >>> bad({"version": 2, "sessions": []})
        unsupported manifest version 2 (expected 1)
        >>> bad({"version": 1, "sessions": [{"name": "my.app", "windows": [{}]}]})
        invalid session name 'my.app': use letters, digits, '-' or '_' (no dots)
        >>> bad({"version": 1, "sessions": [{"name": "a", "windows": []}]})
        session 'a' has no windows
        >>> bad({"version": 1, "sessions": [{"name": "a", "windows": [{}]}, {"name": "a", "windows": [{}]}]})
        duplicate session name 'a'
    """
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a mapping at the top level")
    version = data.get("version")
    if version != 1:
        raise ManifestError(f"unsupported manifest version {version!r} (expected 1)")
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ManifestError("'defaults' must be a mapping")
    settle = defaults.get("settle", DEFAULT_SETTLE)
    if not isinstance(settle, (int, float)) or settle < 0:
        raise ManifestError(f"defaults.settle must be a non-negative number, got {settle!r}")

    raw_sessions = data.get("sessions")
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ManifestError("'sessions' must be a non-empty list")

    sessions: list[Session] = []
    seen: set[str] = set()
    for raw in raw_sessions:
        if not isinstance(raw, dict):
            raise ManifestError(f"each session must be a mapping, got {raw!r}")
        name = raw.get("name")
        if not isinstance(name, str) or not SESSION_NAME_RE.match(name):
            raise ManifestError(
                f"invalid session name {name!r}: use letters, digits, '-' or '_' (no dots)"
            )
        if name in seen:
            raise ManifestError(f"duplicate session name {name!r}")
        seen.add(name)
        raw_windows = raw.get("windows")
        if not isinstance(raw_windows, list) or not raw_windows:
            raise ManifestError(f"session {name!r} has no windows")
        windows: list[Window] = []
        for idx, raw_win in enumerate(raw_windows):
            if raw_win is None:
                raw_win = {}
            if not isinstance(raw_win, dict):
                raise ManifestError(f"session {name!r} window #{idx} must be a mapping")
            cwd = raw_win.get("cwd")
            if cwd is None:
                cwd = "~"
            if not isinstance(cwd, str) or not cwd.strip():
                raise ManifestError(f"session {name!r} window #{idx}: cwd must be a string")
            command = raw_win.get("command")
            if command is not None and (not isinstance(command, str) or not command.strip()):
                raise ManifestError(f"session {name!r} window #{idx}: command must be a string")
            windows.append(Window(cwd=cwd.strip(), command=command.strip() if command else None))
        sessions.append(Session(name=name, windows=tuple(windows)))
    return Manifest(sessions=tuple(sessions), settle=float(settle))


def select_sessions(manifest: Manifest, only: Optional[Sequence[str]]) -> list[Session]:
    """Pick the sessions named by ``--only``, or all of them when it is empty.

    Raises:
        ManifestError: If a requested name is not in the manifest.

    Examples:
        >>> m = Manifest((Session("a", (Window(),)), Session("b", (Window(),))))
        >>> [s.name for s in select_sessions(m, None)]
        ['a', 'b']
        >>> [s.name for s in select_sessions(m, ["b"])]
        ['b']
        >>> try:
        ...     select_sessions(m, ["zzz"])
        ... except ManifestError as exc:
        ...     print(exc)
        unknown session(s): zzz (manifest has: a, b)
    """
    if not only:
        return list(manifest.sessions)
    by_name = {s.name: s for s in manifest.sessions}
    unknown = [n for n in only if n not in by_name]
    if unknown:
        raise ManifestError(
            f"unknown session(s): {', '.join(unknown)} (manifest has: {', '.join(by_name)})"
        )
    return [by_name[n] for n in only]


def resolve_manifest_source(flag: Optional[str], local_exists: bool) -> str:
    """Decide where the manifest comes from.

    Order: an explicit ``--manifest`` value, then ``configs/screens.yaml`` in
    the current directory, then the copy published on GitHub Pages.

    Examples:
        >>> resolve_manifest_source("/tmp/x.yaml", local_exists=True)
        '/tmp/x.yaml'
        >>> resolve_manifest_source(None, local_exists=True)
        'configs/screens.yaml'
        >>> resolve_manifest_source(None, local_exists=False)
        'https://ohjho.github.io/dotfiles/configs/screens.yaml'
    """
    if flag:
        return flag
    return DEFAULT_MANIFEST if local_exists else REMOTE_MANIFEST_URL


def is_url(source: str) -> bool:
    """Whether a manifest source is fetched over HTTP(S) rather than read from disk.

    Examples:
        >>> is_url("https://example.com/a.yaml"), is_url("configs/screens.yaml")
        (True, False)
    """
    return source.startswith(("http://", "https://"))


def normalize_command(command: str) -> str:
    """Canonicalize whitespace/quoting so typed and observed commands compare equal.

    Examples:
        >>> normalize_command("uv  run   app.py  --port 8501")
        'uv run app.py --port 8501'
        >>> normalize_command('python "my script.py"')
        "python 'my script.py'"
    """
    try:
        return shlex.join(shlex.split(command))
    except ValueError:
        return " ".join(command.split())


def plan_create(session: Session, home: Optional[str] = None) -> ScreenStep:
    """The ``screen -dmS`` step that creates a detached session with window 0.

    ``-dmS`` inherits the invoking process's cwd for its first shell, so the
    step carries the first window's directory as ``cwd``.

    Examples:
        >>> s = Session("web", (Window("~/proj", "uv run app.py"), Window("~/other")))
        >>> plan_create(s, home="/Users/me")
        ScreenStep(argv=('screen', '-dmS', 'web'), cwd='/Users/me/proj', sleep_after=0.0)
    """
    return ScreenStep(argv=("screen", "-dmS", session.name), cwd=expand_path(session.windows[0].cwd, home))


def plan_windows(
    sock: str, windows: Sequence[Window], settle: float, home: Optional[str] = None
) -> list[ScreenStep]:
    r"""The steps that populate an already-created session addressed by ``sock``.

    Window 0 already exists (from :func:`plan_create`), so it only receives its
    command. Each further window is created with ``chdir`` + ``screen`` and then
    receives its command via ``-p <index> -X stuff``. A trailing bare ``chdir``
    resets the session's default directory to ``$HOME``. Idle windows get no
    ``stuff`` at all, so their scrollback stays clean.

    The command is passed verbatim plus a newline: when ``stuff`` arrives via
    ``-X`` (already split into argv) screen does not apply its ``.screenrc``
    escapes, so ``$VAR``, ``^X`` and ``\`` reach the shell exactly as written
    (verified against screen 4.00.03 on macOS).

    Args:
        sock: ``PID.NAME`` handle (or the bare name in a dry run).
        windows: The session's windows in order.
        settle: Seconds to wait after creating a window before typing into it,
            because input stuffed before zsh finishes starting can be lost.
        home: Home directory for ``~`` expansion (doctest injection).

    Examples:
        >>> w = (Window("~/proj", "uv run app.py"), Window("~/other"), Window("~", "ollama serve"))
        >>> for step in plan_windows("42.web", w, settle=0.5, home="/Users/me"):
        ...     print(shlex.join(step.argv).replace("\n", "\\n"), step.sleep_after)
        screen -S 42.web -p 0 -X stuff 'uv run app.py\n' 0.0
        screen -S 42.web -X chdir /Users/me/other 0.0
        screen -S 42.web -X screen 0.5
        screen -S 42.web -X chdir /Users/me 0.0
        screen -S 42.web -X screen 0.5
        screen -S 42.web -p 2 -X stuff 'ollama serve\n' 0.0
        screen -S 42.web -X chdir 0.0
    """
    steps: list[ScreenStep] = []
    base = ("screen", "-S", sock)
    for index, window in enumerate(windows):
        if index > 0:
            steps.append(ScreenStep(argv=base + ("-X", "chdir", expand_path(window.cwd, home))))
            steps.append(ScreenStep(argv=base + ("-X", "screen"), sleep_after=settle))
        if window.command:
            steps.append(ScreenStep(argv=base + ("-p", str(index), "-X", "stuff", window.command + "\n")))
    steps.append(ScreenStep(argv=base + ("-X", "chdir")))
    return steps


def plan_stop(live: LiveSession) -> ScreenStep:
    """The ``quit`` step that kills a live session (all its windows).

    Examples:
        >>> plan_stop(LiveSession("web", 42, "Detached")).argv
        ('screen', '-S', '42.web', '-X', 'quit')
    """
    return ScreenStep(argv=("screen", "-S", live.sock, "-X", "quit"))


def match_windows(
    wanted: Sequence[Window], live: Sequence[LiveWindow], home: Optional[str] = None
) -> tuple[list[Optional[LiveWindow]], list[LiveWindow]]:
    """Pair manifest windows with live windows, one-to-one.

    A manifest window with a command matches a live window in the same
    directory running the same (normalized) command. A command-less manifest
    window matches any live window in that directory, preferring idle shells,
    because the user may well have started something by hand in it (for
    example ``claude``). Whatever is left over on the live side is "extra".

    Returns:
        ``(matches, extras)`` where ``matches[i]`` is the live window paired
        with ``wanted[i]`` or ``None`` if missing.

    Examples:
        >>> wanted = [Window("~/a", "uv run app.py"), Window("~/b"), Window("~/c", "ollama serve")]
        >>> live = [LiveWindow(1, "/Users/me/b", "claude"), LiveWindow(2, "/Users/me/a", "uv  run app.py"),
        ...         LiveWindow(3, "/Users/me/zzz", None)]
        >>> matches, extras = match_windows(wanted, live, home="/Users/me")
        >>> [m.shell_pid if m else None for m in matches], [e.shell_pid for e in extras]
        ([2, 1, None], [3])
        >>> live2 = [LiveWindow(1, "/Users/me/b", "claude"), LiveWindow(4, "/Users/me/b", None)]
        >>> match_windows([Window("~/b")], live2, home="/Users/me")[0][0].shell_pid
        4
    """
    remaining = list(range(len(live)))
    matches: list[Optional[LiveWindow]] = [None] * len(wanted)

    def same_dir(window: Window, candidate: LiveWindow) -> bool:
        return candidate.cwd is not None and os.path.normpath(candidate.cwd) == expand_path(window.cwd, home)

    for i, window in enumerate(wanted):
        if window.command is None:
            continue
        target = normalize_command(window.command)
        for j in remaining:
            candidate = live[j]
            if same_dir(window, candidate) and candidate.command and normalize_command(candidate.command) == target:
                matches[i] = candidate
                remaining.remove(j)
                break

    for i, window in enumerate(wanted):
        if window.command is not None:
            continue
        candidates = sorted(
            (j for j in remaining if same_dir(window, live[j])),
            key=lambda j: live[j].command is not None,
        )
        if candidates:
            matches[i] = live[candidates[0]]
            remaining.remove(candidates[0])

    return matches, [live[j] for j in remaining]


def windows_to_manifest(
    sessions: Sequence[tuple[LiveSession, Sequence[LiveWindow]]],
    settle: float = DEFAULT_SETTLE,
    home: Optional[str] = None,
) -> dict:
    """Render live sessions as a manifest-shaped dict ready for ``yaml.safe_dump``.

    Examples:
        >>> live = [(LiveSession("web", 42, "Detached"),
        ...          [LiveWindow(1, "/Users/me/proj", "uv run app.py"), LiveWindow(2, "/Users/me", None)])]
        >>> windows_to_manifest(live, home="/Users/me")
        {'version': 1, 'defaults': {'settle': 1.0}, 'sessions': [{'name': 'web', 'windows': [{'cwd': '~/proj', 'command': 'uv run app.py'}, {'cwd': '~'}]}]}
    """
    rendered = []
    for session, windows in sessions:
        items: list[dict] = []
        for window in windows:
            item: dict = {"cwd": contract_home(window.cwd, home) if window.cwd else "~"}
            if window.command:
                item["command"] = window.command
            items.append(item)
        rendered.append({"name": session.name, "windows": items})
    return {"version": 1, "defaults": {"settle": settle}, "sessions": rendered}


def render_status(status: SessionStatus, home: Optional[str] = None) -> list[str]:
    """Format one session's status as printable lines.

    Examples:
        >>> s = Session("web", (Window("~/a", "uv run app.py"), Window("~/b")))
        >>> st = SessionStatus(s, live=[LiveSession("web", 42, "Detached")])
        >>> st.matches = [LiveWindow(1, "/Users/me/a", "uv run app.py"), None]
        >>> st.extras = [LiveWindow(9, "/Users/me/zzz", None)]
        >>> for line in render_status(st, home="/Users/me"): print(line)
        [running] web  pid 42  Detached
          #0 OK       ~/a  uv run app.py
          #1 MISSING  ~/b  (shell)
          EXTRA       ~/zzz  (idle shell)
        >>> render_status(SessionStatus(s))
        ['[missing] web']
        >>> render_status(SessionStatus(s, live=[LiveSession("web", 7, "Dead ???")]))
        ['[dead]    web  pid 7  Dead ???  (run `screen -wipe` to clean up)']
    """
    if not status.live:
        return [f"[missing] {status.session.name}"]
    if not status.running:
        dead = ", ".join(f"pid {s.pid}  {s.state}" for s in status.live)
        return [f"[dead]    {status.session.name}  {dead}  (run `screen -wipe` to clean up)"]

    lines = []
    for live in status.running:
        lines.append(f"[running] {status.session.name}  pid {live.pid}  {live.state}")
    if len(status.running) > 1:
        lines.append("  WARNING  more than one live session has this name")
    for index, (window, match) in enumerate(zip(status.session.windows, status.matches)):
        mark = "OK     " if match is not None else "MISSING"
        what = window.command or "(shell)"
        if match is not None and window.command is None and match.command:
            what = f"(shell, running: {match.command})"
        lines.append(f"  #{index} {mark}  {window.cwd}  {what}")
    for extra in status.extras:
        cwd = contract_home(extra.cwd, home) if extra.cwd else "?"
        lines.append(f"  EXTRA       {cwd}  {extra.command or '(idle shell)'}")
    return lines


# --------------------------------------------------------------------------- side effects


def run_screen(step: ScreenStep) -> subprocess.CompletedProcess:
    """Run one screen step (no shell involved) and honour its settle delay."""
    logger.debug("$ {}{}", shlex.join(step.argv), f"  (cwd={step.cwd})" if step.cwd else "")
    result = subprocess.run(list(step.argv), cwd=step.cwd, capture_output=True, text=True, check=False)
    if step.sleep_after:
        time.sleep(step.sleep_after)
    return result


def execute(
    steps: Iterable[ScreenStep],
    runner: Callable[[ScreenStep], subprocess.CompletedProcess] = run_screen,
    dry_run: bool = False,
) -> bool:
    """Run (or print, in a dry run) each step; return ``False`` on the first failure."""
    for step in steps:
        if dry_run:
            suffix = f"    # cwd={step.cwd}" if step.cwd else ""
            typer.echo(shlex.join(step.argv).replace("\n", "\\n") + suffix)
            continue
        result = runner(step)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            logger.error("screen failed ({}): {}{}", result.returncode, shlex.join(step.argv), f"\n  {detail}" if detail else "")
            return False
    return True


def list_sessions() -> list[LiveSession]:
    """Run ``screen -ls`` and parse it (its exit code is meaningless)."""
    try:
        result = subprocess.run(["screen", "-ls"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        logger.error("`screen` is not installed or not on PATH")
        raise typer.Exit(code=1)
    return parse_screen_ls(result.stdout)


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        return fn()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return default


def walk_session(pid: int) -> list[LiveWindow]:
    """Discover a session's windows by walking its process tree with psutil.

    Each window is a child of the ``SCREEN`` process: on macOS a setuid
    ``login`` whose child is the shell, on Linux the shell itself. The shell's
    cwd is the window's directory and its first non-zombie child is the
    command typed into it. ``login`` refuses ``cwd()``/``cmdline()`` to
    non-root callers, which is why the shell is inspected instead.
    """
    try:
        screen_proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []
    windows: list[LiveWindow] = []
    for child in sorted(screen_proc.children(), key=lambda p: _safe(p.create_time, 0.0)):
        shell = child
        if _safe(child.name, "") == "login":
            grandchildren = _safe(child.children, [])
            if not grandchildren:
                continue
            shell = grandchildren[0]
        cwd = _safe(shell.cwd)
        commands = [c for c in _safe(shell.children, []) if _safe(c.status, "") != psutil.STATUS_ZOMBIE]
        command = None
        if commands:
            argv = _safe(commands[0].cmdline, [])
            command = shlex.join(argv) if argv else _safe(commands[0].name)
            if len(commands) > 1:
                logger.debug("window shell {} has {} children; using the first", shell.pid, len(commands))
        windows.append(LiveWindow(shell_pid=shell.pid, cwd=cwd, command=command))
    return windows


def load_manifest_text(source: str) -> str:
    """Read the manifest from a local path or fetch it over HTTP(S)."""
    if is_url(source):
        logger.debug("fetching manifest from {}", source)
        with urllib.request.urlopen(source, timeout=10) as response:
            return response.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


def load_manifest(flag: Optional[str]) -> Manifest:
    """Resolve, load, and validate the manifest; exit 2 on any problem."""
    source = resolve_manifest_source(flag, local_exists=Path(DEFAULT_MANIFEST).is_file())
    logger.debug("manifest: {}", source)
    try:
        text = load_manifest_text(source)
    except (OSError, urllib.error.URLError) as exc:
        logger.error("cannot read manifest {}: {} (pass --manifest/-m to point at a copy)", source, exc)
        raise typer.Exit(code=2) from exc
    try:
        return parse_manifest(yaml.safe_load(text))
    except (yaml.YAMLError, ManifestError) as exc:
        logger.error("invalid manifest {}: {}", source, exc)
        raise typer.Exit(code=2) from exc


def gather_status(session: Session, live: Sequence[LiveSession]) -> SessionStatus:
    """Compare one manifest session with the live sessions and their windows."""
    status = SessionStatus(session=session, live=find_live(session.name, live))
    for running in status.running:
        status.windows.extend(walk_session(running.pid))
    status.matches, status.extras = match_windows(session.windows, status.windows)
    return status


def launch_session(session: Session, live: Sequence[LiveSession], settle: float, dry_run: bool) -> bool:
    """Create one session from the manifest unless it is already running.

    Returns ``True`` when the session ended up fully created (or was skipped
    because it already runs), ``False`` when anything was skipped or failed.
    """
    existing = find_live(session.name, live)
    running = [s for s in existing if not s.is_dead]
    if running:
        states = ", ".join(f"pid {s.pid} {s.state}" for s in running)
        logger.info("skip  {}: already running ({})", session.name, states)
        return True
    for dead in existing:
        logger.warning("{}: stale socket {} ({}); run `screen -wipe` to clean it up", session.name, dead.sock, dead.state)

    windows: list[Window] = []
    ok = True
    for index, window in enumerate(session.windows):
        if os.path.isdir(expand_path(window.cwd)):
            windows.append(window)
        else:
            logger.warning("{}: window #{} skipped, directory not found: {}", session.name, index, window.cwd)
            ok = False
        if window.command and len(window.command) > STUFF_MAX_LEN:
            logger.warning("{}: window #{} command is very long ({} chars); screen's stuff buffer may truncate it", session.name, index, len(window.command))
    if not windows:
        logger.error("{}: no usable windows, session not created", session.name)
        return False
    trimmed = Session(name=session.name, windows=tuple(windows))

    create = ScreenStep(argv=plan_create(trimmed).argv, cwd=plan_create(trimmed).cwd, sleep_after=settle)
    if dry_run:
        typer.echo(f"# {session.name}: {len(windows)} window(s)")
        execute([create] + plan_windows(session.name, windows, settle), dry_run=True)
        return ok

    before = {s.pid for s in live}
    if not execute([create]):
        return False
    created = [s for s in find_live(session.name, list_sessions()) if s.pid not in before and not s.is_dead]
    if not created:
        logger.error("{}: `screen -dmS` returned but no new session appeared in `screen -ls`", session.name)
        return False
    sock = created[0].sock
    if not execute(plan_windows(sock, windows, settle)):
        logger.error("{}: session {} was created but not fully populated", session.name, sock)
        return False
    logger.info("start {}: {} window(s) as {}", session.name, len(windows), sock)
    return ok


# --------------------------------------------------------------------------- CLI


def _manifest_option() -> Any:
    return typer.Option(
        None, "--manifest", "-m",
        help=f"Manifest path or URL (default: ./{DEFAULT_MANIFEST}, else {REMOTE_MANIFEST_URL}).",
    )


def _only_option() -> Any:
    return typer.Option(None, "--only", "-s", help="Restrict to these session names (repeatable).")


def _verbose_option() -> Any:
    return typer.Option(False, "--verbose", "-v", help="Debug logging (shows every screen command).")


def _configure_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{message}")
    if os.environ.get("STY"):
        logger.debug("running inside screen session {}", os.environ["STY"])


def _select(manifest: Manifest, only: Optional[List[str]]) -> list[Session]:
    try:
        return select_sessions(manifest, only)
    except ManifestError as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2) from exc


@app.command()
def launch(
    manifest_path: Optional[str] = _manifest_option(),
    only: Optional[List[str]] = _only_option(),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Print the screen commands without running them."),
    settle: Optional[float] = typer.Option(None, "--settle", help="Seconds to wait after creating a window before typing into it (overrides the manifest)."),
    verbose: bool = _verbose_option(),
) -> None:
    """Create every manifest session that is not already running."""
    _configure_logging(verbose)
    manifest = load_manifest(manifest_path)
    sessions = _select(manifest, only)
    delay = manifest.settle if settle is None else settle
    live = list_sessions()
    failures = 0
    for session in sessions:
        if not launch_session(session, live, delay, dry_run):
            failures += 1
    if failures:
        logger.warning("{} session(s) incomplete", failures)
        raise typer.Exit(code=1)


@app.command()
def status(
    manifest_path: Optional[str] = _manifest_option(),
    only: Optional[List[str]] = _only_option(),
    verbose: bool = _verbose_option(),
) -> None:
    """Compare the manifest with the live screen sessions and their windows."""
    _configure_logging(verbose)
    manifest = load_manifest(manifest_path)
    sessions = _select(manifest, only)
    live = list_sessions()
    problems = 0
    for session in sessions:
        result = gather_status(session, live)
        for line in render_status(result):
            typer.echo(line)
        if not result.ok:
            problems += 1
    unmanaged = sorted({s.name for s in live} - {s.name for s in manifest.sessions})
    if unmanaged and not only:
        typer.echo(f"[unmanaged] {', '.join(unmanaged)}  (live but not in the manifest)")
    if problems:
        raise typer.Exit(code=1)


@app.command()
def snapshot(
    only: Optional[List[str]] = _only_option(),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write YAML here instead of stdout."),
    verbose: bool = _verbose_option(),
) -> None:
    """Dump every live session and window as manifest YAML (prune by hand before committing)."""
    _configure_logging(verbose)
    live = [s for s in list_sessions() if not s.is_dead]
    if only:
        live = [s for s in live if s.name in set(only)]
    if not live:
        logger.error("no live screen sessions to snapshot")
        raise typer.Exit(code=1)
    collected = [(session, walk_session(session.pid)) for session in live]
    text = yaml.safe_dump(windows_to_manifest(collected), sort_keys=False, width=200)
    if output:
        output.write_text(text, encoding="utf-8")
        logger.info("wrote {} session(s) to {}", len(collected), output)
    else:
        typer.echo(text, nl=False)


@app.command()
def stop(
    manifest_path: Optional[str] = _manifest_option(),
    only: Optional[List[str]] = _only_option(),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Print the screen commands without running them."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation."),
    verbose: bool = _verbose_option(),
) -> None:
    """Kill the selected manifest sessions (every window in them)."""
    _configure_logging(verbose)
    manifest = load_manifest(manifest_path)
    sessions = _select(manifest, only)
    live = list_sessions()
    targets: list[LiveSession] = []
    for session in sessions:
        found = [s for s in find_live(session.name, live) if not s.is_dead]
        if not found:
            logger.info("skip  {}: not running", session.name)
        elif len(found) > 1:
            logger.error("{}: {} live sessions share this name; refusing to guess", session.name, len(found))
            raise typer.Exit(code=1)
        else:
            targets.extend(found)
    if not targets:
        return
    current = os.environ.get("STY")
    targets.sort(key=lambda s: s.sock == current)
    for target in targets:
        note = "  <- this is the session you are in!" if target.sock == current else ""
        typer.echo(f"{target.sock}  ({target.state}){note}", err=True)
    if dry_run:
        execute([plan_stop(t) for t in targets], dry_run=True)
        return
    if not yes and not typer.confirm(f"Stop {len(targets)} session(s)?", default=False):
        raise typer.Exit(code=1)
    failures = 0
    for target in targets:
        if execute([plan_stop(target)]):
            logger.info("stopped {}", target.sock)
        else:
            failures += 1
    if failures:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
