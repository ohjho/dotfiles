---
name: goatcounter-tracking
description: Add GoatCounter pageview analytics (goatcounter.com) to any web thing this repo produces or the user points at — surge-published HTML pages and SPAs, Quarto websites and Reveal.js decks, Gradio apps / Hugging Face Spaces, Streamlit apps, GitHub Pages (Jekyll, plain HTML, Quarto docs/), FastAPI templates, or anything else that emits <head>/</body>. Use this whenever the user mentions "goatcounter", "analytics", "track visits" / "track pageviews" / "page views", asks "who is looking at this page", or says "add tracking to the app / blog / space / page / deck". It always asks which GoatCounter site to send to and how to keep apps apart on one dashboard before editing anything, updates an existing snippet instead of duplicating it, only redeploys surge pages itself, verifies the live page, and never embeds tokens or fires synthetic hits.
---

# GoatCounter tracking

Put one small `<script>` in the right place so a page, app, or site reports pageviews to a
GoatCounter dashboard, then prove it is live. Pageviews first; custom events are an optional
second phase (`references/events.md`).

Two rules override everything else in this file:

1. **Always ask which GoatCounter site.** The site code (`jho` → `https://jho.goatcounter.com/count`)
   or self-hosted endpoint is the user's to pick, every run, even when memory, `.env`, or an
   existing snippet in the repo already names one. Known values are *offered as options with their
   source*; nothing is written until the user picks. Never skip a ✋ step because the answer "seems
   obvious".
2. **Never duplicate.** A page must end up with exactly one `count.js` tag. Detect existing
   snippets before inserting and offer to update them.

