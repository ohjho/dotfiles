---
name: quarto-writeup
description: Draft a Quarto `.qmd` blog post or write-up that documents an experiment run, a tool, or an analysis from its real artifacts (result CSVs, CLIs, published review pages, git history) in the project's house style. Use this whenever the user wants to "document", "write up", "blog about", "summarize the run", "do a post-mortem", "turn this into a post", or mentions quarto / .qmd / the data-science blog — even when they never say "blog" and even when the artifacts are scattered across Downloads, a published review page, and a repo. It recomputes every number from the data, interviews the user before writing, drafts from a bundled template, lints without rendering, and stops at the draft so the user renders and publishes.
---

# Quarto Write-up

Turn finished experiment work into a `.qmd` post that a teammate can read months later and
trust. The deliverable is a **drafted, lint-clean `.qmd`** in the host project. Rendering,
copying into the blog site, and publishing stay with the user — they know their site's
build; you don't. What you own is that every number, command, and claim in the draft is
traceable to an artifact you actually opened.

## Where this ends, and what is sacred

- The output is one `.qmd` (default `blog/<slug>.qmd` in the current repo). Do not render it
  and do not copy it anywhere. Offer a commit at the end; never commit without a yes.
- Once the user edits the file, **their edits win**. Before any follow-up change, re-read the
  file and `git diff` / `git log -p` it so you see what they changed, then work around it.
  Restructuring on request is fine; silently restoring a deleted paragraph is not.

## 1. Orient: whose house style is this?

Read the host project's `CLAUDE.md` and `README` for anything about a blog: destination
folder, an example post, author line, categories, render/publish steps. Then look for a prior
`.qmd` in the repo (often `blog/`) and mirror its front matter and idioms — a post that looks
like its neighbours is read as part of the site, one that doesn't is read as a draft.

If the project says nothing, open `references/my-defaults.md` for the user's usual defaults.
Treat that file as a fallback, not a rule: project conventions always override it.

Then pick the archetype and copy the matching template from `assets/`:

| tell-tale signs | archetype | template |
|---|---|---|
| a batch was run, there are result files, tables and evidence images/videos, "did X beat Y" | experiment run write-up | `assets/experiment.qmd` |
| commands to reproduce, parameters to explain, "how do I", numbered stages | how-to / guide | `assets/howto.qmd` |
| opinions, trends, a proposal, sections of argument with many citations, few tables | roadmap / opinion | `assets/roadmap.qmd` |

`references/quarto-idioms.md` explains every idiom the templates use and when each one earns
its place. Read it once per post; skim it again when you're unsure whether a table needs an
id or a callout should be a tip or a note.

## 2. Gather evidence before writing a word

A write-up is only as good as the artifacts behind it, so find them all first:

- **Data and results**: input CSVs, result CSVs, parsed/wide tables, JSON blobs. Note row counts,
  columns, and which file is derived from which.
- **The code that produced them**: the CLIs and their options. `git log` gives you dates and,
  through commit messages and CLI help, the commands that were actually run. Ask the user for
  the exact invocation when the history is ambiguous — a post that shows the wrong flags is
  worse than one that shows none.
- **Published companions**: review pages, dashboards, demo spaces. Fetch them (`curl -sI`) so
  you can link only what is live and describe what the page actually shows.

**Recompute every statistic yourself** with a throwaway script in the scratchpad, reading the
result files directly. Never lift a number from memory, a chat summary, or a column you did not
inspect. Why this matters: in the run this skill was distilled from, one model alternated the
spelling of its JSON keys, so the pre-computed "agreement" column undercounted by six rows;
only a recount that coalesced the two spellings caught it. Keep the script — you will rerun it
when the user asks for a different cut.

**Look at the media.** Download a handful of candidate images or frames to the scratchpad,
thumbnail them (`sips -Z 700` on macOS, `convert -resize` elsewhere) and view them. Pick
examples a reader can actually read; a blurry crop illustrates nothing. Media in the post is
referenced by **remote URL only**. Local-only media is a blocker to raise with the user, not
something to path in from their home directory — those links break the moment the post leaves
their machine.

## 3. Interview the user, then state your assumptions

