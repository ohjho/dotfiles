---
name: quarto-gh-publish-action
description: Set up a GitHub Actions workflow that renders a Quarto website and deploys it to GitHub Pages from a public repo — the deliverable is a generated `.github/workflows/publish.yml`, an optional `site-url` / navbar fix in `_quarto.yml`, and (when pushed) a green first run. Use this whenever the user says "publish the Quarto site", "deploy to GitHub Pages", "set up GitHub Actions for quarto", "gh-pages workflow", "publish.yml", "auto-deploy the blog on push", "enable Pages", or "the site isn't deploying". It detects the repo before asking anything, runs three short question rounds instead of one long one, generates the workflow with a bundled script rather than by hand, renders locally to check the config, never pushes or enables Pages without a yes, and touches GitHub only through `gh` when it is installed and authenticated.
---

# Quarto GitHub Pages Publish Action

Get a Quarto website deploying itself to GitHub Pages on every push. The deliverable is a
`publish.yml` produced by `scripts/render_gh_action_quarto_workflow.py` from the user's answers,
plus the one or two `_quarto.yml` lines that make a project site resolve correctly. Done means:
the workflow file exists, `quarto render` passes locally, and, if the user chose to push with an
authenticated `gh`, the first run is green and the live page serves the site's title.

## Guardrails

- **Fixed assumptions: GitHub Pages, public repo.** Do not ask about hosts or visibility. If
  detection shows `private: true`, stop and say Pages on private repos needs a paid plan.
- **Never skip a ✋ gate because the answer "seems obvious".** A question made moot by detection
  or an earlier answer is *stated as an assumption* in the round's intro text, not silently
  dropped — the user can still override it under "Other".
- **Never overwrite an existing workflow without a diff and Q0.** Render to the scratchpad first.
- **Never `git push`, never `gh api -X POST|PUT`, never `quarto publish`** without the matching
  answer or an explicit yes in that step. Pushing is the user's Round 2 choice; enabling Pages is
  its own ✋ in the hand-off.
- **Post-push services exist only when `gh` passed preflight.** No `gh`, or `gh auth status`
  non-zero → print the manual Settings → Pages instruction and stop after the push. Do not
  install `gh` or ask the user to.
- **Edit `_quarto.yml` only for `site-url` and the navbar placeholders**, and only when asked.
  Themes, formats, render globs, `output-dir` are the user's.
- **Always write the workflow with the script, never by hand**, and run `--self-test` first. The
  script is the template; there is no static `publish.yml` asset to copy.
- **Only `${{ secrets.GITHUB_TOKEN }}`.** No PATs, no secrets in the file, no `enablement: true`.

## 1. Detect (no prompts)

Run from the repo root. Collect facts; act on none of them yet.

