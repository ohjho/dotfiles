## Site

Quarto website: `index.qmd` is a prose landing page, `posts.qmd` lists the flat `posts/*.qmd`
files, `pages/` holds generated pages that are not hand-written posts. Only `*.qmd` files render
(`render: "**/*.qmd"`), so markdown files like this one never become pages. Navbar:
Posts · {{About · }}GitHub. Published at {{site_url}} by `.github/workflows/publish.yml` on every
push to `{{default_branch}}`.

## Commands

```bash
quarto preview          # live-reload dev server
quarto render           # builds to _site/ (gitignored, as is .quarto/)
```

Posts freeze computational output (`posts/_metadata.yml`), so a changed code cell needs
`quarto render posts/<name>.qmd` to refresh its cache; commit `_freeze/` if a post gains cells,
because the publish workflow installs no runtime.

## Design tokens

The site's look is derived, not picked: `design.md` is the brief (keystone: {{keystone}}) and
`design.tokens.json` holds the values. `theme-light.scss` and `theme-dark.scss` are generated from
the JSON and wired in `_quarto.yml`; `site.scss` applies the tokens to Quarto components and is
hand-maintained. To change a colour or font, edit the JSON, then:

```bash
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py check design.tokens.json
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render md   design.tokens.json --into design.md
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme light -o theme-light.scss
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme dark  -o theme-dark.scss
```

Posts use `var(--token)` values through `site.scss`, never inline colours, and never a title
banner or a second accent.

## Skills

`quarto-site-setup`, `design-derivation`, `goatcounter-tracking`, `quarto-gh-publish-action` and
`quarto-writeup` under `.claude/skills/` are symlinks into the author's dotfiles repo, not repo
content; they resolve only on that machine. `quarto-writeup` is the intended path for turning work
into posts under `posts/`.
