# The gh-pages branch mechanism

Read this only when Round 1 chose `quarto publish gh-pages`. The workflow the generator emits
(`--mechanism gh-pages`) pushes rendered output to a `gh-pages` branch with
`quarto-dev/quarto-actions/publish@v2`. That action does not create the branch; the user does,
once, from their machine.

## one-time bootstrap (the user runs this, not you)

```bash
quarto publish gh-pages
```

What happens, so you can narrate it and check the result:

1. Quarto asks `Publish site to https://<owner>.github.io/<repo>/ using gh-pages? (Y/n)`, renders
   the site, and creates an **orphan** `gh-pages` branch holding only the rendered files plus a
   `.nojekyll` marker.
2. It pushes that branch and writes `_publish.yml` next to `_quarto.yml`:

   ```yaml
   - source: project
     gh-pages:
       - id: <uuid>
         url: https://<owner>.github.io/<repo>/
   ```

3. It sets the repo's Pages source to the `gh-pages` branch, root folder (via the API if the user
   has `gh` credentials; otherwise it tells them to do it in Settings).

After it finishes:

```bash
git ls-remote --heads origin gh-pages      # one line → the branch exists
git status --short _publish.yml            # ?? _publish.yml → commit it with the workflow
```

`_publish.yml` **must be committed**: the action reads it to know the target. If the user already
has `_publish.yml` from an earlier `quarto publish`, keep it.

## checks before the first CI run

- Pages source is `gh-pages` / `(root)` — `gh api repos/O/R/pages --jq '{build_type,source}'`
  should show `"build_type":"legacy"` and `"branch":"gh-pages"`. If it shows `"workflow"`, the
  branch will fill up but the site never changes; switch it (`gh-cli.md`).
- The workflow has `permissions: contents: write` (the generator sets this) — the action pushes
  with `GITHUB_TOKEN`.
- Output dir: the generator's publish step uses `render: false` after its own `quarto render`, so
  `output-dir` in `_quarto.yml` is honoured automatically; nothing to pass.

## when a `gh-pages` branch already exists from another tool

Jekyll, mkdocs and `peaceiris/actions-gh-pages` all leave a `gh-pages` branch. `quarto publish`
will reuse it and overwrite its contents on the next publish, which is usually what the user wants;
say so before they run the bootstrap. If they want to keep the old site, the target branch is not
configurable in this generator; pick the `artifact` mechanism instead, which never touches branches.

## why prefer the artifact mechanism anyway

Rendered HTML in git history grows the repo on every deploy, the branch is a second source of truth
that can drift from `main`, and PR render-checks need the extra `if:` that the generator emits.
The artifact mechanism has none of that. Offer `gh-pages` only when the user has a reason (an
existing branch-based setup, tooling that reads the branch, or an org policy).
