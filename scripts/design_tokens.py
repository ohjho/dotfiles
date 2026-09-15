# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12", "loguru>=0.7"]
# ///
"""Validate and render a W3C DTCG ``design.tokens.json`` written by the design-derivation skill.

The skill derives a visual direction and records it as ``design.md`` (the reasons) and
``design.tokens.json`` (the values, in the W3C Design Tokens Community Group format).
This script is the bridge to the skills that consume those values, so nobody hand
translates hex codes into CSS, Markdown, or SCSS::

    uv run scripts/design_tokens.py check design.tokens.json
    uv run scripts/design_tokens.py render css  design.tokens.json            # :root + dark media query
    uv run scripts/design_tokens.py render css  design.tokens.json --artifact # + data-theme guards
    uv run scripts/design_tokens.py render md   design.tokens.json --into design.md
    uv run scripts/design_tokens.py render scss design.tokens.json --theme dark -o theme-dark.scss

Token file shape (colors live in one ``light`` and one ``dark`` set, everything else is
shared)::

    {
      "$description": "Keystone: colour = which pipeline phase you are in",
      "color": {
        "light": {"bg": {"$type": "color", "$value": "#F4F6F7",
                         "$extensions": {"design-derivation": {"from": "constraint"}}}, ...},
        "dark":  {"bg": {"$type": "color", "$value": "#10161D"}, ...}
      },
      "font":    {"display": {"$type": "fontFamily", "$value": ["Fraunces", "serif"]}, ...},
      "radius":  {"md":   {"$type": "dimension", "$value": {"value": 8,  "unit": "px"}}},
      "space":   {"base": {"$type": "dimension", "$value": {"value": 8,  "unit": "px"}}},
      "measure": {"body": {"$type": "dimension", "$value": {"value": 65, "unit": "ch"}}}
    }

``check`` enforces the **core roles** every consumer may rely on (``bg surface ink muted
line accent accent-soft``; ``font.display``/``font.body``; ``radius.md``, ``space.base``,
``measure.body``), light/dark parity, valid hex colours, and WCAG AA contrast on the
ink/muted/accent-on-ground pairs. Extra colour tokens that carry the design's keystone
(``hot``/``cold``, ``offline``/``runtime``) are welcome and only get contrast *warnings*.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import typer
from loguru import logger

PROVENANCE_EXT = "design-derivation"
THEMES = ("light", "dark")
CORE_COLORS = ("bg", "surface", "ink", "muted", "line", "accent", "accent-soft")
CORE_FONTS = ("display", "body")
CORE_LAYOUT = (("radius", "md"), ("space", "base"), ("measure", "body"))
CSS_ALIASES = {"space-base": "space", "measure-body": "measure"}
# (foreground, background, minimum ratio) — WCAG AA: 4.5 for text, 3.0 for large text / UI.
CONTRAST_PAIRS = (
    ("ink", "bg", 4.5),
    ("ink", "surface", 4.5),
    ("muted", "bg", 3.0),
    ("muted", "surface", 3.0),
    ("accent", "bg", 3.0),
)
EXTRA_MIN_CONTRAST = 3.0
MARK_START = "<!-- tokens:start -->"
MARK_END = "<!-- tokens:end -->"
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# Quarto / Bootstrap SCSS variables fed from the core roles.
SCSS_COLOR_MAP = (
    ("body-bg", "bg"),
    ("body-color", "ink"),
    ("link-color", "accent"),
    ("border-color", "line"),
    ("text-muted", "muted"),
    ("card-bg", "surface"),
    ("code-bg", "surface"),
)
SCSS_FONT_MAP = (
    ("headings-font-family", "display"),
    ("font-family-sans-serif", "body"),
    ("font-family-monospace", "mono"),
)

app = typer.Typer(
    add_completion=False,
    help="Validate and render a DTCG design.tokens.json into CSS, Markdown, or Quarto SCSS.",
)


@dataclass(frozen=True)
class Token:
    """One resolved design token.

    Attributes:
        path: Group path from the file root, e.g. ``("color", "light", "bg")``.
        type: The DTCG ``$type`` (own or inherited from an enclosing group).
        value: The raw ``$value``.
        description: The token's ``$description`` (may be empty).
        source: Which derivation input produced it, from
            ``$extensions["design-derivation"]["from"]`` (may be empty).
    """

    path: tuple[str, ...]
    type: Optional[str]
    value: Any
    description: str = ""
    source: str = ""

    @property
    def name(self) -> str:
        """Dashed name inside its theme/group, e.g. ``accent-soft``."""
        return "-".join(self.path[2:] if self.path[:1] == ("color",) else self.path[1:])


@dataclass(frozen=True)
class Issue:
    """A validation finding: ``level`` is ``error`` or ``warning``."""

    level: str
    message: str


def sample_tree() -> dict:
    """Return a minimal valid token tree, used by the doctests below.

    Examples:
        >>> sorted(sample_tree()["color"]["light"])
        ['accent', 'accent-soft', 'bg', 'ink', 'line', 'muted', 'surface']
    """

    def color(value: str, source: str = "content") -> dict:
        return {
            "$type": "color",
            "$value": value,
            "$extensions": {PROVENANCE_EXT: {"from": source}},
        }

    return {
        "$description": "Sample: colour = phase",
        "color": {
            "light": {
                "bg": color("#F4F6F7", "constraint"),
                "surface": color("#FFFFFF", "constraint"),
                "ink": color("#1B2733", "audience"),
                "muted": color("#5C6B7A", "audience"),
                "line": color("#DCE3E8", "constraint"),
                "accent": color("#2B5FC7"),
                "accent-soft": color("#E7EDFB"),
            },
            "dark": {
                "bg": color("#10161D", "constraint"),
                "surface": color("#171F28", "constraint"),
                "ink": color("#E7EDF2", "audience"),
                "muted": color("#93A2B1", "audience"),
                "line": color("#2A3642", "constraint"),
                "accent": color("#7FA3F5"),
                "accent-soft": color("#1B2A47"),
            },
        },
        "font": {
            "$type": "fontFamily",
            "display": {"$value": ["Fraunces", "serif"], "$description": "editorial voice"},
            "body": {"$value": ["Inter", "sans-serif"]},
            "mono": {"$value": ["JetBrains Mono", "monospace"]},
        },
        "radius": {"md": {"$type": "dimension", "$value": {"value": 8, "unit": "px"}}},
        "space": {"base": {"$type": "dimension", "$value": {"value": 8, "unit": "px"}}},
        "measure": {"body": {"$type": "dimension", "$value": {"value": 65, "unit": "ch"}}},
    }


# --------------------------------------------------------------------------- parsing


def flatten(tree: dict, prefix: tuple[str, ...] = (), inherited_type: Optional[str] = None) -> list[Token]:
    """Walk a DTCG tree and return every token (any dict carrying ``$value``).

    Group-level ``$type`` is inherited by the tokens beneath it, as the spec allows.
    Keys starting with ``$`` are metadata, never groups.

    Args:
        tree: The parsed JSON object (or a sub-group of it).
        prefix: Path accumulated so far.
        inherited_type: ``$type`` declared on an enclosing group.

    Returns:
        Tokens in file order.

    Examples:
        >>> toks = flatten({"font": {"$type": "fontFamily", "body": {"$value": ["Inter"]}}})
        >>> toks[0].path, toks[0].type, toks[0].value
        (('font', 'body'), 'fontFamily', ['Inter'])
        >>> flatten({"$description": "meta only"})
        []
        >>> t = flatten({"x": {"$value": "#fff", "$extensions": {"design-derivation": {"from": "goal"}}}})[0]
        >>> t.source, t.type
        ('goal', None)
    """
    tokens: list[Token] = []
    group_type = tree.get("$type", inherited_type)
    for key, node in tree.items():
        if key.startswith("$") or not isinstance(node, dict):
            continue
        path = prefix + (key,)
        if "$value" in node:
            ext = node.get("$extensions", {}).get(PROVENANCE_EXT, {})
            tokens.append(
                Token(
                    path=path,
                    type=node.get("$type", group_type),
                    value=node["$value"],
                    description=str(node.get("$description", "")),
                    source=str(ext.get("from", "")) if isinstance(ext, dict) else "",
                )
            )
        else:
            tokens.extend(flatten(node, path, group_type))
    return tokens


def color_set(tokens: list[Token], theme: str) -> dict[str, Token]:
    """Return the colour tokens of one theme keyed by dashed name.

    Examples:
        >>> light = color_set(flatten(sample_tree()), "light")
        >>> light["accent-soft"].value
        '#E7EDFB'
        >>> color_set(flatten(sample_tree()), "sepia")
        {}
    """
    return {t.name: t for t in tokens if t.path[:2] == ("color", theme)}


def shared_tokens(tokens: list[Token]) -> list[Token]:
    """Return every non-colour token (fonts, dimensions, ...), shared by both themes.

    Examples:
        >>> [t.name for t in shared_tokens(flatten(sample_tree()))]
        ['display', 'body', 'mono', 'md', 'base', 'body']
    """
    return [t for t in tokens if t.path[:1] != ("color",)]


def find_token(tokens: list[Token], *path: str) -> Optional[Token]:
    """Look a token up by exact path.

    Examples:
        >>> find_token(flatten(sample_tree()), "radius", "md").value
        {'value': 8, 'unit': 'px'}
        >>> find_token(flatten(sample_tree()), "radius", "xl") is None
        True
    """
    return next((t for t in tokens if t.path == path), None)


# --------------------------------------------------------------------------- colour math


def parse_hex(value: str) -> tuple[float, float, float]:
    """Parse ``#RGB``, ``#RRGGBB`` or ``#RRGGBBAA`` into sRGB channels in ``0..1`` (alpha dropped).

    Raises:
        ValueError: if the string is not a hex colour.

    Examples:
        >>> parse_hex("#fff")
        (1.0, 1.0, 1.0)
        >>> parse_hex("#10161D80")[0] == 0x10 / 255
        True
        >>> parse_hex("rgb(0,0,0)")
        Traceback (most recent call last):
        ...
        ValueError: not a hex colour: 'rgb(0,0,0)'
    """
    if not isinstance(value, str) or not HEX_RE.match(value):
        raise ValueError(f"not a hex colour: {value!r}")
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    r, g, b = (int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b)


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG 2.x relative luminance of linearised sRGB channels.

    Examples:
        >>> relative_luminance((1.0, 1.0, 1.0))
        1.0
        >>> relative_luminance((0.0, 0.0, 0.0))
        0.0
    """

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two hex colours (order-independent, ``1..21``).

    Examples:
        >>> contrast_ratio("#000", "#fff")
        21.0
        >>> round(contrast_ratio("#1B2733", "#F4F6F7"), 2)
        13.99
        >>> contrast_ratio("#777", "#777")
        1.0
    """
    l1, l2 = sorted((relative_luminance(parse_hex(fg)), relative_luminance(parse_hex(bg))), reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 4)


# --------------------------------------------------------------------------- validation


def find_issues(tree: dict, allow_single_theme: bool = False) -> list[Issue]:
    """Validate a token tree against the core-role contract and WCAG AA.

    Errors: a missing core role, a theme set present in ``light`` but not ``dark`` (or
    vice versa), an invalid hex colour, a malformed dimension, or a contrast pair under
    its AA threshold. Warnings: a missing ``font.mono``, an extra colour token with weak
    contrast against ``bg``, and a missing ``dark`` set when ``allow_single_theme``.

    Args:
        tree: Parsed ``design.tokens.json``.
        allow_single_theme: Downgrade a missing ``dark`` set to a warning (for print or
            other single-state destinations).

    Returns:
        Issues in detection order; empty when the file is clean.

    Examples:
        >>> find_issues(sample_tree())
        []
        >>> bad = sample_tree(); del bad["color"]["dark"]["line"]; bad["color"]["light"]["ink"]["$value"] = "#AAAAAA"
        >>> for i in find_issues(bad): print(i.level, "|", i.message)
        error | color.dark.line: missing core colour role
        error | color.light.ink on bg: contrast 2.14 < 4.5 (WCAG AA)
        error | color.light.ink on surface: contrast 2.32 < 4.5 (WCAG AA)
        >>> extra = sample_tree(); extra["color"]["light"]["hot"] = {"$type": "color", "$value": "#F2A93B"}
        >>> for i in find_issues(extra): print(i.level, "|", i.message)
        error | color.dark.hot: defined in light but missing in dark
        warning | color.light.hot on bg: contrast 1.84 < 3.0 (keystone extra; fine if decorative)
        >>> single = sample_tree(); del single["color"]["dark"]
        >>> [i.level for i in find_issues(single)]
        ['error']
        >>> [i.level for i in find_issues(single, allow_single_theme=True)]
        ['warning']
    """
    issues: list[Issue] = []
    tokens = flatten(tree)
    sets = {theme: color_set(tokens, theme) for theme in THEMES}

    if not sets["light"]:
        issues.append(Issue("error", "color.light: missing colour set"))
    if not sets["dark"]:
        level = "warning" if allow_single_theme else "error"
        issues.append(Issue(level, "color.dark: missing colour set (every web consumer expects both themes)"))

    present = [theme for theme in THEMES if sets[theme]]
    for theme in present:
        for role in CORE_COLORS:
            if role not in sets[theme]:
                issues.append(Issue("error", f"color.{theme}.{role}: missing core colour role"))
        for name, token in sets[theme].items():
            if token.type not in (None, "color"):
                issues.append(Issue("error", f"color.{theme}.{name}: $type is {token.type!r}, expected 'color'"))
            try:
                parse_hex(token.value)
            except ValueError:
                issues.append(Issue("error", f"color.{theme}.{name}: {token.value!r} is not a #RRGGBB hex colour"))
    if len(present) == 2:
        for theme, other in ((THEMES[0], THEMES[1]), (THEMES[1], THEMES[0])):
            for name in sorted(sets[theme].keys() - sets[other].keys() - set(CORE_COLORS)):
                issues.append(Issue("error", f"color.{other}.{name}: defined in {theme} but missing in {other}"))

    for theme in present:
        colours = {n: t.value for n, t in sets[theme].items() if isinstance(t.value, str) and HEX_RE.match(t.value)}
        for fg, bg, minimum in CONTRAST_PAIRS:
            if fg in colours and bg in colours:
                ratio = contrast_ratio(colours[fg], colours[bg])
                if ratio < minimum:
                    issues.append(Issue("error", f"color.{theme}.{fg} on {bg}: contrast {ratio:.2f} < {minimum} (WCAG AA)"))
        if "bg" in colours:
            for name in sorted(colours.keys() - set(CORE_COLORS)):
                if name.endswith("-soft"):
                    continue
                ratio = contrast_ratio(colours[name], colours["bg"])
                if ratio < EXTRA_MIN_CONTRAST:
                    issues.append(
                        Issue("warning", f"color.{theme}.{name} on bg: contrast {ratio:.2f} < {EXTRA_MIN_CONTRAST} (keystone extra; fine if decorative)")
                    )

    for role in CORE_FONTS:
        if find_token(tokens, "font", role) is None:
            issues.append(Issue("error", f"font.{role}: missing core font role"))
    if find_token(tokens, "font", "mono") is None:
        issues.append(Issue("warning", "font.mono: not set (needed for code, data readouts, labels)"))
    for token in tokens:
        bad_font = not isinstance(token.value, (list, str)) or (isinstance(token.value, list) and not token.value)
        if token.path[:1] == ("font",) and bad_font:
            issues.append(Issue("error", f"{'.'.join(token.path)}: fontFamily $value must be a non-empty list or string"))

    for group, name in CORE_LAYOUT:
        if find_token(tokens, group, name) is None:
            issues.append(Issue("error", f"{group}.{name}: missing core layout token"))
    for token in tokens:
        if token.type == "dimension" and not _valid_dimension(token.value):
            issues.append(Issue("error", f"{'.'.join(token.path)}: dimension $value must be {{\"value\": <number>, \"unit\": <str>}} or a CSS length string"))
    return issues


def _valid_dimension(value: Any) -> bool:
    """True for the DTCG object form or a CSS length string.

    Examples:
        >>> _valid_dimension({"value": 8, "unit": "px"}), _valid_dimension("0.5rem"), _valid_dimension(8)
        (True, True, False)
    """
    if isinstance(value, str):
        return bool(re.match(r"^-?\d*\.?\d+[a-z%]*$", value.strip()))
    return isinstance(value, dict) and isinstance(value.get("value"), (int, float)) and isinstance(value.get("unit"), str)


# --------------------------------------------------------------------------- rendering


def css_var_name(token: Token) -> str:
    """CSS custom-property name for a token.

    Colour tokens drop the ``color.<theme>`` prefix so both themes share one name;
    other groups are joined with dashes, with the ``space``/``measure`` base aliases.

    Examples:
        >>> css_var_name(Token(("color", "light", "accent-soft"), "color", "#fff"))
        '--accent-soft'
        >>> css_var_name(Token(("font", "display"), "fontFamily", []))
        '--font-display'
        >>> css_var_name(Token(("space", "base"), "dimension", "8px"))
        '--space'
        >>> css_var_name(Token(("space", "xl"), "dimension", "8px"))
        '--space-xl'
    """
    if token.path[:1] == ("color",):
        return "--" + "-".join(token.path[2:])
    joined = "-".join(token.path)
    return "--" + CSS_ALIASES.get(joined, joined)


def format_value(token: Token) -> str:
    """Render a token's ``$value`` as CSS text.

    Examples:
        >>> format_value(Token(("font", "body"), "fontFamily", ["Inter", "sans-serif"]))
        '"Inter", sans-serif'
        >>> format_value(Token(("font", "body"), "fontFamily", "Georgia"))
        'Georgia'
        >>> format_value(Token(("radius", "md"), "dimension", {"value": 8, "unit": "px"}))
        '8px'
        >>> format_value(Token(("radius", "md"), "dimension", {"value": 0.5, "unit": "rem"}))
        '0.5rem'
        >>> format_value(Token(("motion", "fast"), "duration", {"value": 150, "unit": "ms"}))
        '150ms'
        >>> format_value(Token(("shadow", "card"), "shadow", "0 1px 2px rgba(0,0,0,.1)"))
        '0 1px 2px rgba(0,0,0,.1)'
    """
    value = token.value
    if isinstance(value, list):
        generic = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-monospace", "ui-serif", "ui-sans-serif"}
        return ", ".join(v if v in generic else f'"{v}"' for v in value)
    if isinstance(value, dict) and "value" in value and "unit" in value:
        number = value["value"]
        text = f"{number:g}" if isinstance(number, float) else str(number)
        return f"{text}{value['unit']}"
    return str(value)


def _declarations(tokens: list[Token], indent: str = "  ") -> str:
    return "\n".join(f"{indent}{css_var_name(t)}: {format_value(t)};" for t in tokens)


def render_css(tree: dict, artifact: bool = False) -> str:
    """Render ``:root`` custom properties: light + shared tokens, then the dark redefinition.

    Args:
        tree: Parsed ``design.tokens.json``.
        artifact: Add the ``data-theme`` guards the claude.ai artifact contract needs
            (``:root:not([data-theme="light"])`` inside the media query plus an explicit
            ``:root[data-theme="dark"]`` block). Surge pages leave this off.

    Examples:
        >>> css = render_css(sample_tree())
        >>> print(css.splitlines()[1]); print(css.splitlines()[2])
        :root {
          --bg: #F4F6F7;
        >>> "@media (prefers-color-scheme: dark)" in css and "--space: 8px;" in css
        True
        >>> 'data-theme' in css, 'data-theme' in render_css(sample_tree(), artifact=True)
        (False, True)
        >>> "@media" in render_css({"color": {"light": {"bg": {"$type": "color", "$value": "#fff"}}}})
        False
    """
    tokens = flatten(tree)
    light = list(color_set(tokens, "light").values())
    dark = list(color_set(tokens, "dark").values())
    parts = ["/* generated by design_tokens.py from design.tokens.json — edit the JSON, not this */"]
    parts.append(":root {\n" + _declarations(light + shared_tokens(tokens)) + "\n}")
    if dark:
        selector = ':root:not([data-theme="light"])' if artifact else ":root"
        parts.append("@media (prefers-color-scheme: dark) {\n  " + selector + " {\n" + _declarations(dark, "    ") + "\n  }\n}")
        if artifact:
            parts.append(':root[data-theme="dark"] {\n' + _declarations(dark) + "\n}")
    return "\n".join(parts) + "\n"


def render_md(tree: dict) -> str:
    """Render the token tables for ``design.md`` (colours per theme, then shared tokens).

    Examples:
        >>> md = render_md(sample_tree())
        >>> print(md.splitlines()[0])
        | token | light | dark | from | note |
        >>> "| bg | `#F4F6F7` | `#10161D` | constraint |  |" in md
        True
        >>> "| font-display | `\\"Fraunces\\", serif` | audience? |" in md
        False
        >>> [l for l in md.splitlines() if l.startswith("| font-display")]
        ['| font-display | `"Fraunces", serif` |  | editorial voice |']
    """
    tokens = flatten(tree)
    light, dark = color_set(tokens, "light"), color_set(tokens, "dark")
    lines = ["| token | light | dark | from | note |", "|---|---|---|---|---|"]
    for name in list(light) + [n for n in dark if n not in light]:
        token = light.get(name) or dark[name]
        lines.append(
            f"| {name} | {_cell(light.get(name))} | {_cell(dark.get(name))} | {token.source} | {token.description} |"
        )
    shared = shared_tokens(tokens)
    if shared:
        lines += ["", "| token | value | from | note |", "|---|---|---|---|"]
        for token in shared:
            lines.append(f"| {css_var_name(token)[2:]} | `{format_value(token)}` | {token.source} | {token.description} |")
    return "\n".join(lines) + "\n"


def _cell(token: Optional[Token]) -> str:
    return f"`{format_value(token)}`" if token else "—"


def render_scss(tree: dict, theme: str = "light") -> str:
    """Render a Quarto SCSS theme file for one theme.

    Emits a ``scss:defaults`` block mapping the core roles to Bootstrap variables, and a
    ``scss:rules`` block exposing every token as a CSS custom property. Quarto takes one
    theme file per state, so call once with ``light`` and once with ``dark``.

    Examples:
        >>> scss = render_scss(sample_tree())
        >>> print(scss.splitlines()[0]); print(scss.splitlines()[1])
        /*-- scss:defaults --*/
        $body-bg: #F4F6F7;
        >>> '$headings-font-family: "Fraunces", serif;' in scss and "--ink: #1B2733;" in scss
        True
        >>> '$font-family-monospace: "JetBrains Mono", monospace;' in scss
        True
        >>> "$body-bg: #10161D;" in render_scss(sample_tree(), "dark")
        True
        >>> render_scss(sample_tree(), "sepia")
        Traceback (most recent call last):
        ...
        ValueError: no colour set named 'sepia'
    """
    tokens = flatten(tree)
    colours = color_set(tokens, theme)
    if not colours:
        raise ValueError(f"no colour set named {theme!r}")
    defaults = ["/*-- scss:defaults --*/"]
    for var, role in SCSS_COLOR_MAP:
        if role in colours:
            defaults.append(f"${var}: {format_value(colours[role])};")
    for var, role in SCSS_FONT_MAP:
        token = find_token(tokens, "font", role)
        if token is not None:
            defaults.append(f"${var}: {format_value(token)};")
    radius = find_token(tokens, "radius", "md")
    if radius is not None:
        defaults.append(f"$border-radius: {format_value(radius)};")
    rules = ["/*-- scss:rules --*/", ":root {", _declarations(list(colours.values()) + shared_tokens(tokens)), "}"]
    return "\n".join(defaults) + "\n\n" + "\n".join(rules) + "\n"


def splice_between_markers(text: str, block: str) -> str:
    """Replace whatever sits between the tokens markers in ``design.md`` with ``block``.

    Raises:
        ValueError: if either marker is missing or out of order.

    Examples:
        >>> doc = "# D\\n<!-- tokens:start -->\\nold\\n<!-- tokens:end -->\\ntail\\n"
        >>> print(splice_between_markers(doc, "| new |\\n"))
        # D
        <!-- tokens:start -->
        | new |
        <!-- tokens:end -->
        tail
        <BLANKLINE>
        >>> splice_between_markers("no markers", "x")
        Traceback (most recent call last):
        ...
        ValueError: design.md needs both '<!-- tokens:start -->' and '<!-- tokens:end -->' markers
    """
    start, end = text.find(MARK_START), text.find(MARK_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"design.md needs both {MARK_START!r} and {MARK_END!r} markers")
    head = text[: start + len(MARK_START)]
    return f"{head}\n{block.rstrip()}\n{text[end:]}"


# --------------------------------------------------------------------------- side effects


def load_tokens(path: Path) -> dict:
    """Read and parse a token file; exits with code 2 on a missing or malformed file."""
    if not path.is_file():
        logger.error("token file not found: {}", path)
        raise typer.Exit(code=2)
    try:
        tree = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("{} is not valid JSON: {}", path, exc)
        raise typer.Exit(code=2)
    if not isinstance(tree, dict):
        logger.error("{}: top level must be a JSON object", path)
        raise typer.Exit(code=2)
    return tree


def configure_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="<level>{level:<7}</level> {message}")


@app.command()
def check(
    tokens: Path = typer.Argument(..., help="Path to design.tokens.json."),
    allow_single_theme: bool = typer.Option(False, "--allow-single-theme", help="A missing dark set is a warning, not an error (print / single-state destinations)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging."),
) -> None:
    """Validate core roles, light/dark parity, hex colours, and WCAG AA contrast."""
    configure_logging(verbose)
    tree = load_tokens(tokens)
    issues = find_issues(tree, allow_single_theme=allow_single_theme)
    for issue in issues:
        typer.echo(f"{issue.level.upper():<7} {issue.message}")
    errors = sum(1 for i in issues if i.level == "error")
    warnings = len(issues) - errors
    logger.info("{}: {} token(s), {} error(s), {} warning(s)", tokens, len(flatten(tree)), errors, warnings)
    if errors:
        raise typer.Exit(code=1)


@app.command()
def render(
    target: str = typer.Argument(..., help="css | md | scss"),
    tokens: Path = typer.Argument(..., help="Path to design.tokens.json."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write here instead of stdout."),
    into: Optional[Path] = typer.Option(None, "--into", help="md only: rewrite the block between the tokens markers of this design.md in place."),
    theme: str = typer.Option("light", "--theme", help="scss only: which colour set to render (light | dark)."),
    artifact: bool = typer.Option(False, "--artifact", help="css only: add the data-theme guards for claude.ai artifacts."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging."),
) -> None:
    """Render the tokens as CSS custom properties, Markdown tables, or a Quarto SCSS theme."""
    configure_logging(verbose)
    tree = load_tokens(tokens)
    try:
        if target == "css":
            text = render_css(tree, artifact=artifact)
        elif target == "md":
            text = render_md(tree)
        elif target == "scss":
            text = render_scss(tree, theme=theme)
        else:
            logger.error("unknown render target {!r}; expected css, md, or scss", target)
            raise typer.Exit(code=2)
    except ValueError as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2)

    if into is not None:
        if target != "md":
            logger.error("--into only applies to the md target")
            raise typer.Exit(code=2)
        if not into.is_file():
            logger.error("design.md not found: {}", into)
            raise typer.Exit(code=2)
        try:
            into.write_text(splice_between_markers(into.read_text(encoding="utf-8"), text), encoding="utf-8")
        except ValueError as exc:
            logger.error("{}", exc)
            raise typer.Exit(code=2)
        logger.info("updated token tables in {}", into)
        return
    if output is not None:
        output.write_text(text, encoding="utf-8")
        logger.info("wrote {} ({} bytes)", output, len(text))
        return
    typer.echo(text, nl=False)


if __name__ == "__main__":
    app()
