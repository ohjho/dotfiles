# Design: attention-lab

A generic worked example of the design-derivation output. The page is hypothetical: an
interactive explainer showing how a vision transformer weights image patches, published as
a surge page for ML engineers. Its tokens live in `example.design.tokens.json` next to this
file; the tables below were generated from that file with
`design_tokens.py render md --into`.

## Derivation

| Input | Read | Produces |
|---|---|---|
| Content | attention weights over ~200 image patches | a **heatmap** metaphor: colour can *be* the attention map |
| Audience | ML engineers who live in editors and terminals | **mono for structure, sans for prose** |
| Goal | make signal dilution *felt*, not described | an **interactive lab**: click patches, drag K, watch weights move |
| Constraint | surge page, light + dark, no build step | one self-contained `index.html`, tokens on `:root`, glyph icons |

## Keystone

**Colour = signal temperature.** Hot marks what the model attends to, cold marks what it
ignores. Because colour now carries meaning it cannot also decorate: every other colour in
the page stays neutral so the ramp reads as data.

## Colour scheme

Proposed in round 2: the heat ramp as above, accent = the hot end, cool hue-biased neutrals.
The user had no brand or favourite colour to bring, so the proposal stands unchanged. Had
they supplied one, its role would have been asked (accent / background / extra / ink) and
`design_tokens.py scheme <hex>` would have rebuilt the seven core roles around it.

## Tokens

Standard set (core roles + keystone extras). The three font tokens carry `faces` entries
(Google Fonts woff2 URLs) so the Streamlit render can load IBM Plex. Both themes checked with `design_tokens.py check`: 0 errors. Standard set, so there is no `## System` section; a full-system run adds one after `## Colour scheme` with the round-3 outcome.

<!-- tokens:start -->
| token | light | dark | from | note |
|---|---|---|---|---|
| bg | `#F3F5F4` | `#0E1A1D` | constraint | cool off-white so the hot ramp stays legible |
| surface | `#FFFFFF` | `#152428` | constraint |  |
| ink | `#17232B` | `#E6EDEF` | audience |  |
| muted | `#5B6B74` | `#93A5AC` | audience |  |
| line | `#D8DFE2` | `#27383D` | constraint |  |
| accent | `#B0480B` | `#F2A13B` | content | the hottest step of the ramp doubles as the accent |
| accent-soft | `#F7E4D6` | `#3A2A12` | content |  |
| hot | `#B0480B` | `#F2A13B` | content | high attention |
| warm | `#A6367A` | `#E06AB8` | content | mid attention |
| cold | `#4B6A8A` | `#7FA0C0` | content | ignored patches |

| token | value | from | note |
|---|---|---|---|
| font-display | `"IBM Plex Mono", ui-monospace, monospace` | audience | mono for structure: headings, labels, readouts |
| font-body | `"IBM Plex Sans", system-ui, sans-serif` | audience | sans for prose; mono tires in paragraphs |
| font-mono | `"IBM Plex Mono", ui-monospace, monospace` | audience |  |
| radius-md | `4px` | audience | tight corners, instrument-like |
| space | `8px` | goal |  |
| measure | `68ch` | goal |  |
<!-- tokens:end -->

## Layout & rhythm

One column at `--measure` for prose; the lab breaks out to full width. Sections are short
and alternate explanation → instrument → readout, so the reader always tries the thing
they just read about. Density is high but every readout is set in mono with tabular
figures, which is the audience's native reading mode.

## Signature move

The patch grid *is* the palette swatch: the hot/warm/cold ramp appears nowhere else on the
page except the grid and the single accent. No gradients, no illustration, no second
accent. Restraint everywhere else is what lets the one bold idea land.

## Self-check

Same content for an exec audience → the mono headings and the clickable lab would be
wrong; you would land on a calm narrative page with one static heatmap figure and a
sans display face. The inputs change the look, so the derivation is rooted in the brief.

## Handoff

- **surge-artifacts**: `design_tokens.py render css example.design.tokens.json` → paste into `<style>` of `surge_artifacts/attention-lab/index.html`.
- **dataviz**: use `hot → warm → cold` as the sequential ramp for any attention chart; `accent` is already the hot end, so charts and page agree.
- **Streamlit** (if the lab were a Streamlit app instead): `design_tokens.py render streamlit example.design.tokens.json --into .streamlit/config.toml` → see `example.streamlit.config.toml` for the result.
