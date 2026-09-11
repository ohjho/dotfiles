# My defaults (fallback only)

Personal conventions for John's projects. **Consult this only after the host project's
`CLAUDE.md`, `README`, and existing posts have said nothing** — anything they specify wins.
Update this file when a default changes; do not copy its values into SKILL.md.

## Author and site

- Author line: `john@greenfly.com`.
- Blog site: the Quarto website at `~/Documents/Git/_miro/ds-experiments` ("Data Science
  Blog"). Posts live in `notebooks/*.qmd` (and `*.ipynb`); the listing is `index.qmd`.
- Publishing is manual and not part of this skill: the user copies the `.qmd` into
  `notebooks/`, runs `quarto render notebooks/<post>.qmd`, and commits the source together with
  the rendered `docs/` on the `dev` branch. Quarto 1.6.x.
- Default drafting destination inside an experiment repo: `blog/<slug>.qmd`, where `blog/` is
  untracked or committed at the user's discretion. Slug pattern seen: `<topic>_<YYYYMM>` or
  `<topic>_<dataset>_<YYYYMM>` (e.g. `vinyaSAM_202608_improvements`, `extract_arena_wisc_mbb_202609`).

## Category vocabulary in use

`VLM`, `video`, `how-to`, `SAM`, `tracking`, `bibby`, `RosterIQ`, `Vinyasa`, `Clipper`,
`ffmpeg`, `LLM`, `CVAT`, `SceneIQ`, `kikz`, `runnertag`, `watermark`, `soccer`, `Overview`,
`intern project`, `presentation`, `auto-annotation`. Reuse before inventing.

## House front matter extras

Same as `quarto-idioms.md` §1 plus, on most recent posts: `code-annotations: hover`,
`lightbox: true` (or explicit `false` for video-heavy posts), and a `crossref.custom` kind —
`Video`/`vid` for video floats, `Card`/`card` for image evidence cards.

## Companion pages and related skills

- Interactive review pages are published with the `surge-artifacts` skill (lives in the
  experiment repo's `.claude/skills/`) at `https://miroai-artifacts-<slug>.surge.sh`, sources in
  `surge_artifacts/<slug>/`. When one exists for the experiment, link it from the post and
  describe its filters instead of reproducing its grid.
- In the blog repo: `post-to-slides` turns a finished post into a Reveal.js deck;
  `hostify-images` / `upload-image` host local images so posts can reference them by URL. Point
  the user at these when local media blocks a post; do not run them from this skill.
- Commit offers: the experiment repos carry a `commit-changes` slash command
  (`.claude/commands/commit-changes.md`) that commits only the changed files with a descriptive
  message. Prefer it over a hand-rolled `git commit`.

## Style preferences learned from edits

- Bare filenames in commands, never `~/Downloads/...` paths.
- Quarto code annotations (`# <1>` + numbered list) instead of inline shell comments.
- Do not restate in prose or tables what an interactive page shows better; keep the tables
  that carry per-model latency, abstention, and other non-visual facts.
- Categories and callout wording are things John adjusts by hand afterwards; keep them short.
- Internal service names (`bibbyd2`, `reknum`, dev CDN hosts) are acceptable in posts; the
  blog is internal.
