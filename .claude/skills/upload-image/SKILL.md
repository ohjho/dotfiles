---
name: upload-image
description: >-
  Upload a local image file to imgbb and get back a public, shareable image
  URL. Use this whenever the user wants to upload/host an image, get a public
  or shareable link/URL for a local image (PNG, JPG, etc.), share an annotated
  or processed image, post a screenshot, or when a downstream step needs an
  image as a URL instead of a local file path. Triggers on phrases like "upload
  this image", "get me a URL for this picture", "host this screenshot", "post
  this image", or "turn this local image into a link".
---

# Upload Image → Public URL

Upload a local image to [imgbb](https://imgbb.com) and return its public URL.

## Command

Run this from the repository root:

```bash
uv run --env-file .env \
  https://ohjho.github.io/dotfiles/scripts/upload_imgbb.py "<image_path>"
```

Replace `<image_path>` with the path to the image to upload, e.g.
`"to_post/diagram.png"`. `uv run` fetches the script and its dependencies on the
fly — nothing needs to be installed first.

By convention, post-ready images live in `to_post/`, but the command accepts an
image path anywhere in the repo.

## How to use it

1. Confirm the image file exists at the path you were given. If the path is
   unclear or the file is missing, ask which image to upload rather than
   guessing.
2. Run the command above with that path.
3. On success the script prints **one line to stdout: the direct image URL**
   (plain text, starting with `https://`). Capture that line — it is the result.
4. Report the URL back to the user. If the skill is a step in a larger pipeline
   (e.g. an annotated image that a later step needs as a URL), pass the captured
   URL forward rather than the local path.

## Requirements

- A `.env` file in the repo root containing the imgbb API key:
  ```
  IMGBB_API_KEY=your_key_here
  ```
  The `--env-file .env` flag loads it. If the file is missing or the key is
  unset, the script fails with an auth error — surface that plainly and tell the
  user to add `IMGBB_API_KEY` to `.env` rather than retrying.
- `uv` must be available on the PATH.

## Useful flags

Append these before the image path if needed:

- `--json` / `-j` — print the full imgbb API response as JSON instead of just
  the URL. Use when you need the delete URL, thumbnail, or dimensions.
- `--expiration <seconds>` — auto-delete the image after N seconds (60–15552000).
  Use for temporary uploads the user doesn't want kept.
- `--name <filename>` — the filename stored on imgbb (defaults to the image's
  stem).

## Notes

- The script uploads to a third-party host (imgbb); the image becomes publicly
  accessible via the returned URL. Don't upload sensitive images without the
  user's intent being clear.
- Return the URL as-is. Never fabricate or reconstruct a URL — if the upload
  didn't print one, report the failure instead.