Ask before drafting, in one round when possible (use `AskUserQuestion` when interactive).
Always cover these six, because different answers produce materially different posts:

1. **Destination and filename** — folder in this repo, slug, date.
2. **Where the data comes from** — which files are canonical, which are pilots or scratch.
3. **Framing and allowed claims** — is there ground truth? Is this an accuracy measurement or an
   audit? May the post judge examples ("the model was right") or only report what each source
   said? This single question changes the title, the tables, and every caption.
4. **Scope** — side experiments, pilots, cost, latency, companion pages: in or out.
5. **Example selection** — show the candidates you picked (ids, what each shows) and let the
   user swap before writing. They know which cases matter.
6. **Anything they want added** — open field; people usually have one thing in mind.

Everything else, decide yourself and list as assumptions in the same message (author,
categories, mermaid yes/no, table set). Saying "I assumed X" once is cheaper than a rewrite.

## 4. Draft

Copy the template, then fill it in order. Rules, each with its reason:

- **Front matter mirrors the house style** exactly, including options that look inert
  (mermaid theme with no diagram, crossref kinds with no floats): the site's CSS and listing
  page rely on them. Date is today unless the user says otherwise.
- **Commands appear exactly as run**, with bare filenames rather than `~/Downloads/...` paths
  (readers have their own folders), and with Quarto code annotations (`# <1>` in the block, a
  numbered list right after) instead of shell comments — annotations render as hover notes and
  keep the command copy-pasteable.
- **Show one raw result** in a fenced block. A reader who sees the data shape trusts the tables
  that follow and can reproduce the parsing.
- **Tables only where they carry information a companion page cannot.** If an interactive
  review page exists, link it, describe its filters and what each control reveals, and do not
  reproduce its grid or its headline counts as prose tables — the user cut exactly that from the
  source post as redundant. Per-model latency, abstention rates, and other things a card grid
  cannot show are what the tables are for.
- **Evidence cards** are custom cross-reference floats (`::: {#card-… .column-page}` with a
  `layout-ncol` block and a caption paragraph), referenced from prose as `@card-…`. Captions
  state what each source said (`internal 4 · model A 32 · model B 32`), never who is right,
  unless the user explicitly allowed verdicts in step 3. Observable facts about the image
  ("two players share the crop") are fine; judgements are not.
- **Callouts carry semantics**: `note` for a fact or definition, `tip` for an interpretation,
  `important` for a decision or a caveat the reader must not miss, `caution collapse="true"`
  for an expandable parameter reference. Mixing them up trains readers to skip them.
- **Numbers in prose stay few**; anything the reader might compare goes in a table with an id
  and a caption. Percentages sit beside their counts.
- **Close with** a Conclusion of bulleted findings, a numbered "next steps", and a
  `callout-important` titled "Bottom line" with the one decision the post supports.

Keep prose specific: name the model, the file, the flag. Avoid narrating your own process
("I then computed…"); the post is about the experiment, not the drafting.

## 5. Check without rendering

Run the bundled linter and fix everything it reports:

```bash
python3 <skill-dir>/scripts/check_post.py blog/<slug>.qmd
```

It parses the front matter, matches every `@ref` to an `{#id}`, flags duplicate ids, tables
without a captioned id, code annotations without their numbered list, home-directory or local
media paths, and every remote URL that does not return 2xx/3xx (`--offline` to skip network).
It does not render — the user will, in their own site, where the theme and listing live.

## 6. Hand off

Report, in this order: the file path; the headline numbers and where each came from; the
assumptions and judgement calls (framing, examples chosen, anything left out and why). Then
offer a commit: if the host project has a commit skill or slash command (e.g. `commit-changes`),
invoke that; otherwise propose `git add <file>` with a descriptive message. Wait for a yes.

## 7. When the user comes back with edits

Re-read the file and diff it first (see "sacred" above). When asked to remove or merge sections,
also repair what depends on them: dangling `@card-`/`@tbl-` references in other sections, a
"see table below" that now points nowhere, a conclusion bullet quoting a deleted number. Re-run
the checker, and re-run your stats script if any number changed. Report what you removed, what
you moved, and what you rewrote so the user can verify their own edits survived.
