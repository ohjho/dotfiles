---
name: quarto-site-setup
description: Turn a fresh or `quarto create project blog`-scaffolded repo into a Quarto website shaped like the author's alhaka site — a prose `index.qmd` describing the project, a `posts.qmd` listing over flat `posts/*.qmd`, a `pages/` folder, a derived light + dark theme (`design.tokens.json` → `theme-*.scss` + a hand-written `site.scss`), GoatCounter tracking and a GitHub Pages workflow — by chaining `design-derivation`, `goatcounter-tracking` and `quarto-gh-publish-action`. Use it whenever the user says "set up a quarto site / blog", "new quarto project", "scaffold the blog", "make this repo a quarto website", "set it up like alhaka", "landing page plus a posts listing", or when a stock blog scaffold (sample posts by Tristan O'Malley / Harlow Malloc, placeholder navbar links) sits untouched. It reads `project_brief.md` / `README.md` / `CLAUDE.md` before interviewing, confirms every move or delete, lets each chained skill ask its own questions, offers one commit per stage, and never pushes or enables Pages itself.
---

# Quarto Site Setup

Take a repo from "Quarto scaffold" (or nothing) to a site that looks and behaves like
[alhaka](https://seekingvega.github.io/alhaka): the landing page says what the project is, the
blog lives one click away, the theme is derived from the content instead of picked, visits are
counted, and every push to the default branch redeploys. Done means all of these exist and
`quarto render` exits 0 with the stage-6 checks passing:

`_quarto.yml` · `index.qmd` · `posts.qmd` · `posts/_metadata.yml` · `pages/.gitkeep` ·
`design.md` + `design.tokens.json` · `theme-light.scss` + `theme-dark.scss` + `site.scss` ·
one `count.js` tag · `.github/workflows/publish.yml`.

This skill is an orchestrator. Three stages are owned by sibling skills, which are invoked with
the `Skill` tool and run their own question rounds; this file only says what to pass them and what
to check when they return.

## Guardrails

- **Only the current repo.** Reference sites (alhaka or any other) are read, never edited. The
  dotfiles repo is touched only to create symlinks in step 0, and only after a yes.
- **Nothing is moved or deleted before the step-2 table is confirmed.** Sample posts are deleted
  only when the user picks that option in step 1.
- **Sub-skills own their questions.** Pass them context in prose (target file, recommended option,
  why); never pre-answer on the user's behalf, and never repeat a question they already asked.
- **`_quarto.yml` is merged key by key, never overwritten.** Show the diff. `theme:` and
  `include-in-header:` live under `format: html:`; no post carries its own `format:` block.
- **`site-url` and the real GitHub href are written in step 2**, from `git remote`, so the publish
  skill's site-url and navbar questions become confirmations rather than guesses.
- **Never `git add -A`.** Commits go through the host's `commit-changes` command when present,
  otherwise `git add <files> && git commit`, one offer per stage, each behind a ✋.
- **`quarto render` is the only build run locally.** No `quarto publish`, `git push`, or Pages API
  calls — the publish skill owns those behind its own gates.

## 0. Preflight (no prompts unless something is missing)

```bash
quarto --version                                   # missing → stop; brew install --cask quarto
git rev-parse --show-toplevel
git remote get-url origin 2>/dev/null              # → OWNER/REPO; absent → step 5 is skipped
git config user.email
ls -d .claude/skills/{design-derivation,goatcounter-tracking,quarto-gh-publish-action} 2>&1
ls .claude/commands/commit-changes.md 2>&1
```

Locate dotfiles for symlinking, first hit wins: `$DOTFILES`, `../dotfiles`, `../../dotfiles`,
`~/Documents/Git/_GADA_experiments/dotfiles`. A user site (`REPO == OWNER.github.io`) serves at
`https://OWNER.github.io`; anything else at `https://OWNER.github.io/REPO`. Print a findings block:

```
Quarto 1.10.18 · origin OWNER/REPO → https://OWNER.github.io/REPO · email you@example.com
Skills: design-derivation ✓ goatcounter-tracking ✓ quarto-gh-publish-action ✗ · commit-changes ✗
dotfiles: ../dotfiles
```

✋ Only when something is missing, one `AskUserQuestion`: `Symlink the missing items from
<dotfiles> (Recommended)` / `Abort, I'll install them myself` / `Different dotfiles path — under
Other`. On yes, from the repo root, one `ln -s <relative path to dotfiles>/.claude/skills/<name>
.claude/skills/<name>` per skill (and the same for `.claude/commands/commit-changes.md`), then re-run
the `ls`. Symlinks resolve only on this machine; step 7's CLAUDE.md section says so.

## 1. Brief (read first, then one ✋ round)

Read, in this order, whatever exists: `project_brief.md`, `README.md`, `CLAUDE.md`, the current
`index.qmd` and `about.qmd`, front matter of every `posts/**/*.qmd`. Detect stock sample posts
(`references/migration.md#sample-posts`). From that, write a compact read in the message text:

```
Site      → ZoneMTL: pick a Montreal neighbourhood by working backwards from school quality
Audience  → parents choosing where to live; the author as builder
Title     → "ZoneMTL"   (repo is mtl-101 — say which you want)
Blurb     → one sentence for website.description and the index lede
Navbar    → Posts · About · GitHub (letsgada/mtl-101)
Posts     → 2 stock sample posts found (welcome, post-with-code)
```

Then **one** `AskUserQuestion` (four questions max):

1. **Read** — `Go (Recommended)` / `Adjust` (corrections under Other). If the title is ambiguous
   (repo name ≠ project name), make this question the title choice instead and treat the rest as
   confirmed unless they say otherwise.
2. **Author line** for `posts/_metadata.yml` — options: the `git config user.email` value, each
   distinct author found in existing posts, `None — per-post front matter`, free text under Other.
3. **About page** — `Keep / scaffold about.qmd` (asks for bio text and links later, keeps
   `profile.jpg` if present) / `Drop it from the navbar` (file is deleted only if it is the stock
   template; a customised one is kept but unlinked).
4. **Links** — `GitHub only, from origin (Recommended)` / `GitHub plus others — list under Other`
   (Bluesky, LinkedIn, …) / `None`.

If sample posts were found, a **second ✋** with exactly these options: `Delete them` /
`Relocate them into the flat posts/ layout` / `Replace them with one hello post drawn from the
brief`. Never decide this silently.

If no brief, README or CLAUDE.md exists, the round instead asks the four design inputs
(content, audience, goal, constraint) plus the title, and the rest follows in a second round.

## 2. Structure (inventory → ✋ table → write → ✋ commit)

Inventory: `_quarto.yml` keys (`theme`, `site-url`, `navbar`, `render`, `output-dir`,
`include-in-header`), whether `index.qmd` carries a `listing:` block, `posts/` layout (subdirs vs
flat, which posts reference local images), `posts.qmd`, `pages/`, `about.qmd`, `_brand.yml`,
`.gitignore` Quarto lines. Present a **create / edit / move / delete table**, one row per file,
and ✋ ask `Apply (Recommended)` / `Adjust — under Other` / `Abort`.

Then write, following `references/migration.md` for every merge and move rule:

- **`_quarto.yml`** → merge toward `assets/_quarto.yml`: `project.type: website`,
  `project.render: ["**/*.qmd"]`, `website.title`, `website.site-url`, `website.description`,
  `website.llms-txt: true`, navbar right = `Posts → posts.qmd`, `about.qmd` if kept, `{icon:
  github, href: https://github.com/OWNER/REPO}`, extra links if given. Set `format.html.theme:
  [cosmo]` for now (step 3 rewires it), keep `css: styles.css`, drop `brand` when no `_brand.yml`
  exists, remove scaffold placeholder hrefs, keep user keys this skill does not own.
- **`index.qmd`** from `assets/index.qmd`: prose from the brief, `toc: false`, a "Start here"
  callout, a "What is here" list linking `posts.qmd` (and `about.qmd`). The old `listing:` block
  and `title-block-banner` go.
- **`posts.qmd`** from `assets/posts.qmd`.
- **`posts/_metadata.yml`** from `assets/posts_metadata.yml`: `freeze: true`,
  `title-block-banner: false`, `author:` if chosen.
- **Posts**: `posts/<slug>/index.qmd` with no local image references → `posts/<slug>.qmd` and the
  empty folder removed; a post that references images in its folder stays where it is. Sample
  posts: per the step-1 answer; "replace" writes `assets/hello.qmd` filled from the brief as
  `posts/hello.qmd` (pick a slug that reads as a title, not `hello`, when the brief suggests one).
- **`about.qmd`**: keep, rewrite the stock template with the user's bio and links, or drop, per
  step 1.
- **`pages/.gitkeep`**; **`.gitignore`** gains `/.quarto/`, `/_site/`, `**/*.quarto_ipynb` if absent.

Show the `_quarto.yml` diff, then ✋ offer a commit ("Restructure site: prose landing page, posts
listing, flat posts/"). If nothing is committed yet, this is the first real commit of the site;
ask in the same offer whether the `.claude/` symlinks should be committed or gitignored.

## 3. Design (invoke `design-derivation`, then wire it → ✋ commit)

Invoke the `design-derivation` skill. Before it asks, state the context it needs in prose so its
read is right the first time: *a Quarto website at the repo root; constraint = light + dark;
tokens live at the project root (`design.md` + `design.tokens.json`); finish = brief only, this
skill does the wiring.* It runs its own rounds: read + deliverable, the colour-scheme check, and
the system check when Full system is chosen. Do not answer them.

When it returns with the two files:

```bash
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py check design.tokens.json
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme light -o theme-light.scss
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme dark  -o theme-dark.scss
```

Then **write `site.scss` fresh** from `references/site-scss.md`: it applies the tokens to Quarto's
components (fonts, navbar, links, prose measure, listing rows, categories, code cells, tables)
using only `var(--token)` values, plus a `$web-font-path` for whichever Google fonts the token
file names. No literal colours; no helper classes the site does not need yet. Wire the theme:

```yaml
format:
  html:
    # Themes are rendered from design.tokens.json; see design.md. Edit the JSON, not the theme-*.scss files.
    theme:
      light: [cosmo, theme-light.scss, site.scss]
      dark: [cosmo, theme-dark.scss, site.scss]
```

`quarto render` once here to catch SCSS errors early. ✋ commit offer ("Add a derived light/dark
theme from design tokens").

## 4. Analytics (invoke `goatcounter-tracking` → ✋ commit)

Invoke the `goatcounter-tracking` skill. Say in prose: the target is `_quarto.yml` under
`format: html:` (`include-in-header: - text: |`), and that the author's other sites report to a
shared dashboard with the hostname-prefix path scheme — but the site code and scheme are its
questions, asked every run. When it returns: `grep -c 'gc.zgo.at/count.js' _quarto.yml` must print
`1`. ✋ commit offer ("Add GoatCounter pageview tracking").

## 5. Publish (invoke `quarto-gh-publish-action`)

Requires `origin`. Without one, report the stage as skipped with the exact
`git remote add origin https://github.com/OWNER/REPO.git` line and "then run
`/quarto-gh-publish-action`", and continue to step 6.

Invoke the skill. Its detect step will find `site-url` present and matching, no navbar
placeholders, and (normally) zero executable cells with `freeze: true`, so its rounds shrink to
confirmations. Recommend in prose: the Pages-via-Actions-artifact mechanism, pinning the detected
Quarto version, and a path filter of `.claude/**`, `CLAUDE.md`, `.gitignore`, `design.md`,
`design.tokens.json` — those last two are not rendered (`render: **/*.qmd`) and do not change the
site, while the `.scss` files do and must stay out of the filter. Its own hand-off question
decides commit / push; this skill adds no commit offer here.

## 6. Verify

```bash
quarto render 2>&1 | tail -5                                    # exit 0
test -f _site/index.html && test -f _site/posts.html && echo pages-ok
grep -c 'gc.zgo.at/count.js' _site/index.html _site/posts.html  # 1 and 1
grep -o 'data-goatcounter="[^"]*"' _site/index.html             # the confirmed endpoint
grep -c 'quarto-listing' _site/posts.html                       # >= 1
grep -c -- '--accent' _site/site_libs/bootstrap/bootstrap*.css  # >= 1 in each theme css
grep -c '<loc>https://' _site/sitemap.xml                       # = number of pages
test -f _site/llms.txt && echo llms-ok
grep -rl '^```{' --include='*.qmd' . | wc -l                    # 0, or _freeze/ is committed
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py check design.tokens.json
git status --short
```

`WARN: Unable to resolve link target` lines are content problems, not setup problems; report them
with file and line and move on.

## 7. ✋ CLAUDE.md, then the report

Ask `Add or refresh the site section in CLAUDE.md (Recommended)` / `Skip`. On yes, fill
`assets/claude-md-section.md` and append it; if `## Site`, `## Commands`, `## Design tokens` or
`## Skills` already exist, replace only those sections. ✋ commit offer.

Final report, in this order: files written or changed per stage; the render result and any
non-fatal warnings; the GoatCounter dashboard URL; the expected site URL and, unless the publish
skill pushed and watched a green run, the one-time instruction verbatim — **Settings → Pages →
Build and deployment → Source: "GitHub Actions"**. Point at `quarto-writeup` as the way to add
posts under `posts/`.

## Things that go wrong

- **Render fails on `theme: [cosmo, brand]`** — the scaffold references `_brand.yml`, which does
  not exist. Step 2 drops `brand`; if it survived, remove it.
- **No tracker or theme on one post** — that post has its own `format:` block, which replaces the
  site's `format.html` (and with it `include-in-header` and `theme`). Delete the block.
- **`include-in-header` ignored** — it sits at the YAML root instead of under `format: html:`.
- **`posts.qmd` lists nothing** — `contents: posts` finds no `.qmd`; usually a half-done flatten
  left `posts/<slug>/index.qmd` next to `posts/<slug>.qmd`. Keep one.
- **CSS and links 404 under `/REPO/`** — `site-url` lacks the `/REPO` subpath or has a trailing
  slash. Fix it; never hand-set `site-path`.
- **`README.md` does not appear on the site** — intended: `render: ["**/*.qmd"]`. A page wanted
  from markdown is renamed to `.qmd`.
- **Token tables in `design.md` reverted** — hand edits between `<!-- tokens:start -->` and
  `<!-- tokens:end -->` are overwritten by `render md --into`. Edit the JSON instead.
- **Fonts fall back to system faces** — `$web-font-path` in `site.scss` does not list the family
  named in `font.display` / `font.body`. Match the Google Fonts URL to the token file.
- **A future session cannot find the sibling skills** — the `.claude/skills/*` entries are
  symlinks into dotfiles on the author's machine. Step 0 recreates them; CLAUDE.md says so.
