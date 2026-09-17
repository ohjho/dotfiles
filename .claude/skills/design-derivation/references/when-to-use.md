# When to use design-derivation, in full

The SKILL.md description is capped at 1024 characters, so it carries a compressed version of
this list. This file is the untrimmed record; read it when unsure whether a request is in scope
or which consumer skill should run afterwards.

## Trigger phrases

Any request to style, design, or choose the look of something:

- "style this page", "make it look good", "what should this look like"
- "design a slide about X", "design a deck / poster / report"
- "pick colors / fonts / a layout", "give it a visual identity"
- "design tokens", "colour palette for this", "a theme for this"
- "theme my Streamlit app", anything touching `.streamlit/config.toml` `[theme]`
- "use my brand colour", "I like this colour", "match our brand"
- a Quarto site, surge page, claude.ai artifact, or app about to be styled with no
  `design.md` / `design.tokens.json` next to it

## Consumer skills that call it first

`surge-artifacts`, `artifact-design`, `frontend-design`, `quarto-writeup`, `quarto-site-setup`,
`dataviz`, `theme-factory`, and any Streamlit app: each needs a palette and type pairing before it
builds, and should run this skill when the token files do not exist yet.

## What a run does (the part trimmed from the description)

Walks the four-step derivation (content → keystone, audience → voice, goal → form,
constraints → shaping); confirms the read and the deliverable (round 1); proposes a colour scheme
and checks it against the user's brand or favourite colour (round 2); for a full system, proposes
the spacing and type scales, shadow, motion and breakpoints with alternatives (round 3); writes
`design.md` and/or `design.tokens.json`, validates with `design_tokens.py check`, and hands off to
the execution skill with the matching `render` command.

## Original description, verbatim (before the trim on 2026-09-17)

Derive the right visual aesthetic for a page, slide, deck, artifact, or document by reasoning from content, audience, goal, and constraints — instead of picking a look at random — and record the result as design tokens (`design.md` and/or a W3C DTCG `design.tokens.json`) that downstream skills consume. Use this BEFORE styling anything. Fires whenever the user wants to style, design, or choose the look of something: "style this page", "design a slide about X", "what should this look like", "make it look good", "pick colors/fonts/a layout", "give it a visual identity", "design a deck/poster/report", "design tokens", "colour palette for this", "theme my Streamlit app" / `.streamlit/config.toml`, "use my brand colour", "I like this colour", or when surge-artifacts, artifact-design, quarto-writeup, dataviz, or a Streamlit app need a palette and type pairing that does not exist yet. Walks a four-step derivation, proposes a colour scheme and checks it against the user's brand or favourite colour, writes the token files, then hands off to the execution skills.
