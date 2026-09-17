# Migrating an existing Quarto repo to the alhaka shape

Read this in step 2, after the inventory and before the ✋ table. Every rule below produces one
row in that table; nothing here runs before the user says Apply.

## Inventory checklist

| look at | note |
|---|---|
| `_quarto.yml` | `project.type`, `render`, `output-dir`, `site-url`, `navbar` entries, `format.html.theme`, `css`, `include-in-header`, anything else (`editor`, `execute`, `author`) |
| `index.qmd` | has a `listing:` block? (→ it is the scaffold's blog index) `title-block-banner`? body text? |
| `posts/` | `_metadata.yml`; each post: subdir with `index.qmd` or flat `.qmd`; does the body reference a local file (`image:` in front matter, `![](file)`, `<img src="file">`, `{{< video file >}}`)? |
| `posts.qmd`, `pages/`, `about.qmd`, `profile.jpg`, `_brand.yml`, `styles.css` | exists? stock or customised? |
| `.gitignore` | `/.quarto/`, `/_site/`, `**/*.quarto_ipynb` present? |

## `_quarto.yml` merge rules

- **Keep** every key this skill does not own: `editor`, `execute`, `output-dir`, `author`, custom
  `format` options, existing `include-in-header` file references (the goatcounter skill appends to
  that file rather than adding a second include).
- **Set** `project.render: ["**/*.qmd"]` (add, or extend an existing list that lacks it),
  `website.title`, `website.site-url`, `website.description`, `website.llms-txt: true`.
- **Rebuild** `website.navbar.right` from the step-1 answers: `Posts → posts.qmd`, `about.qmd`
  if kept, the GitHub icon with the real repo URL, extra links if given. Anything else the user had
  in the navbar (a custom page) stays, in its original position, and is called out in the table.
- **Placeholders** to remove or replace: `href: https://github.com/`, `https://bsky.app/`,
  `https://twitter.com`, `https://linkedin.com` with no path; `site-url:
  https://your-website-url.example.com`; `description: "A blog built with Quarto"`.
- **`format.html.theme`**: replace whatever is there with `[cosmo]` in step 2 (step 3 rewires it
  to the light/dark block). Drop `brand` unless `_brand.yml` exists; if it does exist, keep it and
  say so — design-derivation should then extend that brand rather than invent a palette.
- **Show the diff** (`diff -u` against the original) before the commit offer.

## `index.qmd`: listing → prose

The scaffold's `index.qmd` is only front matter with a `listing:` block. Its `listing:` moves to
`posts.qmd` (the asset already has the alhaka settings plus `feed: true` so RSS keeps working);
`title-block-banner` and `page-layout: full` are dropped from `index.qmd`. If the existing
`index.qmd` has body prose, keep it and fold it into the asset's structure instead of replacing it.

## Posts: subdir → flat

Rule: a post at `posts/<slug>/index.qmd` that references **no** local file moves to
`posts/<slug>.qmd` and its folder is removed. A post that references a local image, video or data
file **stays in its subdir** unchanged. The listing (`contents: posts`) picks up both layouts.
State per post which rule applied, in the table.

Front matter is preserved verbatim on a move. If `posts/_metadata.yml` gains an `author:`, remove
`author:` from posts whose value is identical, and leave a differing one in place.

## Sample posts

The `quarto create project blog` scaffold ships two posts. Detect them by any of: folder names
`posts/welcome/` + `posts/post-with-code/`; titles `Welcome To My Blog` / `Post With Code`;
authors `Tristan O'Malley` / `Harlow Malloc`. Always list them and ask (step 1, second ✋):

- **Delete them** — remove the two folders (including `thumbnail.jpg` / `image.jpg`).
- **Relocate** — apply the subdir → flat rule; both have images, so both stay in their folders.
- **Replace with one hello post** — delete them, write `assets/hello.qmd` filled from the brief.

A post with a stock title but edited body is not a sample post; treat it as the user's.

## `about.qmd`

Stock template: `template: jolla`, links to bare `https://twitter.com` / `https://bsky.app/` /
`https://linkedin.com` / `https://github.com`, body `About this blog`. Per step 1: **keep** →
rewrite with the user's bio (ask for two or three sentences) and only the links they gave, keep
`image: profile.jpg` when the file exists; **drop** → delete the stock file, remove it from the
navbar; a customised `about.qmd` is never deleted, only unlinked.

## Everything else

- `pages/.gitkeep` is created if `pages/` is absent; an existing `pages/` is left alone.
- `styles.css` is kept and wired (`css: styles.css`) but not edited; `site.scss` owns styling.
- `.gitignore`: append `/.quarto/`, `/_site/`, `**/*.quarto_ipynb` if absent. `_freeze/` is **not**
  ignored: the publish workflow relies on committed freeze output.
- `README.md` never renders under `render: ["**/*.qmd"]`; mention it once in the report.
