# gh CLI recipes

Read this only when step 1 found `gh` installed **and** authenticated and the user chose to push.
Every command is run from the repo root. `O/R` is `owner/repo` from the git remote. Commands that
change GitHub state are marked ✋ and need the user's yes first; the read-only ones are safe to run
during detection.

## preflight

```bash
command -v gh >/dev/null && echo installed || echo "not installed"
gh auth status            # exit 0 when a token is active; prints the account and scopes
```

Expected: `Logged in to github.com account <user> (keyring)` with `Token scopes` including `repo`
(and `workflow` for pushing a workflow file over HTTPS). Any non-zero exit means "not
authenticated": the skill treats `gh` as absent from here on and prints manual instructions instead.

## inspect

```bash
gh api repos/O/R --jq '{private, default_branch, has_pages, html_url}'
```

```json
{"default_branch":"main","has_pages":false,"html_url":"https://github.com/O/R","private":false}
```

`private: true` → stop; Pages on private repos needs a paid plan and this skill assumes public.

```bash
gh api repos/O/R/pages --jq '{build_type, source, html_url, status, cname}'
```

- Pages disabled: `gh: Not Found (HTTP 404)` — expected on a fresh repo, not an error.
- Enabled for Actions: `{"build_type":"workflow", "source":{"branch":"main","path":"/"}, …}` —
  nothing to do for the `artifact` mechanism.
- Enabled for a branch: `{"build_type":"legacy", "source":{"branch":"gh-pages","path":"/"}, …}` —
  right for the `gh-pages` mechanism; must be switched for `artifact`.

## ✋ enable or switch the Pages source

Ask first; show the exact command in the question. Run **before** the push so the first run can
deploy.

Artifact mechanism, Pages disabled (POST creates the site):

```bash
gh api -X POST repos/O/R/pages -f build_type=workflow
```

Artifact mechanism, Pages already enabled for a branch (PUT updates; returns no body, HTTP 204):

```bash
gh api -X PUT repos/O/R/pages -f build_type=workflow
```

gh-pages mechanism, Pages disabled (the `gh-pages` branch must already exist, see
`gh-pages-branch.md`):

```bash
gh api -X POST repos/O/R/pages -f build_type=legacy -f 'source[branch]=gh-pages' -f 'source[path]=/'
```

Confirm with the inspect command above. POST on an already-enabled site returns
`HTTP 409 Conflict`; use PUT instead.

## push and watch the first run

```bash
git push origin <branch>
gh run list --workflow publish.yml --limit 1 --json databaseId,status,conclusion,url
```

The run appears within a few seconds of the push; if the list is empty after ~15 s, the push did
not trigger it (check `paths-ignore` and the branch name).

```bash
gh run watch <databaseId> --exit-status     # streams job progress; exit 0 only on success
gh run view  <databaseId> --log-failed      # on failure: just the failing step's log
```

Typical failure texts and their meaning are in SKILL.md → "Things that go wrong".

## verify the live site

```bash
gh api repos/O/R/pages --jq .html_url       # https://O.github.io/R/  (or the custom domain)
for i in 1 2 3 4 5 6; do
  title=$(curl -fsSL "<html_url>" | grep -o '<title>[^<]*' | head -1)
  [ -n "$title" ] && { echo "$title"; break; }
  sleep 15
done
```

Expected: `<title><site title from _quarto.yml></title>` within ~90 s. A 404 on the first tries
right after enabling Pages is CDN propagation, not a failed deploy; `gh run watch` already said the
deploy succeeded. Also spot-check one rendered asset so the subpath is right:

```bash
curl -fsSI "<html_url>site_libs/bootstrap/bootstrap.min.css" | head -1   # HTTP/2 200
```

A 404 here with a working home page means `site-url` lacks the `/<repo>` subpath; see
`quarto-yml-edits.md`.
