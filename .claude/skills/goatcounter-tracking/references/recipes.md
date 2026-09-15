# Per-platform recipes

Each recipe: **Locate → Insert → Rebuild / redeploy → Verify → Gotchas.** `SNIPPET` means the
variant chosen in SKILL.md step 3 with the confirmed `ENDPOINT` substituted. The rebuild step is
run by the **user** unless the target is a surge directory (the one deploy this skill performs
itself, after asking).

Rule for every platform: insert **once**, in the file that emits `<head>` or `</body>` for every
page (base template, layout, site config). Per-page insertion is only for a directory of unrelated
static files with no shared layout.

Facts about count.js used below are from https://www.goatcounter.com/help/js — re-read it when a
recipe misbehaves; the library changes rarely but the docs are short.

---

## static-html

Surge pages and SPAs (`surge_artifacts/<slug>/`), plain-HTML GitHub Pages (`docs/*.html` without
a generator), any exported HTML.

**Locate.** Every `*.html` in the directory that is a full page (has `</body>`). A SPA is just
`index.html`; a multi-page export is each page. Never touch `*.js` / `*.css`.

**Insert.** `SNIPPET` on its own line(s) immediately before `</body>`. Keep the file's existing
indentation style. Confirm afterwards with `grep -c 'gc.zgo.at/count.js' <file>` = 1 per file.

**Rebuild / redeploy.**

- Surge (dir has a `CNAME`): ✋ ask "redeploy now?", then from the repo root
  ```bash
  surge ./surge_artifacts/<slug> "$(cat surge_artifacts/<slug>/CNAME)"
  ```
  This is the same command the `surge-artifacts` skill uses; the URL stays stable.
- Plain GitHub Pages: the user commits and pushes; Pages rebuilds in about a minute.

**Verify.** `curl -s https://<domain>/ | grep -o 'data-goatcounter="[^"]*"'` prints the confirmed
endpoint; `curl -s https://<domain>/ | grep -c 'gc.zgo.at/count.js'` prints `1`.

**Gotchas.** A SPA that changes "views" without changing the URL records one pageview per load;
view changes are events (see `events.md`). If the page sets `<link rel="canonical">`, count.js
records that instead of `location.pathname`.

---

## quarto

Quarto websites (John's blog: `~/Documents/Git/_miro/ds-experiments`, `project: type: website`,
`output-dir: docs`, published as GitHub Pages from `docs/`), Quarto books, single `.qmd` posts, and
Reveal.js decks rendered by Quarto.

**Locate.** Site-wide: `_quarto.yml`. Per-post or per-deck: the document's YAML front matter.
Quarto-rendered GitHub Pages: **edit the source, never `docs/` or `_site/`** — the next render
overwrites them.

**Insert.** Under the format key. If `_quarto.yml` has no `format:` block (the blog does not, as of
2026-09), add one at top level:

```yaml
format:
  html:
    include-in-header:
      - text: |
          <script data-goatcounter="ENDPOINT" async src="//gc.zgo.at/count.js"></script>
```

Hostname-prefix variant, same place:

```yaml
format:
  html:
    include-in-header:
      - text: |
          <script>window.goatcounter = { path: function(p) { return location.host + p; } };</script>
          <script data-goatcounter="ENDPOINT" async src="//gc.zgo.at/count.js"></script>
```

Decks: the same `include-in-header` under `format: revealjs:` (per deck in its front matter, or in
`_quarto.yml` if every deck should carry it). If the site already has `format: html:` with other
keys (`theme`, `toc`, …) add `include-in-header` next to them; if it already has
`include-in-header: somefile.html`, append the snippet to that file instead of adding a `text:` entry.

**Rebuild.** User runs `quarto render` (or `quarto preview` to check locally). For the blog the
rendered `docs/` is committed with the source on `dev` (see
`quarto-writeup/references/my-defaults.md`).

**Verify.** Before publish: `grep -c 'gc.zgo.at/count.js' docs/index.html` = 1 and the same on one
post. After publish: the `static-html` curl check against the live site URL.

