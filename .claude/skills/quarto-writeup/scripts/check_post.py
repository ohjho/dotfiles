#!/usr/bin/env python3
"""Lint a Quarto ``.qmd`` post without rendering it.

Checks the things that break silently at render time or after the post
leaves the author's machine: missing front matter keys, ``@refs`` with no
matching ``{#id}``, duplicate ids, pipe tables without a captioned id, code
annotations (``# <1>``) without their numbered list, media that points at a
local or home-directory path, and remote URLs that do not answer 2xx/3xx.

Standard library only, so it runs anywhere Python 3.8+ does.

Usage:
    python3 check_post.py POST.qmd [--offline] [--json] [--timeout SECONDS]

Exit status is 1 when any ERROR finding exists, else 0. WARN findings never
fail the run; they are things to look at, not defects.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

REQUIRED_FRONT_MATTER = ("title", "date", "author", "categories")
LOCAL_PATH_PREFIXES = ("/Users/", "/home/", "~/", "file:", "C:\\", "/tmp/")
MEDIA_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".mov", ".webm")
USER_AGENT = "quarto-writeup-check/1.0"


@dataclass
class Finding:
    """One lint result.

    Attributes:
        level: ``"ERROR"`` (fails the run) or ``"WARN"``.
        line: 1-based line number in the post, 0 when not line-specific.
        message: Human-readable description.
    """

    level: str
    line: int
    message: str


def split_front_matter(text: str) -> Tuple[Optional[str], str, int]:
    """Split a ``.qmd`` into its YAML front matter and body.

    Args:
        text: Full file contents.

    Returns:
        ``(front_matter, body, body_offset)`` where ``front_matter`` is the
        YAML text without the ``---`` fences (``None`` when absent) and
        ``body_offset`` is the number of lines the body starts after.

    Example:
        >>> fm, body, off = split_front_matter("---\\ntitle: x\\n---\\n# Hi\\n")
        >>> fm, body, off
        ('title: x', '# Hi\\n', 3)
        >>> split_front_matter("# no front matter\\n")[0] is None
        True
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[1:i]).rstrip("\n"), "".join(lines[i + 1 :]), i + 1
    return None, text, 0


def front_matter_keys(front_matter: str) -> Set[str]:
    """Return the top-level keys of a YAML front-matter block.

    A naive line scan is enough here: top-level keys are unindented
    ``key:`` lines. Nested keys are indented and skipped.

    Example:
        >>> sorted(front_matter_keys("title: x\\nformat:\\n    html:\\n        toc: true\\ndate: 1/1/2026"))
        ['date', 'format', 'title']
    """
    return {
        m.group(1)
        for line in front_matter.splitlines()
        if (m := re.match(r"^([A-Za-z_][\w-]*)\s*:", line))
    }


def strip_code_fences(body: str) -> Tuple[str, List[Tuple[int, int, str, List[str]]]]:
    """Blank out fenced code blocks, returning the fences separately.

    Fenced blocks are excluded from reference, id, table and URL scanning
    (a URL in a command is not a link) but are returned so the annotation
    check can inspect them. Line numbering of the returned text is preserved.

    Args:
        body: Post body (after front matter).

    Returns:
        ``(text_without_fences, fences)`` where each fence is
        ``(start_line, end_line, info_string, code_lines)`` with 1-based
        line numbers relative to ``body``.

    Example:
        >>> txt, fences = strip_code_fences("a\\n```bash\\nls # <1>\\n```\\nb\\n")
        >>> txt.splitlines()
        ['a', '', '', '', 'b']
        >>> fences
        [(2, 4, 'bash', ['ls # <1>'])]
    """
    out: List[str] = []
    fences: List[Tuple[int, int, str, List[str]]] = []
    in_fence = False
    fence_marker = ""
    start = 0
    info = ""
    code: List[str] = []
    for i, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            start, info, code = i, stripped[3:].strip(), []
            out.append("")
        elif in_fence and stripped.startswith(fence_marker) and stripped.strip(fence_marker) == "":
            in_fence = False
            fences.append((start, i, info, code))
            out.append("")
        elif in_fence:
            code.append(line)
            out.append("")
        else:
            out.append(line)
    return "\n".join(out), fences


