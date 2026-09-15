---
name: design-derivation
description: >-
  Derive the right visual aesthetic for a page, slide, deck, artifact, or
  document by reasoning from content, audience, goal, and constraints — instead
  of picking a look at random — and record the result as design tokens
  (`design.md` and/or a W3C DTCG `design.tokens.json`) that downstream skills
  consume. Use this BEFORE styling anything. Fires whenever the user wants to
  style, design, or choose the look of something: "style this page", "design a
  slide about X", "what should this look like", "make it look good", "pick
  colors/fonts/a layout", "give it a visual identity", "design a
  deck/poster/report", "design tokens", "colour palette for this", or when surge-artifacts,
  artifact-design, quarto-writeup, or dataviz need a palette and type pairing
  that does not exist yet. Walks a four-step derivation, writes the token
  files, then hands off to the execution skills.
---

# Design derivation

An aesthetic is **derived, not chosen from a mood board.** Nobody sensible starts with "let's do dark mode with amber accents." They answer four questions about the *thing being designed*, and the look is what's left once those answers are honest.

When a design feels arbitrary or templated, a step was skipped and someone grabbed a look. When it feels *inevitable* — like every choice had a reason — each choice traces back to one of four inputs. This skill runs that derivation first, **records the answer as design tokens** so no downstream skill has to re-derive or re-guess them, then hands the direction to an execution skill to build.

Do this **before** touching color, type, or layout. Deriving takes a minute and saves a redesign.

## The four steps

Work them in order — each one's output constrains the next. For each, name what it *produces*, not just what it is.

### 1. Content, literally → the metaphor / keystone idea
Ask: *what is this, concretely?* The literal subject usually suggests one organizing idea the whole design can serve.
- *Attention weighting over image patches* → "which regions are hot vs. cold" → a **heatmap**. So the palette can *be* the heatmap (hot=signal, cold=ignored). Color now carries meaning, not decoration.
- *A quarterly revenue story* → the shape of a trend → the number and its direction are the hero, everything else recedes.

This step produces the **keystone choice** (see below). Spend the most thought here.

### 2. Audience → the voice
Ask: *who reads this, and what visual language signals "trustworthy / for me" to them?* Match the tools and references they already live in.
- *ML engineers* → the language of editors, terminals, and docs → **monospace for structure** (headings, labels, data readouts, code) + **sans-serif for prose** (mono is tiring to read in long paragraphs). That mono/sans split is a direct answer to "who is reading," not a style whim.
- *Executives* → the language of decks and reports → generous whitespace, one confident headline, restrained palette, narrative over instrument.

### 3. Goal (what they should *do* or *feel*) → the form
Ask: *what is this supposed to accomplish?* Describing a thing and making someone *feel* it call for different forms.
- Goal is *make signal dilution felt* → you can't feel a paragraph → an **interactive lab** (click, drag, watch it change).
- Goal is *let them skim and decide* → a static, scannable layout with clear hierarchy; interactivity would be noise.

### 4. Constraints (where it lives / what's off-limits) → practical shaping
Ask: *where does this run, and what can't I use?* Constraints aren't obstacles — they push the design toward coherence. This step also decides **how many theme states** the tokens need: anything on the web (surge page, artifact, Quarto site) gets light *and* dark; a PDF, poster, or print deck gets one.
- *Opens from a `file://` path, no build step* → **single self-contained `.html`, vanilla JS, inline CSS**; "icons" become Unicode glyphs (`→ ⊕ ▲`) and CSS shapes, which happens to reinforce a minimal, typographic feel.
- *Must match an existing brand/system* → adopt its tokens; your job is fit, not novelty. Look for one first: a `design.tokens.json` or `design.md` next to the deliverable, a CLAUDE.md design section, a theme file.
- *Published on surge.sh* → self-contained, both themes via `prefers-color-scheme`, webfonts allowed (no CSP).
- *Rendered as a claude.ai artifact* → self-contained, theme-aware with `data-theme` guards, no external assets.

## The keystone choice

One decision is load-bearing — usually the one that falls out of step 1. Identify it, make it boldly, and make **everything else serve it**. In the heatmap example, "color = signal temperature" is the keystone; once color carries meaning it can't also be decorative, which forces a restrained, disciplined palette. Spend your boldness in one place; keep the rest quiet. A design with three "wow" moments has none.

## Interaction protocol: infer, confirm, and settle the deliverable in one ask

Do **not** interrogate the user question-by-question. Infer all four inputs from the request and surrounding context, show your read as a compact block in the message text, then ask **one** `AskUserQuestion` that settles everything before any file is written:

```
Content    → attention over image patches (a heatmap concept)
Audience   → ML engineers
Goal       → make signal dilution *felt*, not just described
Constraint → surge page, light + dark, no build step

Here's my read of your brief — the questions below let you correct it.
```

