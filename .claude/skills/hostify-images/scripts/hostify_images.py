#!/usr/bin/env python3
"""Convert a markdown/qmd doc's local inline images into hosted imgbb URLs.

Scans the doc for inline markdown images ![caption](/local/path.jpg), uploads
each unique local file to imgbb once (cached in a TSV map file, so reruns and
duplicate references never re-upload), replaces every inline local path with a
reference-style tag ![caption][im-<label>], and appends the
[im-<label>]: https://... definitions at the bottom of the doc.

Remote images (http/https/data:) are left untouched. Running the script again
on a converted doc is a no-op.

Run from the repository root (the uploader needs ./.env with IMGBB_API_KEY):

    python3 .claude/skills/hostify-images/scripts/hostify_images.py <doc.qmd|doc.md> [options]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

UPLOADER_URL = "https://ohjho.github.io/dotfiles/scripts/upload_imgbb.py"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff"}
INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def find_local_images(content: str, doc_dir: Path):
    """Return ({target_str: resolved Path}, [skipped warnings]) for local inline images.

    target_str is the exact string inside the parentheses, so replacement can be
    done with a literal match. Order of first appearance is preserved.
    """
    targets: dict[str, Path] = {}
    warnings: list[str] = []
    for m in INLINE_IMAGE_RE.finditer(content):
        target = m.group(1).strip()
        if target in targets:
            continue
        if re.match(r"^(https?:|data:|ftp:)", target, re.IGNORECASE):
            continue
        # strip an optional markdown title: ](path "title")
        path_part = re.sub(r'\s+"[^"]*"$', "", target)
        path = Path(path_part).expanduser()
        if not path.is_absolute():
            path = (doc_dir / path).resolve()
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        if not path.is_file():
            warnings.append(f"missing file, left untouched: {target}")
            continue
        targets[target] = path
    return targets, warnings


def load_map(map_file: Path) -> dict[str, str]:
    urls: dict[str, str] = {}
    if map_file.is_file():
        for line in map_file.read_text().splitlines():
            if "\t" in line:
                p, url = line.split("\t", 1)
                urls[p] = url
    return urls


def upload(path: Path, expiration: int | None) -> str:
    cmd = ["uv", "run", "--env-file", ".env", UPLOADER_URL]
    if expiration:
        cmd += ["--expiration", str(expiration)]
    cmd.append(str(path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if result.returncode != 0 or not url.startswith("https://"):
        sys.exit(
            f"ERROR: upload failed for {path}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}\n"
            "Aborting — no URLs are fabricated. Already-uploaded images are cached "
            "in the map file; rerun to resume."
        )
    return url


def make_labels(paths: list[Path], prefix: str) -> dict[Path, str]:
    labels: dict[Path, str] = {}
    used: set[str] = set()
    for path in paths:
        base = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "image"
        label = f"{prefix}{base}"
        n = 2
        while label in used:
            label = f"{prefix}{base}-{n}"
            n += 1
        used.add(label)
        labels[path] = label
    return labels


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("doc", type=Path, help="the .qmd or .md document to convert")
    ap.add_argument("--map-file", type=Path, default=None,
                    help="path→URL TSV cache (default: <doc>.imgbb_map.tsv)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list the unique local images that would be uploaded, then exit")
    ap.add_argument("--expiration", type=int, default=None,
                    help="auto-delete uploads after N seconds (60–15552000); for temp/test runs")
    ap.add_argument("--label-prefix", default="im-", help="reference label prefix (default: im-)")
    args = ap.parse_args()

    if not args.doc.is_file() or args.doc.suffix.lower() not in {".md", ".qmd", ".markdown"}:
        sys.exit(f"ERROR: {args.doc} is not an existing .md/.qmd document")
    if not Path(".env").is_file():
        sys.exit("ERROR: no .env in the current directory — run from the repo root "
                 "(the uploader needs IMGBB_API_KEY from ./.env)")

    content = args.doc.read_text()
    targets, warnings = find_local_images(content, args.doc.parent.resolve())
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    unique_paths = list(dict.fromkeys(targets.values()))
    n_refs = sum(1 for m in INLINE_IMAGE_RE.finditer(content)
                 if m.group(1).strip() in targets)
    if not targets:
        print("No local inline images found — nothing to do.")
        return

    if args.dry_run:
        print(f"Would upload {len(unique_paths)} unique image(s) "
              f"({n_refs} inline reference(s)):")
        for p in unique_paths:
            print(f"  {p}")
        return

    map_file = args.map_file or args.doc.with_suffix(args.doc.suffix + ".imgbb_map.tsv")
    urls = load_map(map_file)
    uploaded = reused = 0
    for path in unique_paths:
        key = str(path)
        if key in urls:
            reused += 1
            continue
        url = upload(path, args.expiration)
        with map_file.open("a") as f:
            f.write(f"{key}\t{url}\n")
        urls[key] = url
        uploaded += 1
        print(f"uploaded: {path.name} -> {url}")

    labels = make_labels(unique_paths, args.label_prefix)

    def replace(m: re.Match) -> str:
        target = m.group(1).strip()
        if target not in targets:
            return m.group(0)
        bang_caption = m.group(0)[: m.group(0).rfind("(")]  # "![caption]"
        return f"{bang_caption}[{labels[targets[target]]}]"

    content = INLINE_IMAGE_RE.sub(replace, content)
    defs = "\n".join(f"[{labels[p]}]: {urls[str(p)]}" for p in unique_paths)
    content = content.rstrip("\n") + "\n\n" + defs + "\n"
    args.doc.write_text(content)

    print(f"\n{args.doc}: replaced {n_refs} inline reference(s) with "
          f"{len(unique_paths)} label(s); {uploaded} uploaded, {reused} reused from "
          f"{map_file}")


if __name__ == "__main__":
    main()
