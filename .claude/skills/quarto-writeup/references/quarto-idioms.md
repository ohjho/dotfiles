# Quarto idioms for write-ups

The recurring building blocks of a data-science blog post in Quarto (HTML output), with a
one-line "use when" for each. Distilled from twenty posts on one site; mirror the host
project's own posts first, and use this as the explanation of what you are mirroring.

## Contents

1. House front matter
2. Options that vary, and when to set them
3. Structural idioms (tables, floats, media, callouts, code, citations, diagrams)
4. Small conventions that make a post look native

## 1. House front matter

Present in nearly every post. Copy it whole; inert options are harmless and keep the site's
CSS and listing behaviour consistent.

```yaml
---
title: "<Title Case, specific: what was tested and on what>"
abstract: <one line the listing page shows; what a reader gets from the post>
date: M/D/YYYY
date-format: full
author: <author line the site uses>
categories:
    - <site vocabulary; see the project's other posts>
format:
    html:
        mermaid:
            theme: forest
            securityLevel: loose
        toc: true
        toc-depth: 3
        toc-expand: 2
        toc-title: Contents
        toc-location: left
        link-external-icon: true
        link-external-newwindow: true
draft: false
execute:
  echo: false
---
```

`execute.echo: false` matters even in a pure-markdown post: it keeps any code cell (mermaid,
python) from echoing its source.

## 2. Options that vary

| option | set it when | note |
|---|---|---|
| `code-annotations: hover` | the post has fenced commands with `# <1>` markers | pairs with the numbered list after the block |
| `lightbox: true` | images are evidence the reader will want to enlarge | set `false` explicitly for video-heavy posts where clicks should not open a lightbox |
| `crossref.custom` | you use custom floats (`::: {#vid-…}`, `::: {#card-…}`) | one entry per kind: `kind: float`, `reference-prefix: Video`, `key: vid` |
| `image: <url>` | you want a specific listing thumbnail | remote URL; otherwise the first `.preview-image` is used |
| `license: "CC BY-NC-SA"` | the site adds it to some posts | copy the neighbours |
| `abstract` | always for listing pages | one sentence |

## 3. Structural idioms

### Captioned table with an id

Use when the reader may compare numbers or refer back. The caption line is the only way the
site captions tables; `.column-page` widens it past the body column.

```markdown
::: {.column-page}
| model | answered | latency mean / median (s) |
|:---|---:|:---|
| `a` | 140 | 4.2 / 2.8 |

: per-model behaviour {#tbl-models}
:::
```

Refer to it in prose as `@tbl-models`. Add `tbl-colwidths="[30,20,50]"` inside the braces when
a column needs room.

### Custom cross-reference float (evidence card / video block)

Use when a group of media plus a caption is a unit the prose refers to. Declare the kind in
`crossref.custom`, then:

```markdown
::: {#card-split .column-page}
::: {layout-ncol=2}
![internal **23** · model A 2 · model B 23](https://…/slice1.jpg)

![internal **3** · model A 3 · model B 23](https://…/slice2.jpg)
:::

One model dissents: `req 8993 · pf 15249` (two players share the crop) and `req 8997 · pf 15303`.
:::
```

The last paragraph inside the outer div is the float's caption. Reference as `@card-split`;
Quarto renders "Card 1". Video floats use `{{< video https://… >}}` as the first cell and
`layout-ncol=3` for video + two stills.

### Media

- Images: `![caption](https://…){height=500}` — remote URL, caption in the alt text; `{height=…}`
  tames tall portraits.
- Video: `{{< video https://….mp4 >}}` — remote only; there is no local-video path on the site.
- Reference-style images for media-heavy posts: `![caption][slug]` in the prose and a block of
  `[slug]: https://…` definitions at the end of the section, so the prose stays readable.
- `.preview-image` on one image or mermaid block per post picks the listing thumbnail.
- Never use `/Users/…`, `~/…`, or relative local paths: they break outside the author's machine.

### Callouts, with semantics

```markdown
::: {.callout-note}
## Fact or definition
:::

::: {.callout-tip}
## Interpretation: what the numbers mean
:::

::: {.callout-important}
## Decision, caveat, or "Bottom line"
:::

::: {.callout-caution collapse="true"}
## Expand for details on `command`'s parameters
- `flag`: what it controls (default: …)
:::

::: {.callout-warning}
## Data caveat the reader must not miss
:::
```

Collapsible caution blocks are the house pattern for parameter references in guides: the
narrative stays short, the detail is one click away.

### Commands with code annotations

```markdown
```bash
uv run main.py extract-df in.csv --out-csv out.csv -m model-a # <1>
uv run main.py parse-results out.csv --out-csv parsed.csv     # <2>
```
1. one call per row; the out-csv is rewritten after every row
2. flattens the stored JSON into wide columns
```

Requires `code-annotations: hover`. Numbers must be contiguous from 1 and each must have a list
item. Use `{.bash filename="scripts/run.sh"}` or `{.yaml filename="config.yaml"}` when the
block is a file rather than a command.

### Footnotes as the bibliography

`[^slug]` in prose with `[^slug]: text and [link](url)` definitions grouped at the end of the
section. No post uses `bibliography:`; footnotes are the citation mechanism. Use them for
sources, asides, and "covered previously in [post](other-post.qmd)".

### Mermaid diagram near the top

```markdown
::: {.column-page}
```{mermaid}
flowchart LR
    A["input CSV"] --> B["extract-df<br/>resumable"] --> C["parse-results"]
    B -. "one call per row" .-> D["hosted models"]
```
:::
```

Use for pipelines and architectures. `%%| label: fig-x` and `%%| fig-cap: "…"` inside the block
make it a referenceable figure. Set `%%{init}%%` colours only when the site theme demands it.

### Embedded charts

`<iframe>` of a published Google Sheets chart (or any hosted chart) for results plots. Prefer it
over a static PNG when the chart is already hosted; otherwise a remote PNG with a caption.

## 4. Small conventions

- Section numbering by hand (`# I: …`, `# II: …`) in guides; plain H1s in experiment posts.
- `{.unnumbered}` on Introduction / Resources headings when the rest are numbered.
- Anchor links to headings: `[Strike](#cloudboom-strike)`.
- Each "Results" subsection that draws a conclusion ends with a `callout-tip` titled
  "Takeaway: …"; the post ends with `callout-important` "Bottom line".
- Ids: `tbl-`, `fig-`, `vid-`, `card-` prefixes; lowercase, hyphenated, unique across the post.
