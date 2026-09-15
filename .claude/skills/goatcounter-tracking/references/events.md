# Optional phase: custom events

Read this only when the user answered "pageviews now, then walk me through custom events" at
kickoff, or asks for events later. Pageviews must already be live and verified — events reuse the
loaded `count.js`.

## What GoatCounter offers

- `goatcounter.count({ path: 'event-name', event: true })` records an event. `title` is optional
  human text. Events show under their own tab on the dashboard, keyed by `path`.
- `data-goatcounter-click="event-name"` on any element records a click without writing JS.
  `count.js` binds these on load via `goatcounter.bind_events()` — **except** under `no_onload` /
  `no_events` (the Streamlit guarded loader), where you call `goatcounter.bind_events()` yourself
  right after `goatcounter.count()` in the `load` handler.
- The `path` **callback** also receives event names. Under the hostname-prefix scheme events come
  out as `host/event-name`, which is usually fine (it keeps apps apart). If the user wants clean
  event names instead, give events a literal app prefix (`extract-arena:filter-changed`) and make the
  callback return `p` unchanged when `p` has no leading `/`.
- Ad blockers that block `count.js` block events too. Always guard: `window.goatcounter &&
  goatcounter.count && goatcounter.count({...})`.

## ✋ Before editing

Ask in one `AskUserQuestion` round:

1. **Which interactions** (multi-select from what you found in the code: filter/sort controls,
   primary buttons, tab switches, downloads, form submits, SPA view changes). Offer at most six.
2. **Event names.** Propose kebab-case names derived from the UI labels (`filter-model`,
   `sort-by-agreement`, `open-crop`), let the user edit under "Other". Names are dashboard keys:
   once live, renaming splits history — say so.

Never bind events without a confirmed list; a page that fires on every keystroke is noise and
quota.

## Per-platform hints

**Static HTML / SPA.** Call inside the existing handler, after the UI change:

```js
btn.addEventListener('click', () => {
  applyFilter(value);
  window.goatcounter && goatcounter.count && goatcounter.count({ path: 'filter-model', event: true, title: value });
});
```

For view changes that do not alter the URL (tabs, modals), an event is right. For SPA routers that
do change the URL (`history.pushState`), record a **pageview** instead on route change:
`goatcounter.count({ path: location.pathname + location.search })` — leave `event` off.

**Quarto.** `data-goatcounter-click="download-csv"` on the link in the `.qmd` (Quarto passes HTML
attributes through), or a small `<script>` block in `include-after-body`. Reveal.js decks: bind on
`Reveal.on('slidechanged', e => goatcounter.count({ path: 'slide-' + e.indexh, event: true }))`
inside `include-after-body` so the deck's own script has loaded.

**Gradio.** Event listeners take `js=` (frontend JS run before `fn`):

```python
run_btn.click(fn, inputs, outputs,
              js="() => { window.goatcounter && goatcounter.count && goatcounter.count({path: 'run-clicked', event: true}); }")
```

Page-load logic goes in `gr.Blocks(js=...)`. In a framed HF Space the iframe variant's `path`
callback still applies, so events are prefixed with the parent host.

**Streamlit.** There is no client-side handler to hook. Emit the event from the Python branch that
runs only when the action happened, with the same one-shot guard as the pageview loader:

```python
if submitted:
    st.html("""<script>window.goatcounter && goatcounter.count && goatcounter.count({path: 'form-submitted', event: true});</script>""",
            unsafe_allow_javascript=True)
```

Because `st.html` re-injects on every rerun, only place this inside a branch that is true for a
single run (a button press, a form submit), never at top level.

**FastAPI / Jekyll / generic.** Same as static HTML: the event call sits in the page's own JS next
to the interaction, or as `data-goatcounter-click` attributes on links and buttons.

## Gotcha: state restored on load fires the same DOM event

A `<details>` whose `open` is restored from `localStorage`, a tab re-selected from the URL hash, a
select set from a saved value — each dispatches the very event you just bound (`toggle`, `change`),
often asynchronously, so a listener attached right after the restore still receives it. That records
one phantom event per returning visitor. Set a flag during the restore and skip the first event when
it is set (see the n200 page's `restoringStrip`), or bind the listener only after the restore has
settled.

## Verify

Open the page, trigger each confirmed interaction once, and check the dashboard's events tab for
one entry per name. `curl` cannot verify events; a browser network tab filtered on `/count?` shows
one request per interaction with `e=true` in the query string.
