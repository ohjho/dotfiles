---
name: design-derivation
description: >-
  Derive the right visual aesthetic for a page, slide, deck, artifact, or
  document by reasoning from content, audience, goal, and constraints — instead
  of picking a look at random. Use this BEFORE styling anything. Fires whenever
  the user wants to style, design, or choose the look of something: "style this
  page", "design a slide about X", "what should this look like", "make it look
  good", "pick colors/fonts/a layout", "give it a visual identity", "design a
  deck/poster/report". Walks a four-step derivation, then hands off to the
  execution skills (frontend-design, artifact-design, theme-factory, dataviz).
---

# Design derivation

An aesthetic is **derived, not chosen from a mood board.** Nobody sensible starts with "let's do dark mode with amber accents." They answer four questions about the *thing being designed*, and the look is what's left once those answers are honest.

When a design feels arbitrary or templated, a step was skipped and someone grabbed a look. When it feels *inevitable* — like every choice had a reason — each choice traces back to one of four inputs. This skill runs that derivation first, then hands the concrete direction to an execution skill to build.

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
Ask: *where does this run, and what can't I use?* Constraints aren't obstacles — they push the design toward coherence.
- *Opens from a `file://` path, no build step* → **single self-contained `.html`, vanilla JS, inline CSS**; "icons" become Unicode glyphs (`→ ⊕ ▲`) and CSS shapes, which happens to reinforce a minimal, typographic feel.
- *Must match an existing brand/system* → adopt its tokens; your job is fit, not novelty.
- *Rendered as a claude.ai artifact* → self-contained, theme-aware, no external assets.

## The keystone choice

One decision is load-bearing — usually the one that falls out of step 1. Identify it, make it boldly, and make **everything else serve it**. In the heatmap example, "color = signal temperature" is the keystone; once color carries meaning it can't also be decorative, which forces a restrained, disciplined palette. Spend your boldness in one place; keep the rest quiet. A design with three "wow" moments has none.

## Interaction protocol: infer, then confirm

Do **not** interrogate the user question-by-question. Infer all four inputs from the request and surrounding context, then show your read in a compact block and invite correction:

```
Content    → attention over image patches (a heatmap concept)
Audience   → ML engineers
Goal       → make signal dilution *felt*, not just described
Constraint → single self-contained .html, opens from disk, no build

Here's my read of your brief — correct anything, or say go.
```

If a field is genuinely unknowable from context and would change the design, ask about that one field only. Once the user corrects or says go, derive the direction.

## From brief → concrete direction

Collapse the four answers into named choices. Keep it a scannable brief, each choice tied back to the input that produced it:

- **Palette** — the colors *and the reason* (e.g. "amber/magenta/steel = the heat ramp, from the content").
- **Type** — the pairing and why (e.g. "mono labels + sans body, from the audience").
- **Layout & rhythm** — structure, density, section pattern (from the goal).
- **Signature move** — the one bold, memorable thing (the keystone) — and what stays restrained around it.

## Two ways to finish — let the user pick

Ask which they want (or infer if obvious):

- **Brief only** — deliver the written design direction above and stop. Good when the user will build it themselves or wants to decide before investing.
- **Build it** — continue into implementation. **Defer execution craft to the skills that already own it** rather than re-deriving it here:
  - `frontend-design` / `artifact-design` — turning the direction into a token system, typography, light/dark themes, and avoiding templated-AI clichés.
  - `theme-factory` — when a pre-set theme fits; use the derived brief to pick or tune one deliberately instead of at random.
  - `dataviz` — for any chart, plot, or dashboard in the piece.

This skill's job is the *reasoning that precedes* those. Don't restate their guidance.

## Self-check

Sanity-test the derivation: **re-derive for a different audience or goal.** Same content, exec audience instead of engineers → mono-everything and a clickable lab would be wrong, and you'd land somewhere calmer and more narrative. If changing an input *doesn't* change the aesthetic, the derivation was too shallow — the look isn't actually rooted in the brief yet.

## Calibrate — don't over-invest

Match effort to the request. A utilitarian memo, plan, or internal note needs one honest pass (readable, structured, unfussy), not a full visual identity. Reserve the full derivation for pieces where the look does real work — something published, persuasive, or meant to teach. Read the request and calibrate the *treatment*; the four questions still apply, the ambition scales down.

## Worked example

The DINOv3 repo's `docs/feature-pooling-tutorial.html` is this method applied end to end:

| Step | Input | Produced |
|------|-------|----------|
| Content | attention over 196 image patches | heatmap metaphor → **palette = heat ramp** (amber hot, magenta mid, steel cold); color carries meaning |
| Audience | ML engineers | **mono for structure + sans for prose**, terminal-adjacent voice |
| Goal | make signal dilution *felt* | an **interactive "lab"** (click patches, drag K, watch weights shift), not an essay |
| Constraint | docs file opened from disk | **single self-contained `.html`**, vanilla JS, no deps; Unicode glyphs as icons |

Keystone: *color = signal temperature.* Everything — dark teal-black grounds so the hot colors glow, the restrained accent set, mono data readouts — serves that one idea. That's why the page reads as inevitable rather than decorated.
