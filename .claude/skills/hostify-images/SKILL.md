---
name: hostify-images
description: >-
  Convert a markdown/Quarto document's local inline images into hosted public
  imgbb URLs: uploads each unique image once, replaces every local path with a
  reference-style tag (![caption][im-name]), and appends the
  [im-name]: https://... definitions at the bottom of the doc. Use this
  whenever a .md/.qmd doc references images on the local disk and the user
  wants them shareable/publishable — phrases like "convert the local images to
  image urls", "replace the local image paths with hosted links", "make this
  post's images public", "the images in this qmd point to my Downloads
  folder", "prepare this post's images for publishing", or when a rendered
  page shows broken images because paths are absolute local paths. For hosting
  a single standalone image (no document to rewrite), use the upload-image
  skill instead.
---

# Hostify Images → Reference-Style Hosted URLs

Turn a `.md`/`.qmd` doc's local inline images into imgbb-hosted URLs, so the
document renders for anyone, anywhere. The whole workflow is one script.

## Command

Run **from the repository root** (the uploader reads `IMGBB_API_KEY` from `./.env`):

```bash
python3 .claude/skills/hostify-images/scripts/hostify_images.py <doc.qmd|doc.md>
```

The script:

1. Finds inline images `![caption](path)` pointing at **local** files
   (`http(s)://` and `data:` targets are left untouched; relative paths resolve
   against the doc's directory).
2. Uploads each **unique** file once via the same imgbb uploader the
   `upload-image` skill uses. Every success is cached immediately in a TSV map
   file (`<doc>.imgbb_map.tsv` by default), so duplicate references, reruns, and
   resumes after a failure never upload the same image twice.
3. Rewrites each inline reference to `![caption][im-<label>]` (labels are
   kebab-cased from the filename; duplicates share one label) and appends the
   `[im-<label>]: https://...` definition block at the end of the doc.
4. Prints a summary line — relay it to the user, along with any `WARNING:`
   lines about missing files (those references are left untouched).

Rerunning on a converted doc is a no-op, so it is safe to run again after
adding new images to the doc.

## Useful flags

- `--dry-run` — list what would be uploaded without changing anything. Prefer
  this first when it isn't already clear the user wants these specific images
  made public: uploads land on a third-party host and become publicly
  accessible, so the user should know what's about to leave their machine.
- `--expiration <seconds>` — auto-delete the uploads after N seconds
  (60–15552000). Use for tests or temporary shares; **omit it for real posts**,
  whose published links must keep working.
- `--map-file <path>` — override the cache location (e.g. to share one cache
  across several docs referencing the same images).
- `--label-prefix` — default `im-`.

## Requirements

Same as the `upload-image` skill: `IMGBB_API_KEY` in the repo-root `.env`, and
`uv` on the PATH. If the key is missing the upload fails with an auth error —
surface it and tell the user to add `IMGBB_API_KEY` to `.env` rather than
retrying.

## Failure behavior

If any upload fails, the script aborts without touching the document — partial
conversions would leave a mix of working and broken references. URLs already
obtained are kept in the map file, so simply rerunning resumes where it left
off. Never hand-edit a URL into the doc that the uploader didn't print.