```bash
quarto --version                                  # e.g. 1.6.39 → the pin offered in Q3
git remote get-url origin                         # → OWNER/REPO (strip .git; ssh or https)
git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || git branch --show-current
ls .github/workflows/*.yml 2>/dev/null && grep -l 'quarto-actions\|deploy-pages' .github/workflows/*.yml
grep -nE '^\s*(type|site-url|output-dir):' _quarto.yml
grep -nE 'href: https://(github\.com|twitter\.com)/?$' _quarto.yml     # scaffold placeholders
awk '/^ *render:/{f=1; print; next} f && /^ *- /{print; next} f{exit}' _quarto.yml   # render globs
grep -rl '^```{' --include='*.qmd' . | wc -l                           # executable cells
ls -d _freeze 2>/dev/null; git ls-files _freeze | head -1; git check-ignore -q _freeze && echo gitignored
grep -rn 'freeze:' _quarto.yml posts/_metadata.yml 2>/dev/null
command -v gh >/dev/null && gh auth status                              # preflight for step 8
```

If `gh` is authenticated, also run the two inspect commands from `references/gh-cli.md`
(visibility + default branch, Pages status). A user site (`REPO == OWNER.github.io`) serves at the
root URL, not under `/REPO/`.

Work out the **paths-ignore candidates** for Q7: top-level files and directories that Quarto does
not render and that do not affect the site. Start from `.claude/**`, `CLAUDE.md`, `.gitignore`,
then drop anything matched by the `render:` globs — with `**/*.md` in there, `README.md` and
`docs/**` are part of the site. `.github/**` is **never** a candidate: it would block edits to the
workflow itself.

Close with a fixed-format findings block in the message, e.g.:

```
Quarto 1.6.39 · origin OWNER/REPO · default branch main · gh: not installed
Workflows: none
_quarto.yml: type website · site-url missing · output-dir _site (default) · navbar placeholders: github, twitter
Code cells: 0 files · _freeze/: absent · freeze: true (posts/_metadata.yml)
```

`gh:` reads `not installed`, `installed, not authenticated`, or `authenticated as USER → Pages:
disabled | branch gh-pages / | GitHub Actions`.

## 2. ✋ Round 1 — fundamentals

One `AskUserQuestion` call. Free text arrives through the built-in "Other".

**Q0 — Existing workflow.** Only when step 1 found a workflow that mentions `quarto-actions` or
`deploy-pages`. `Regenerate and show me the diff` / `Keep it; only do _quarto.yml and Pages
setup` / `Abort`. With `Keep it`, skip Q1–Q3, Q5, Q7–Q8 and go to step 6 after Round 2.

**Q1 — Deploy mechanism.**

- `Pages via Actions artifact (Recommended)` — the workflow uploads `_site/` as a Pages artifact
  and `actions/deploy-pages` publishes it. No `gh-pages` branch, no rendered HTML in git. Needs
  the repo's Pages source set to "GitHub Actions" once.
- `quarto publish gh-pages` — Quarto's publisher pushes rendered HTML to a `gh-pages` branch; the
  Pages source is that branch. Needs a one-time local `quarto publish gh-pages` first
  (`references/gh-pages-branch.md`).

**Q2 — Triggers** (multi-select).

- `Push to <default branch>` — every commit landing there redeploys.
- `Manual (workflow_dispatch)` — a "Run workflow" button.
- `Pull requests: render-check only, no deploy` — PRs render to catch build errors.
- `Schedule — type a 5-field cron under Other` — periodic rebuilds.

Restate the answers in one line and continue; no second confirmation.

## 3. ✋ Round 2 — workflow details

Open with any assumptions carried in from detection (e.g. "No executable cells and freeze is on,
so I'm recommending no runtime"). Four questions is `AskUserQuestion`'s per-call maximum.

**Q3 — Quarto version.** `Pin to <detected> (Recommended)` — CI renders what the user previews,
bumped deliberately / `Latest stable release` — less upkeep, a Quarto update can change output
without a commit / `Pre-release`.

**Q4 — Site URL.** Options adapt to detection:

- `site-url` absent: `Use https://OWNER.github.io/REPO and add site-url to _quarto.yml
  (Recommended)` (root URL for a user site) / `Custom domain — type it under Other` (adds a CNAME
  step and sets `site-url`; DNS is the user's) / `Default URL, don't touch _quarto.yml`.
- `site-url` present and equal to the derived URL: `Keep existing site-url (Recommended)` plus the
  custom-domain option.
- `site-url` present and different: `Keep <existing>` / `Replace with https://OWNER.github.io/REPO`
  / custom domain. Never overwrite silently.

**Q5 — Runtime for executable cells.**

- `No, keep it minimal (Recommended)` — the tag goes here only when the cell count is 0 **or**
  `_freeze/` is committed with `freeze: true`. Otherwise say plainly that CI would try to execute
  cells with no engine installed, and recommend Python or R.
- `Yes, Python + uv` — installs Python, uv and Jupyter; packages asked in Q10.
- `Yes, R` — installs R, rmarkdown, knitr; extra packages under Other.

**Q6 — Handoff.** `Write and commit, don't push (Recommended)` / `Write only` — leave the file
uncommitted for review / `Write, commit, and push` — triggers the first run; with `gh` the skill
offers to enable Pages first, without it the deploy step fails until the user sets the source.

## 4. ✋ Round 3 — small choices

Open by listing what is *not* being asked and why: Q7 is moot without a push or PR trigger, Q9 is
moot without placeholders, Q10 without Python. Then ask what remains.

**Q7 — Path filter.** `Every push (Recommended)` — simple; note which rendered files (README,
docs) most commits touch anyway / `Skip non-site paths: <computed list>` — the candidates from
step 1 / more or fewer under Other.

**Q8 — Concurrency.** `Let it finish, queue the next (Recommended)` — GitHub's Pages template
default, `cancel-in-progress: false` / `Cancel it, deploy only the newest`.

**Q9 — Navbar placeholders** (only if detected). `Fix the GitHub link` → the real repo URL /
`Fix GitHub and remove the Twitter icon` / `Leave them`.

**Q10 — Python packages** (only if Q5 = Python). `Read from pyproject.toml` / `Read from
requirements.txt` (each only if the file exists) / `Type a list under Other` / `Just Jupyter`.

## 5. Generate the workflow

```bash
uv run <skill-dir>/scripts/render_gh_action_quarto_workflow.py --self-test    # must end "0 failed"
```

Then one call with a flag per answer:

| answer | flag |
|---|---|
| Q1 artifact / gh-pages | `--mechanism artifact` (default) / `--mechanism gh-pages` |
| Q2 push to branch | default; `--branch <name>` when the default branch is not `main`; `--no-push` if unticked |
| Q2 manual | `--dispatch` |
| Q2 pull requests | `--pr-check` |
| Q2 schedule | `--schedule "0 6 * * 1"` |
| Q3 pin / release / pre-release | `--quarto-version 1.6.39` / `--quarto-version release` (default) / `--quarto-version pre-release` |
| Q4 custom domain | `--custom-domain blog.example.com` |
| Q5 none / Python / R | default / `--runtime python` / `--runtime r` |
| Q10 packages | `-p pandas -p matplotlib` or `--python-requirements requirements.txt`; R extras `--r-package tidyverse` |
| Q7 skip paths | `-i '.claude/**' -i CLAUDE.md -i .gitignore` (one `-i` per pattern) |
| Q8 cancel | `--cancel-in-progress` (default is queue) |
| `output-dir` in `_quarto.yml` | `--site-dir docs` (default `_site`) |
| destination | `-o .github/workflows/publish.yml` (default); `-o -` prints to stdout |

The script refuses to overwrite an existing file. When Q0 was `Regenerate`, write to the
scratchpad, `diff -u .github/workflows/publish.yml <scratch>/publish.yml`, show it, then rerun with
`--force`. Exit code `2` means a flag combination was rejected; the message says which — fix the
flags, do not edit the output by hand.

## 6. Edit `_quarto.yml`

Only per Q4 and Q9, following `references/quarto-yml-edits.md` (where `site-url` goes, how to
remove a navbar item cleanly, user-site vs project-site URL). Show the diff.

## 7. Verify locally

```bash
quarto render 2>&1 | tail -5                                       # exit 0
grep -c '<loc>https://' _site/sitemap.xml                           # = number of pages when site-url is set
grep -o 'href="https://github.com/[^"]*"' _site/index.html | head -1  # navbar fix landed (Q9)
```

Replace `_site` with the `output-dir` if it differs. `WARN: Unable to resolve link target` lines
are content problems that predate this skill; report them as pre-existing and non-fatal, with the
file and line from `grep -rn '<target>' *.qmd docs/`. Do not fix them unless asked.

## 8. Hand-off

By Q6:

- **Write only** — list the files, print the `git add … && git commit` the user will run, and
  the one-time Pages instruction below. Stop.
- **Write and commit** — commit only the workflow and `_quarto.yml` (and `_publish.yml` for the
  gh-pages mechanism). Use the host's `commit-changes` skill or slash command when one exists;
  otherwise `git add <files> && git commit`. Never `git add -A`. Print the one-time instruction.
  Stop.
- **Write, commit, and push** — commit as above, then:
  - `gh` authenticated: ✋ ask `Enable Pages (source: GitHub Actions) via gh api now?` showing the
    exact command from `references/gh-cli.md` (POST when disabled, PUT to switch a branch source;
    `build_type=legacy` for the gh-pages mechanism). On yes, run it, confirm with the inspect
    command, then `git push`, `gh run watch --exit-status`, and the curl title check with retries.
    On no, push anyway and say the deploy job will fail until the source is set.
  - no `gh`: `git push`, then print the manual instruction and the expected URL. Stop.

The one-time instruction, verbatim: **Settings → Pages → Build and deployment → Source:
"GitHub Actions"** (or **Source: Deploy from a branch → `gh-pages` / (root)** for the gh-pages
mechanism).

Final report: files written or changed, the exact generator command used (so it can be rerun),
the expected URL, and, when pushed with `gh`, the run's conclusion and the served `<title>`.
Mention as a follow-up, not an action: if the host repo keeps a CLAUDE.md, a line about the
workflow belongs there.

## Things that go wrong

- **`deploy-pages` fails "Get Pages site failed" / "HttpError: Not Found" / "Failed to create
  deployment (status: 404)"** — Pages source is not "GitHub Actions" (disabled, or still a branch).
  Enable it via `gh api -X POST … -f build_type=workflow`, PUT to switch, or the Settings page.
- **CI fails "jupyter not found" / "python3 not found" on a site that renders locally** —
  `_freeze/` is gitignored or `freeze` is off, so the runner re-executes cells. Commit `_freeze/`
  or rerun the skill with a runtime.
- **`sitemap.xml` has relative `<loc>`s, feed/OG links break** — `site-url` missing. Q4.
- **Home page loads but CSS and links 404 under `/REPO/`** — `site-url` lacks the `/REPO` subpath.
  Fix `site-url`; never hand-set `site-path`.
- **`quarto render` prints `WARN: Unable to resolve link target`** — a pre-existing content link,
  not the workflow. Non-fatal; report and move on.
- **Editing `publish.yml` and pushing triggers nothing** — `.github/**` landed in `paths-ignore`.
  Never ignore `.github/`.
- **Push triggers nothing** — every changed file matched `paths-ignore` (intended), or the branch
  differs from `--branch` (regenerate).
- **Set up Quarto step 404s** — version given as `v1.6.39` or a patch that was never released. Use
  the bare `N.N.N` from `quarto --version`, or `release`.
- **"Branch 'x' is not allowed to deploy to github-pages due to environment protection rules"** —
  a dispatch or schedule ran from a non-default branch. Run from the default branch.
- **gh-pages mechanism: "couldn't find remote ref gh-pages" or the publish step hangs on a prompt**
  — no local bootstrap. `references/gh-pages-branch.md`, then commit `_publish.yml`.
- **gh-pages mechanism: run green, site unchanged** — Pages source is "GitHub Actions" while the
  content goes to the branch. Switch the source to `gh-pages` / (root).
- **Custom domain resets to `*.github.io` after a deploy** — no `CNAME` in the output. Keep the
  `Write CNAME` step or add `project: resources: [CNAME]`.
- **First curl after enabling Pages returns 404 or an old title** — propagation. Retry for ~90 s
  before calling it a failure; `gh run watch` already reported the deploy result.
- **Second push "queued" for minutes** — `cancel-in-progress: false` doing its job. Q8 if unwanted.
- **`gh api -X POST …/pages` returns 409 Conflict** — Pages already enabled. Use PUT.
