# Writing `site.scss` from the tokens

`theme-light.scss` / `theme-dark.scss` (generated) set Bootstrap's variables and expose every
token as a CSS custom property on `:root`. `site.scss` is layered after them in both theme stacks,
so it is written once and must reference tokens only through `var(--…)` — never a literal colour,
font or size. Write it fresh for each site from this checklist; the shape is fixed, the choices
(weights, which components get the display font) follow `design.md`.

## Header

```scss
/*-- scss:defaults --*/
// Site rules layered after the generated theme-light.scss / theme-dark.scss.
// Tokens come from design.tokens.json (see design.md); this file only applies them.
$web-font-path: "https://fonts.googleapis.com/css2?family=<Display>:wght@400;500;600&family=<Body>:ital,wght@0,400;0,600;1,400&display=swap";

/*-- scss:rules --*/
```

`$web-font-path` must list exactly the families named in `font.display`, `font.body` and
`font.mono` of `design.tokens.json` (URL-encode spaces as `+`). Omit the line when every family is
a system face.

## Components to cover, and which token each uses

| component | selectors | tokens |
|---|---|---|
| body text | `body` | `--font-body`; `line-height: 1.5` |
| headings and brand | `h1, h2, h3, h4, .navbar-brand, .listing-title, .quarto-title .title` | `--font-display`, `--ink`; `h2` gets `border-bottom: 1px solid var(--line)` and `margin-top: calc(var(--space) * 5)` |
| navbar | `.navbar`, `.navbar .navbar-brand, .navbar .nav-link`, `:hover` | `background-color: var(--bg) !important` (cosmo paints it blue otherwise), `border-bottom: 1px solid var(--line)`, links `--ink`, hover `--accent` |
| links | `a`, `a:hover` | no underline until hover; `text-underline-offset: 0.15em` |
| prose measure | `#quarto-document-content p, li, blockquote` | `max-width: var(--measure)` — tables and code stay full width |
| metadata | `.quarto-title-meta, .listing-date, .listing-author, .quarto-categories, .listing-categories` | `--muted` |
| category pills | `.quarto-category, .listing-category` | `border: 1px solid var(--line) !important`, `border-radius: var(--radius-md) !important`, `--muted`, `--font-mono`, `font-size: 0.75em` |
| listing rows | `.quarto-listing-default .quarto-post`, `.listing-title` | `border-bottom: 1px solid var(--line)`, `padding: calc(var(--space) * 2) 0`, title `1.15rem` |
| code | `pre, code`; `div.sourceCode, pre.sourceCode, pre`; `p code, li code, td code` | `--font-mono`; blocks on `--surface` with `1px solid var(--line)` and `--radius-md`; inline the same, `padding: 0 0.25em` |
| tables | `table`, `table thead th`, `table td, table th` | borders `--line`; header row `--surface`, `border-bottom: 2px solid var(--line)`, `--font-display` |

Add a **keystone helper class** only when `design.md` names an extra token that posts will use
(e.g. `.count { color: var(--accent); }` or a `.highlight` on `--accent-soft`), and document it in
the CLAUDE.md design section. Do not port helper classes from another site.

## Checks

- `grep -E '#[0-9A-Fa-f]{3,6}|rgb\(' site.scss` prints nothing.
- Every `var(--name)` used exists in `theme-light.scss` (`grep -o -- '--[a-z-]*' site.scss | sort -u`
  against the generated `:root`).
- `quarto render` succeeds and both `_site/site_libs/bootstrap/bootstrap*.css` files contain
  `--accent`.