What is safe to write down: the site code. It is public by design (it sits in every page's source),
so it may live in committed files. What is never written: GoatCounter API tokens (this skill needs
none) and synthetic hits (verification is by reading the served page, not by counting fake views).

## 1. Detect the target (no prompts)

Look at the working directory and anything the user pointed at. Collect **candidates**; do not act
on them yet.

| look for | target | recipe anchor |
|---|---|---|
| `surge_artifacts/*/CNAME` next to an `index.html` | surge static page / SPA | `recipes.md#static-html` |
| `_quarto.yml` (`project: type: website` / `book`, or `format: revealjs`); a lone `*.qmd` without one → per-post front matter | Quarto site / deck | `recipes.md#quarto` |
| `gradio` in `pyproject.toml` / `requirements.txt`, or `gr.Blocks(` / `gr.Interface(` in `*.py`; a `README.md` with `sdk: gradio` front matter → HF Space (framed) | Gradio / HF Space | `recipes.md#gradio` |
| `streamlit` dependency, `import streamlit`, or a `.streamlit/` dir | Streamlit | `recipes.md#streamlit` |
| `_config.yml` with `_layouts/` or `_includes/`, or `theme: minima` | Jekyll GitHub Pages | `recipes.md#jekyll` |
| `docs/index.html` with `site_libs/` or `.nojekyll` | Quarto-rendered GitHub Pages — edit the **source**, never `docs/` | `recipes.md#quarto` |
| `docs/*.html` with no generator | plain-HTML GitHub Pages | `recipes.md#static-html` |
| `fastapi` dependency with `templates/*.html`, or `HTMLResponse(` | FastAPI | `recipes.md#fastapi` |
| none of the above | generic shell | `recipes.md#generic` |

For each candidate also run `grep -rn "goatcounter" <its files>` and note any existing snippet with
file and line — it feeds step 4 and is shown in the kickoff question.

Also gather the **known sites**, each with its source, for step 2:

- memory: `goatcounter-site.md` in this project's memory directory, if present;
- `.env`: a `GOATCOUNTER_SITE` or `GOATCOUNTER_ENDPOINT` line, if present (read the key, never print
  other lines);
- the repo: `grep -rho 'data-goatcounter="[^"]*"' . | sort -u` (skip `node_modules`).

Dedupe identical values; keep every source label.

## 2. ✋ Kickoff — one `AskUserQuestion` round

Single-select questions; free text arrives through the built-in "Other".

**Q1 — GoatCounter site.** Options, in this order, only for sources that exist:

- `<value>  (from memory: goatcounter-site.md)`
- `<value>  (from .env GOATCOUNTER_SITE)`
- `<value>  (already in <file>:<line>)`
- always: `A different goatcounter.com site code — type it under Other (e.g. jho)`
- always: `Self-hosted / custom-domain endpoint — paste the full …/count URL under Other`

With no known value only the last two appear. A bare code becomes
`https://<code>.goatcounter.com/count`; a pasted URL is used verbatim (must end in `/count`). This
question is asked on every run, including reruns on a page that already carries a snippet.

**Q2 — Keep apps apart on one dashboard.** GoatCounter records only the URL path by default, so two
deployments sharing a site both show up as `/`.

- `Prefix the recorded path with the hostname` — recommended when several deployments share one
  site; records e.g. `miroai-artifacts-foo.surge.sh/`.
- `Separate GoatCounter site code for this app — type it under Other` — the site must already exist
  in the account; this skill cannot create sites. Replaces Q1's endpoint for this run.
- `Plain path (stock behaviour)` — fine when the site serves one deployment.

**Q3 — Confirm target.** Only when step 1 found zero or two-plus candidates. One option per
candidate, naming the file it would edit and marking `already has a snippet at <file>:<line>` where
true, plus rely on "Other" for a path you missed. With exactly one candidate, state it in the
question text as the assumption ("I'll edit `surge_artifacts/<slug>/index.html`") instead of asking.

**Q4 — Events.** `Pageviews only` (default) / `Pageviews now, then walk me through custom events`.

Restate the four answers in one line and proceed — no second confirmation.

## 3. Build the snippet

`ENDPOINT` is the confirmed `…/count` URL. Settings live in `window.goatcounter` **before**
`count.js` loads (or in a `data-goatcounter-settings` JSON attribute — never both). The `path`
setting may be a callback: it receives the default path (`<link rel=canonical>` if present, else
`location.pathname + location.search`) and returns what to record; returning `null` records nothing.
Source: https://www.goatcounter.com/help/js.

| target | scheme | variant |
|---|---|---|
| any non-framed page | plain | **A** |
| any non-framed page | hostname prefix | **B** |
| HF Space embed, old Streamlit `components.html`, any iframe | either | **C** (swap `u.host + u.pathname` for `u.pathname` under plain) |
| Streamlit `st.html` | either | **D** (uncomment `path` for prefix) |

**A — stock**
```html
<script data-goatcounter="ENDPOINT" async src="//gc.zgo.at/count.js"></script>
```

**B — hostname prefix**
```html
<script>window.goatcounter = { path: function(p) { return location.host + p; } };</script>
<script data-goatcounter="ENDPOINT" async src="//gc.zgo.at/count.js"></script>
```

**C — inside an iframe.** `location` is the frame's own URL; the parent page is only available as
`document.referrer`. GoatCounter drops framed hits unless `allow_frame` is set.
```html
<script>
  window.goatcounter = {
    allow_frame: true,
    path: function(p) {
      try { var u = new URL(document.referrer); return u.host + u.pathname; }
      catch (e) { return location.host + p; }
    }
  };
</script>
<script data-goatcounter="ENDPOINT" async src="//gc.zgo.at/count.js"></script>
```

**D — Streamlit `st.html`, guarded.** Not framed, but re-executed on every rerun, so load once and
count once.
```html
<script>
  if (!window.goatcounter) {
    window.goatcounter = { no_onload: true /*, path: function(p){ return location.host + p; } */ };
    var s = document.createElement('script');
    s.async = true; s.src = '//gc.zgo.at/count.js';
    s.setAttribute('data-goatcounter', 'ENDPOINT');
    s.addEventListener('load', function () { goatcounter.count(); });
    document.head.appendChild(s);
  }
</script>
```

`references/recipes.md` shows the Quarto YAML form (indented under `include-in-header: - text: |`)
and the Python string form (plain triple-quoted constant, never an f-string, so the JS braces
survive).

## 4. ✋ Idempotency

If step 1 found a snippet in the target, show the exact line(s) and ask:

- `Update it to the confirmed endpoint and scheme` — replace the whole existing block (the tag and
  any adjacent `window.goatcounter = …` script) with the new variant.
- `Leave it as is` — stop here and report.
- `Abort`.

Also grep the served/rendered output when one exists (`docs/`, `_site/`, `dist/`): a snippet that is
only in build output means the source is elsewhere — find it before editing.

## 5. Insert

Follow the recipe anchor for the target in `references/recipes.md`. The shared rule: insert **once**,
in the file that emits `<head>` or `</body>` for every page (base template, layout, `_quarto.yml`,
`gr.Blocks(head=…)`), and only per page when the pages share nothing. Preserve the file's
indentation; put the snippet on its own line(s) immediately before `</body>` unless the recipe says
head. Then `grep -c 'gc.zgo.at/count.js' <file>` must print `1` for every edited file.

## 6. Deploy, or hand off

- **surge directory** (has a `CNAME`): ✋ ask "redeploy now?". On yes, from the repo root:
  ```bash
  surge ./surge_artifacts/<slug> "$(cat surge_artifacts/<slug>/CNAME)"
  ```
  This is the only deploy this skill performs. Before it, run the privacy grep the `surge-artifacts`
  skill requires (internal hostnames, bucket names) — the page is public.
- **everything else**: print the exact rebuild / restart / push command from the recipe and wait for
  the user to run it. Do not run `quarto render`, `git push`, or restart services yourself.

## 7. Verify

Against the live URL (or the locally served page when nothing is deployed):

```bash
curl -s <url> | grep -o 'data-goatcounter="[^"]*"'   # must print the confirmed ENDPOINT
curl -s <url> | grep -c 'gc.zgo.at/count.js'          # must print 1
```

For framed targets also `grep -c allow_frame` = 1. **Streamlit is the exception**: the DOM arrives
over a websocket, so curl shows a shell without the snippet; verify the source file, a browser
network tab filtered on `count`, and the dashboard instead — and say so.

Then tell the user: open the page once and look at `https://<site>.goatcounter.com` (or the
self-hosted dashboard); the hit appears within seconds. Mention:

- localhost and private-network hits are ignored unless `allow_local: true` is set (dev testing only,
  remove before deploy);
- appending `#toggle-goatcounter` to the page URL and reloading excludes that browser; Settings →
  Tracking → Ignore IPs does it server-side;
- ad blockers block `count.js`; missing hits from such visitors are expected.

## 8. ✋ Optional — custom events

Only if Q4 said yes. Read `references/events.md`; it has its own confirmation step for interaction
list and event names.

## 9. Hand-off

Report: endpoint used, path scheme, every file changed, the live URL with the verification result
(or "after you run `<command>`, check with `<curl line>`"). Offer the `commit-changes` command for
tracked files; note that `surge_artifacts/` is gitignored, so a surge-only change has nothing to
commit. If the user picked a site not yet in memory, *suggest* saving it to `goatcounter-site.md`
and do so only on a yes.

## Things that go wrong

- **Streamlit counts one pageview per widget click** — the guard from variant D is missing, or the
  loader sits inside a branch that reruns. Every rerun re-injects `st.html`.
- **HF Space dashboard shows `/` for everything, or nothing** — `allow_frame` missing (nothing), or
  `path` not derived from `document.referrer` (`/`). Under a strict Referrer-Policy the referrer is
  empty and the fallback records the `*.hf.space` host, which is still distinguishable.
- **Quarto renders without the tag** — `include-in-header` sits at the YAML root instead of under
  `format: html:` (or `format: revealjs:`), or a post overrides `format:` and drops the include.
- **Jekyll theme has no `custom-head.html`** — hooks are theme-specific; look in the theme's
  `_includes/` (`head-custom.html`, `head/custom.html`) or edit the copied layout.
- **Two `count.js` tags** — an earlier hand-added snippet plus the new one. Step 4 exists to prevent
  it; the fix is to delete one.
- **Dashboard empty during a local test** — you are on localhost; that is GoatCounter working as
  designed, not a bug.