The single `AskUserQuestion` carries up to four questions:

1. **Read** — "Is this read right?" Options: `Go (Recommended)` / `Adjust` (they type the correction under Other). If one input is genuinely unknowable from context *and* would change the design, make this question about that one input instead (e.g. "Who is the audience?" with the two or three plausible answers), and treat the rest of the read as confirmed unless they say otherwise.
2. **Deliverable** — which token files to write. Always offer exactly these three: `design.md + design.tokens.json (Recommended)`, `design.md only`, `design.tokens.json only`. Describe each in one line: md is the human brief with reasons and a token table; JSON is the machine-readable W3C DTCG file the consumer skills render from.
3. **Scope** — `Standard set (Recommended)`: core colour roles, keystone extras, font roles, radius / spacing base / measure. `Full system`: also a spacing scale, type scale, shadows, motion durations, breakpoints. Standard is right for almost every page; full is for an app, a multi-page site, or a design the user will keep extending.
4. **Finish** — `Brief only` (write the files and stop) or `Build it` (continue into the execution skill). Infer and mark the recommended option from the request: "design a page for me" → build; "what should this look like" → brief.

Once answered, derive the direction and write the files. If the user picked `Adjust`, revise the read, show it again in text, and proceed on their say-so without re-asking questions 2–4.

## From brief → concrete direction

Collapse the four answers into named choices. Each choice is tied back to the input that produced it, and that provenance travels into the token files as the `from` column / `$extensions` field:

- **Palette** — the colors *and the reason* (e.g. "amber/magenta/steel = the heat ramp, from the content").
- **Type** — the pairing and why (e.g. "mono labels + sans body, from the audience").
- **Layout & rhythm** — structure, density, section pattern (from the goal).
- **Signature move** — the one bold, memorable thing (the keystone) — and what stays restrained around it.

## Writing the deliverables

**Where.** Next to the thing being designed, so the tokens travel with it and a later session finds them without asking: `surge_artifacts/<slug>/design.md` for a surge page, beside the `.qmd` for a Quarto post, in the artifact's scratch folder for a claude.ai artifact, at the project root for a whole app. If a `design.tokens.json` already exists there, you are *extending* it, not replacing it — read it first.

**The tool.** `scripts/design_tokens.py` in the dotfiles repo validates and renders the JSON. From any other project run it remotely:

```bash
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py check design.tokens.json
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render md   design.tokens.json --into design.md
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render css  design.tokens.json            # surge / plain html
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render css  design.tokens.json --artifact # claude.ai artifact
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme light -o theme-light.scss  # Quarto
```

(Inside the dotfiles repo itself use `uv run scripts/design_tokens.py …`.)

### `design.tokens.json` — the values

W3C DTCG format: every token is `{"$type", "$value", "$description"?, "$extensions"?}`, groups nest freely, a group-level `$type` is inherited. Colours are hex strings and live in **two sets**, `color.light` and `color.dark`, with identical token names; everything else is shared. Record *why* each token exists in `$extensions["design-derivation"]["from"]` as one of `content | audience | goal | constraint`, and put the keystone sentence in the root `$description`.

The **core roles** are a contract — every consumer skill may assume they exist, and `check` fails without them:

| group | required tokens | CSS name the renderer emits |
|---|---|---|
| `color.light` / `color.dark` | `bg surface ink muted line accent accent-soft` | `--bg --surface --ink --muted --line --accent --accent-soft` |
| `font` | `display body` (`mono` strongly recommended) | `--font-display --font-body --font-mono` |
| `radius` | `md` | `--radius-md` |
| `space` | `base` | `--space` |
| `measure` | `body` | `--measure` |

**Keystone extras** are the tokens that carry the design's one idea — `hot/warm/cold`, `offline/runtime/db`, `good/warn/bad`. Add as many as the keystone needs, in both themes, and no more; a `-soft` sibling for tinted backgrounds is a common pair. Dimensions use the object form `{"value": 8, "unit": "px"}`; font families are arrays ending in a generic family.

**Full system** adds, when chosen: `space.xs … space.xl`, `type.xs … type.xl` (font sizes), `shadow.*`, `motion.duration.*`, `breakpoint.*`. Keep the same naming discipline; the renderer joins paths with dashes (`--space-xl`, `--motion-duration-fast`).

`check` enforces light/dark parity, valid hex, and **WCAG AA** contrast: `ink` on `bg` and `surface` ≥ 4.5, `muted` and `accent` on their grounds ≥ 3.0. Extras get warnings only. Fix errors before handing off; a warning on a deliberately decorative extra is fine, say so in `design.md`.

### `design.md` — the reasons

The human brief, structured so a reader can audit every choice:

```markdown
# Design: <slug>
## Derivation        (table: Input | Read | Produces — the four steps)
## Keystone          (one bold sentence, then what it forbids)
## Tokens            (one line on scope + check result, then the markers below)
<!-- tokens:start -->
<!-- tokens:end -->
## Layout & rhythm
## Signature move    (and what stays quiet around it)
## Self-check        (the re-derivation for another audience/goal)
## Handoff           (which consumer skill, which render command)
```

Never hand-type the token tables: run `render md --into design.md` and the block between the markers is filled from the JSON, so the two files cannot drift. With `design.md only`, write the tables by hand in the same shape (token | light | dark | from | note) and skip the markers. See `assets/example.design.md` and `assets/example.design.tokens.json` for a complete pair.

## Handing off — let the consumer skill build

**Defer execution craft to the skills that already own it** rather than re-deriving it here. Point each at the token files and the render command it needs:

- **`surge-artifacts`** — public pages on surge.sh. `render css` gives the `:root` + `prefers-color-scheme: dark` block its theming section requires; paste it at the top of `<style>` and style everything through the variables. The files live in `surge_artifacts/<slug>/`, which is where that skill looks first. The `line`/`surface`/`-soft` tokens are what its cards, rules, and tinted callouts should use.
- **`artifact-design`** / the Artifact tool — claude.ai artifacts. Same CSS with `render css --artifact`, which adds the `:root:not([data-theme="light"])` guard and the explicit `:root[data-theme="dark"]` block the artifact contract needs. Reference webfonts are not allowed there, so check `font.*` fallbacks are system faces.
- **`frontend-design`** — apps and reshaped UI. Hand it the JSON as the token system it would otherwise invent; it owns component craft and anti-cliché judgement from there.
- **`quarto-writeup`** — blog posts and Reveal.js decks. `render scss --theme light` and `--theme dark` produce Quarto theme files (`scss:defaults` mapping `bg → $body-bg`, `ink → $body-color`, `accent → $link-color`, fonts to the Bootstrap font variables, plus every token as a custom property in `scss:rules`). Reference them from `format.html.theme: {light: [cosmo, theme-light.scss], dark: [cosmo, theme-dark.scss]}`.
- **`dataviz`** — any chart in the piece. The keystone extras *are* the chart palette: an ordered set (`hot → warm → cold`) is the sequential ramp, a set of peers (`offline / runtime / db`) is the categorical palette, `accent` is the single-series colour. Point dataviz at them instead of its placeholder palette, and let it run its own contrast validator on both themes.
- **`theme-factory`** — when a pre-set theme fits, use the derived brief to pick or tune one deliberately instead of at random; when none fits, `design.md` *is* the custom theme description its "create your own theme" step asks for, so skip the showcase and apply.
- **`design`** (Claude Design canvas) — paste the Tokens and Signature-move sections of `design.md` into the canvas brief so the artboards start from the derived palette and type.

This skill's job is the *reasoning that precedes* those. Don't restate their guidance.

## Self-check

Sanity-test the derivation: **re-derive for a different audience or goal.** Same content, exec audience instead of engineers → mono-everything and a clickable lab would be wrong, and you'd land somewhere calmer and more narrative. If changing an input *doesn't* change the aesthetic, the derivation was too shallow — the look isn't actually rooted in the brief yet. Write the result into the Self-check section of `design.md`.

## Calibrate — don't over-invest

Match effort to the request. A utilitarian memo, plan, or internal note needs one honest pass (readable, structured, unfussy), not a full visual identity: still write the standard token set (it is cheap and it stops the page inheriting defaults), but the derivation table can be four short lines and the signature move can be "none, on purpose." Reserve the full derivation and the full system for pieces where the look does real work — something published, persuasive, or meant to teach.

## Worked example

`assets/example.design.md` + `assets/example.design.tokens.json` show the method end to end on a hypothetical page: an interactive explainer of how a vision transformer weights image patches, published on surge for ML engineers.

| Step | Input | Produced |
|------|-------|----------|
| Content | attention over ~200 image patches | heatmap metaphor → **palette = heat ramp** (`hot`/`warm`/`cold` extras; `accent` is the hot end); color carries meaning |
| Audience | ML engineers | **mono for structure + sans for prose**, tight 4px radius, instrument-like |
| Goal | make signal dilution *felt* | an **interactive "lab"** (click patches, drag K, watch weights shift), not an essay |
| Constraint | surge page, light + dark, no build | both colour sets, webfont pair, glyph icons, tokens on `:root` |

Keystone: *color = signal temperature.* Everything — teal-black dark ground so the hot colors glow, a cool off-white light ground, the single accent, mono readouts — serves that one idea. `check` passes with 0 errors in both themes. That's why the page reads as inevitable rather than decorated.