def find_ids(text: str) -> Dict[str, List[int]]:
    """Collect every ``{#id}`` declaration (divs, tables, figures, headings).

    Mermaid ``%%| label: fig-x`` lines are not visible here because they
    live inside fences; they are collected by :func:`find_fence_labels`.

    Example:
        >>> find_ids("::: {#card-a .column-page}\\n: cap {#tbl-x}\\n# H {#sec-h}")
        {'card-a': [1], 'tbl-x': [2], 'sec-h': [3]}
    """
    ids: Dict[str, List[int]] = {}
    for n, line in enumerate(text.splitlines(), start=1):
        for m in re.finditer(r"\{#([A-Za-z][\w-]*)", line):
            ids.setdefault(m.group(1), []).append(n)
    return ids


def find_fence_labels(fences: Iterable[Tuple[int, int, str, List[str]]]) -> Dict[str, List[int]]:
    """Collect ``%%| label:`` / ``#| label:`` ids declared inside code fences.

    Example:
        >>> find_fence_labels([(1, 4, "{mermaid}", ["%%| label: fig-flow", "flowchart LR"])])
        {'fig-flow': [2]}
    """
    labels: Dict[str, List[int]] = {}
    for start, _end, _info, code in fences:
        for j, line in enumerate(code, start=1):
            m = re.match(r"^\s*(?:%%\||#\|)\s*label:\s*([A-Za-z][\w-]*)", line)
            if m:
                labels.setdefault(m.group(1), []).append(start + j)
    return labels