**Gotchas.** `include-in-header` must sit under `format: html:` (or `format: revealjs:`), not at the
YAML root — at the root Quarto ignores it silently. The `text: |` block is verbatim HTML, so the
snippet is indented under it exactly as shown. A `_quarto.yml` with `format: html:` **and** a
per-post `format:` block: the post's block wins for that post, so a post that overrides `format`
also needs the include (or use a shared `_metadata.yml` in the posts folder).

---

## gradio

Gradio apps and Hugging Face Spaces with `sdk: gradio` in the README front matter.

**Locate.** The `gr.Blocks(...)` or `gr.Interface(...)` constructor in the entry script (`app.py`).
Both accept `head` (custom HTML inserted into the page head) and `head_paths` (one or more HTML
files, concatenated). Prefer `head=` with a module-level constant; use `head_paths=` when the
snippet is shared by several apps.

**Insert.** A plain triple-quoted string — **not** an f-string, or the `{ }` in the JS break:

```python
GOATCOUNTER_HEAD = """
<script data-goatcounter="ENDPOINT" async src="//gc.zgo.at/count.js"></script>
"""

with gr.Blocks(head=GOATCOUNTER_HEAD) as demo:
    ...
```

HF Space: the app is shown inside an iframe at `huggingface.co/spaces/<org>/<name>`, so use the
**iframe variant** (SKILL.md variant C) as the constant: `allow_frame: true` plus a `path` callback
that reads the parent URL from `document.referrer`. The direct `https://<org>-<name>.hf.space` URL
is not framed; the variant's `try/catch` falls back to `location.host + path` there, so one snippet
serves both.

**Rebuild.** Local: restart `python app.py`. Space: user commits and pushes to the Space repo; the
Space rebuilds. `hfs_handler.py` in this repo talks to a Space of this kind — the Space's own
`app.py` is where the snippet goes, not the client.

**Verify.** `curl -s https://<org>-<name>.hf.space | grep -o 'data-goatcounter="[^"]*"'` shows the
endpoint (Gradio renders `head` into the initial HTML). For the framed URL, open it in a browser
and check the dashboard; the recorded path should be `huggingface.co/spaces/<org>/<name>`.

**Gotchas.** Without `allow_frame` GoatCounter drops every hit from the framed Space and the
dashboard stays empty while the direct URL works. `document.referrer` can be empty under a strict
Referrer-Policy; the fallback then records the `*.hf.space` host, which is still distinguishable.
`gr.ChatInterface` wraps Blocks — check its signature for `head` in the installed version before
assuming.

---

## streamlit

**Locate.** The entry script (`app.py` / `streamlit_app.py`), as early as possible: before any
`st.stop()`, auth gate, or branch that may end the run without rendering.

**Insert — modern Streamlit** (`st.html` accepts `unsafe_allow_javascript`; the docs say
"st.html content is not iframed"). Use SKILL.md **variant D**, the guarded loader:

```python
import streamlit as st

GOATCOUNTER_HTML = """
<script>
  if (!window.goatcounter) {
    window.goatcounter = { no_onload: true };
    var s = document.createElement('script');
    s.async = true; s.src = '//gc.zgo.at/count.js';
    s.setAttribute('data-goatcounter', 'ENDPOINT');
    s.addEventListener('load', function () { goatcounter.count(); });
    document.head.appendChild(s);
  }
</script>
"""
st.html(GOATCOUNTER_HTML, unsafe_allow_javascript=True)
```

Why the guard: Streamlit re-executes the script on every widget interaction and `st.html`
re-injects the fragment each time. Without `if (!window.goatcounter)` every rerun appends another
`count.js` and fires another pageview. `no_onload` plus one explicit `count()` in the `load`
handler gives exactly one hit per browser page load. For the hostname-prefix scheme add
`path: function(p){ return location.host + p; }` inside the settings object.

**Insert — older Streamlit** (no `unsafe_allow_javascript`): `components.html` renders in a
sandboxed iframe on a different origin, so use **variant C** (`allow_frame: true`, `path` from
`document.referrer`) and hide the frame:

```python
import streamlit.components.v1 as components
components.html(GOATCOUNTER_IFRAME_HTML, height=0)
```

The iframe is recreated on rerun too; gate the call with
`if "gc_counted" not in st.session_state: ...; st.session_state["gc_counted"] = True` so it fires
once per session.

**Rebuild.** User restarts `streamlit run app.py`, or redeploys on Community Cloud / their host.

**Verify.** `curl` of the page root does **not** show the snippet — Streamlit ships the DOM over a
websocket after load, so the initial HTML is a shell. Verify by (1) `grep -c 'gc.zgo.at' app.py`
= 1, (2) opening the app in a browser with the network tab filtered on `count` and seeing one
request per load, (3) the dashboard. Tell the user this explicitly.

**Gotchas.** Local `streamlit run` hits are ignored by GoatCounter (localhost) unless
`allow_local: true` is added temporarily — remove it before deploy. Multipage apps: the recorded
path is the page's URL path, which is what you want; the guard lives in a shared module imported by
every page.

---

## jekyll

GitHub Pages sites built by Jekyll (`_config.yml`, `_layouts/`, `_includes/`).

**Locate.** Theme `minima` (the GitHub Pages default): `_includes/custom-head.html` — an official
hook included inside `<head>`; create the file if it does not exist. Other themes: the layout every
page uses, usually `_layouts/default.html` — if the theme is a gem and the layout is not in the repo,
copy it out with `bundle info --path <theme>` and edit the copy before `</head>`.

**Insert.** `SNIPPET` verbatim. In `custom-head.html` the file's whole content is the snippet.

**Rebuild.** User pushes (Pages builds), or `bundle exec jekyll serve` for a local check.

**Verify.** The `static-html` curl check against `https://<user>.github.io/<repo>/` (and one inner
page, since layouts can differ).

**Gotchas.** Some themes have their own hook name (`_includes/head/custom.html`, `head-custom.html`
in the Pages themes) — look in the theme's `_includes/` before inventing one. Pages sites with
`plugins:` beyond the allowlist are built by Actions, not Pages; same edit, different rebuild path.

---

## fastapi

FastAPI (or Starlette / Flask — same shape) serving HTML.

**Locate.** Jinja2: `templates/base.html` (or whatever the `{% extends %}` root is) — one place for
all pages. String responses: the `HTMLResponse(...)` literal, or a shared helper that wraps page
bodies.

**Insert.** Jinja2: `SNIPPET` before `</head>`. String responses: append a module-level constant
(plain string, not f-string) to the HTML string before `</body>`. Avoid `{{ }}`/`{% %}` inside the
snippet; the JS braces in variants B–D are fine for Jinja as long as they are not doubled.

**Rebuild.** User restarts `uvicorn app:app` (or the service). Templates reload with `--reload`.

**Verify.** Local: `curl -s http://127.0.0.1:8000/ | grep -o 'data-goatcounter="[^"]*"'`. Deployed:
same against the public URL.

**Gotchas.** Localhost hits are ignored by GoatCounter; the dashboard only moves once the app is
reached via a public host (or `allow_local: true` is set for a test). JSON-only APIs have nothing to
track — say so instead of inserting into a docs page nobody visits.

---

## generic

Nothing above matched.

**Locate.** Find the shared shell:

```bash
grep -rln '</body>\|</head>' --include='*.html' --include='*.htm' --include='*.jinja*' --include='*.j2' --include='*.py' --include='*.js' --include='*.ts*' --include='*.vue' --include='*.svelte' . | grep -v node_modules
```

Pick the one file every page passes through (`index.html` of a Vite/CRA/Next app, a base template,
a layout component). If there are several unrelated ones, ✋ ask which pages to track.

**Insert.** `SNIPPET` before `</body>` (or before `</head>` when the file has no body, e.g. a head
partial). Framework apps that bundle: put the tag in the static `index.html`, not in a component, so
it loads once.

**Rebuild / verify.** The user rebuilds and deploys; then the `static-html` curl check. If the page
is rendered client-side from an empty shell, curl still shows the tag because it lives in the shell.
