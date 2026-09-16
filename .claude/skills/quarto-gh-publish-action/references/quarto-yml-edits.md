# `_quarto.yml` edits

The skill touches `_quarto.yml` for exactly two things, both opt-in through the interview:
`site-url` (Round 2, Q4) and navbar placeholders (Round 3, Q9). Nothing else — not themes, not
`format`, not `render` globs. Show the diff after editing.

## site-url

Quarto uses `site-url` for the sitemap, RSS feeds on listing pages, Open Graph / Twitter card
URLs, and to derive `site-path` (the subpath under which assets resolve). Without it, a project
site served under `/<repo>/` still renders, but the sitemap has relative `<loc>` entries and
feeds/OG links break.

| repo | Pages URL | `site-url` |
|---|---|---|
| `<owner>/<repo>` (project site) | `https://<owner>.github.io/<repo>/` | `https://<owner>.github.io/<repo>` |
| `<owner>/<owner>.github.io` (user site) | `https://<owner>.github.io/` | `https://<owner>.github.io` |
| custom domain | `https://<domain>/` | `https://<domain>` |

No trailing slash. Never set `site-path` by hand; Quarto derives it from `site-url`.

Insert it as the first key under `website:`, right after `title:` if present:

```yaml
website:
  title: "My Blog"
  site-url: https://<owner>.github.io/<repo>
```

If `site-url` already exists and matches, leave it. If it exists and differs (an old domain, an
`http://`), Q4 offers `Keep existing` vs `Replace`; never overwrite silently.

## navbar placeholders

Quarto's `quarto create project website` scaffold ships these two placeholder entries:

```yaml
    right:
      - about.qmd
      - icon: github
        href: https://github.com/
      - icon: twitter
        href: https://twitter.com
```

Detection: `grep -nE 'href: https://(github\.com|twitter\.com)/?$' _quarto.yml`. Only offer Q9 when
this matches; a real `href: https://github.com/<owner>/<repo>` is not a placeholder.

- **Fix the GitHub link** → `href: https://github.com/<owner>/<repo>` (from the git remote).
- **Remove the Twitter icon** → delete the two-line `- icon: twitter` item; do not leave an empty
  list item behind. If `right:` becomes empty, delete the `right:` key too.

## output-dir and `--site-dir`

Default `output-dir` for a website is `_site`. If `_quarto.yml` sets `project: output-dir:` to
anything else (commonly `docs` for branch-based Pages), pass that value to the generator's
`--site-dir` so the upload and the CNAME step point at the right folder. Do not change
`output-dir` in `_quarto.yml`; it is the user's layout choice.

A repo with `output-dir: docs` **and** rendered `docs/` committed is a branch-based Pages setup
(source: `main` / `docs`). The artifact mechanism makes that committed folder redundant; mention
it in the hand-off but do not delete it.

## executable cells and `_freeze/`

The runner installs no Python or R unless the user picked a runtime. That is safe when:

- there are no executable cells (`grep -rl '^```{' --include='*.qmd' .` prints nothing), or
- `freeze: true` (or `auto`) is set in `_quarto.yml` / `posts/_metadata.yml` **and** `_freeze/` is
  committed (`git ls-files _freeze | head -1` prints a path).

`freeze: true` never re-executes on the runner; `freeze: auto` re-executes only when the source
changed, so a post edited and pushed without a local render will still need a runtime. When cells
exist and `_freeze/` is absent or gitignored, say so in the Round 2 intro and do not tag
`No, keep it minimal` as recommended.

## custom domain: CNAME

GitHub Pages reads a `CNAME` file at the root of the deployed output. The generator's
`--custom-domain` emits a `Write CNAME` step after `quarto render`, which is enough. The
alternative that needs no workflow step is a committed `CNAME` file in the project root plus:

```yaml
project:
  resources:
    - CNAME
```

Either works; use the workflow step by default because it keeps the domain in one place (the
workflow) and survives a `quarto render` that wipes `output-dir`. DNS (a `CNAME` record to
`<owner>.github.io`, or the four `A` records for an apex) is the user's job; say so once.