def find_refs(text: str) -> List[Tuple[int, str]]:
    """Find cross-references like ``@tbl-models`` or ``@card-split``.

    A reference needs a prefix, a hyphen and a slug, and must not be glued
    to a preceding word character, so e-mail addresses are ignored.

    Example:
        >>> find_refs("see @tbl-models and (@card-a); mail john@greenfly.com")
        [(1, 'tbl-models'), (1, 'card-a')]
    """
    refs: List[Tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        for m in re.finditer(r"(?<![\w.])@([A-Za-z]+-[\w-]*\w)", line):
            refs.append((n, m.group(1)))
    return refs


def find_tables_without_caption(text: str) -> List[int]:
    """Return start lines of pipe tables not followed by ``: caption {#tbl-…}``.

    Example:
        >>> body = "| a | b |\\n|---|---|\\n| 1 | 2 |\\n\\n: cap {#tbl-ok}\\n\\n| c |\\n|---|\\n| 3 |\\n\\ntext"
        >>> find_tables_without_caption(body)
        [7]
    """
    lines = text.splitlines()
    missing: List[int] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            start = i
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                i += 1
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            nxt = lines[j] if j < len(lines) else ""
            if not (nxt.startswith(":") and "{#tbl-" in nxt):
                missing.append(start + 1)
        else:
            i += 1
    return missing


def check_annotations(
    body_lines: Sequence[str], fences: Iterable[Tuple[int, int, str, List[str]]]
) -> List[Finding]:
    """Verify ``# <n>`` code annotations are contiguous and have a numbered list.

    Quarto renders an annotation only when a ``1.``-style list item exists
    for it right after the fence; a missing or mis-numbered item shows up as
    a bare ``# <3>`` in the rendered code.

    Example:
        >>> body = "```bash\\nls # <1>\\ncd x # <2>\\n```\\n1. list\\n2. change\\n"
        >>> check_annotations(body.splitlines(), strip_code_fences(body)[1])
        []
        >>> body = "```bash\\nls # <1>\\ncd x # <3>\\n```\\n1. list\\n"
        >>> [f.message for f in check_annotations(body.splitlines(), strip_code_fences(body)[1])]
        ['code annotations are not contiguous from 1: [1, 3]', 'code block has 2 annotation(s) but the list after it has 1 item(s)']
    """
    findings: List[Finding] = []
    for start, end, _info, code in fences:
        nums = [int(m.group(1)) for line in code for m in re.finditer(r"#\s*<(\d+)>\s*$", line)]
        if not nums:
            continue
        if sorted(nums) != list(range(1, len(nums) + 1)):
            findings.append(Finding("ERROR", start, f"code annotations are not contiguous from 1: {nums}"))
        items = 0
        k = end  # index of first line after the fence (0-based == end since end is 1-based)
        while k < len(body_lines) and not body_lines[k].strip():
            k += 1
        while k < len(body_lines) and re.match(r"^\s*\d+\.\s", body_lines[k]):
            items += 1
            k += 1
        if items != len(nums):
            findings.append(
                Finding(
                    "ERROR",
                    start,
                    f"code block has {len(nums)} annotation(s) but the list after it has {items} item(s)",
                )
            )
    return findings


def find_links(text: str) -> List[Tuple[int, str, str]]:
    """Find image/link/video/reference-definition targets.

    Returns ``(line, kind, target)`` where kind is ``image``, ``link``,
    ``video`` or ``refdef``. Bare ``<https://…>`` autolinks are not
    collected; they are rare in posts and always visible to the reader.

    Example:
        >>> find_links("![c](https://a/x.jpg) [t](/Users/me/a.png)\\n{{< video https://v/x.mp4 >}}\\n[slug]: https://d/e")
        [(1, 'image', 'https://a/x.jpg'), (1, 'link', '/Users/me/a.png'), (2, 'video', 'https://v/x.mp4'), (3, 'refdef', 'https://d/e')]
    """
    links: List[Tuple[int, str, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        for m in re.finditer(r"(!?)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", line):
            links.append((n, "image" if m.group(1) else "link", m.group(2)))
        for m in re.finditer(r"\{\{<\s*video\s+([^\s>]+)", line):
            links.append((n, "video", m.group(1)))
        m = re.match(r"^\s*\[[^\]^]+\]:\s*(\S+)", line)
        if m:
            links.append((n, "refdef", m.group(1)))
    return links


def is_local_path(target: str) -> bool:
    """True when a target points at the author's machine rather than the web.

    Example:
        >>> is_local_path("/Users/jho/Downloads/a.jpg"), is_local_path("~/x.png"), is_local_path("https://a/b.jpg")
        (True, True, False)
        >>> is_local_path("#section"), is_local_path("other-post.qmd"), is_local_path("assets/a.png")
        (False, False, False)
    """
    return target.startswith(LOCAL_PATH_PREFIXES)


def is_relative_media(target: str) -> bool:
    """True for a relative path to a media file (may be fine, worth a look).

    Example:
        >>> is_relative_media("assets/a.png"), is_relative_media("https://a/b.jpg"), is_relative_media("post.qmd")
        (True, False, False)
    """
    return (
        not re.match(r"^[a-z][a-z0-9+.-]*:", target)
        and not target.startswith(("#", "/"))
        and target.lower().endswith(MEDIA_SUFFIXES)
    )


def find_uncaptioned_media(text: str) -> List[int]:
    """Lines with ``![](url)`` images that have no alt/caption text.

    Example:
        >>> find_uncaptioned_media("![](https://a/x.jpg)\\n![ok](https://a/y.jpg)")
        [1]
    """
    return [n for n, line in enumerate(text.splitlines(), start=1) if re.search(r"!\[\s*\]\(", line)]


def fetch_status(url: str, timeout: float) -> Tuple[str, Optional[int], str]:
    """HEAD a URL, falling back to GET when HEAD is refused.

    Args:
        url: Absolute http(s) URL.
        timeout: Seconds per request.

    Returns:
        ``(url, status_code_or_None, note)``.
    """
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return url, resp.status, ""
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            return url, e.code, e.reason if isinstance(e.reason, str) else ""
        except Exception as e:  # noqa: BLE001 - network errors of every flavour
            if method == "HEAD":
                continue
            return url, None, type(e).__name__
    return url, None, "unreachable"


def check_urls(urls: Iterable[str], timeout: float, workers: int = 8) -> Dict[str, Tuple[Optional[int], str]]:
    """Check many URLs concurrently; returns ``{url: (status, note)}``."""
    unique = sorted(set(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda u: fetch_status(u, timeout), unique)
    return {u: (s, n) for u, s, n in results}


def lint(text: str, offline: bool = False, timeout: float = 10.0) -> List[Finding]:
    """Run every check on a post's text and return the findings.

    Args:
        text: Full ``.qmd`` contents.
        offline: Skip remote URL checks.
        timeout: Per-request timeout for URL checks.

    Returns:
        Findings sorted by line number, errors before warnings on ties.

    Example:
        >>> post = "---\\ntitle: t\\nabstract: s\\ndate: 1/1/2026\\nauthor: a\\ncategories: [x]\\n---\\nsee @tbl-nope\\n"
        >>> [f.message for f in lint(post, offline=True)]
        ['reference @tbl-nope has no matching {#tbl-nope}']
    """
    findings: List[Finding] = []
    front, body, offset = split_front_matter(text)
    if front is None:
        findings.append(Finding("ERROR", 1, "no YAML front matter (--- … ---) at top of file"))
    else:
        keys = front_matter_keys(front)
        for key in REQUIRED_FRONT_MATTER:
            if key not in keys:
                findings.append(Finding("ERROR", 1, f"front matter is missing `{key}`"))
        if "abstract" not in keys:
            findings.append(Finding("WARN", 1, "front matter has no `abstract` (listing pages show it)"))

    prose, fences = strip_code_fences(body)
    body_lines = body.splitlines()
    ln = lambda n: n + offset  # noqa: E731 - body line -> file line

    ids = find_ids(prose)
    for k, v in find_fence_labels(fences).items():
        ids.setdefault(k, []).extend(v)
    for ident, lines in ids.items():
        if len(lines) > 1:
            findings.append(Finding("ERROR", ln(lines[1]), f"duplicate id {{#{ident}}} (also at line {ln(lines[0])})"))

    for n, ref in find_refs(prose):
        if ref not in ids:
            findings.append(Finding("ERROR", ln(n), f"reference @{ref} has no matching {{#{ref}}}"))

    for n in find_tables_without_caption(prose):
        findings.append(Finding("WARN", ln(n), "pipe table without a `: caption {#tbl-…}` line after it"))

    for f in check_annotations(body_lines, fences):
        findings.append(Finding(f.level, ln(f.line), f.message))

    if fences and any(re.search(r"#\s*<\d+>\s*$", l) for _s, _e, _i, c in fences for l in c):
        if front is None or "code-annotations" not in front:
            findings.append(Finding("WARN", 1, "code annotations used but `code-annotations: hover` not set in front matter"))

    urls: List[str] = []
    for n, kind, target in find_links(prose):
        if is_local_path(target):
            findings.append(Finding("ERROR", ln(n), f"{kind} points at a local path: {target}"))
        elif is_relative_media(target):
            findings.append(Finding("WARN", ln(n), f"{kind} uses a relative media path (must exist in the site): {target}"))
        elif target.startswith(("http://", "https://")):
            urls.append(target)

    for n in find_uncaptioned_media(prose):
        findings.append(Finding("WARN", ln(n), "image has no caption/alt text"))

    if urls and not offline:
        statuses = check_urls(urls, timeout)
        for n, _kind, target in find_links(prose):
            if target in statuses:
                status, note = statuses[target]
                if status is None or status >= 400:
                    findings.append(Finding("ERROR", ln(n), f"URL not reachable ({status or note}): {target}"))

    findings.sort(key=lambda f: (f.line, f.level != "ERROR"))
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Lint a Quarto .qmd post without rendering it.")
    parser.add_argument("post", type=Path, help="Path to the .qmd file")
    parser.add_argument("--offline", action="store_true", help="Skip remote URL checks")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    parser.add_argument("--timeout", type=float, default=10.0, help="Seconds per URL request")
    args = parser.parse_args(argv)

    text = args.post.read_text(encoding="utf-8")
    findings = lint(text, offline=args.offline, timeout=args.timeout)
    errors = sum(f.level == "ERROR" for f in findings)
    warns = len(findings) - errors

    if args.json:
        print(json.dumps({"file": str(args.post), "errors": errors, "warnings": warns,
                          "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        for f in findings:
            print(f"{f.level:5} {args.post}:{f.line} {f.message}")
        print(f"{args.post}: {errors} error(s), {warns} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
