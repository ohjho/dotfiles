# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31", "typer>=0.12", "loguru>=0.7"]
# ///
"""Upload a local image to imgbb (https://api.imgbb.com) and print its URL.

Replaces the manual ``curl`` dance (read the file, base64-encode it, ``POST`` it
with your API key) with a single self-contained command. The image is base64
encoded and sent via ``POST`` to imgbb's upload endpoint; on success the direct
image URL (``data.url``) is printed to stdout.

The API key is optional on the CLI and defaults to the ``IMGBB_API_KEY``
environment variable. Get a key at https://api.imgbb.com.

Run it self-contained with ``uv``::

    IMGBB_API_KEY=... uv run scripts/upload_imgbb.py path/to/pic.png
    uv run scripts/upload_imgbb.py pic.png -k YOUR_KEY
    uv run scripts/upload_imgbb.py pic.png --expiration 600 --json
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests
import typer
from loguru import logger

UPLOAD_URL = "https://api.imgbb.com/1/upload"
API_KEY_ENV = "IMGBB_API_KEY"

app = typer.Typer(
    add_completion=False,
    help="Upload a local image to imgbb and print its URL.",
)


def to_base64(data: bytes) -> str:
    """Base64-encode raw bytes into an ASCII string.

    Args:
        data: The raw bytes to encode (e.g. an image file's contents).

    Returns:
        The standard base64 representation as an ASCII ``str``.

    Examples:
        >>> to_base64(b"hi")
        'aGk='
        >>> to_base64(b"")
        ''
    """
    return base64.b64encode(data).decode("ascii")


def build_payload(
    image_b64: str,
    name: Optional[str] = None,
    expiration: Optional[int] = None,
) -> dict:
    """Assemble the form-data dict for the imgbb upload ``POST``.

    Optional fields are omitted entirely when ``None`` so imgbb falls back to
    its defaults (no expiration, server-assigned name).

    Args:
        image_b64: The base64-encoded image string (see :func:`to_base64`).
        name: Optional filename to store the image under.
        expiration: Optional auto-delete window in seconds (60-15552000).

    Returns:
        A dict suitable for ``requests.post(..., data=...)``.

    Examples:
        >>> build_payload("aGk=")
        {'image': 'aGk='}
        >>> build_payload("aGk=", name="pic", expiration=600)
        {'image': 'aGk=', 'name': 'pic', 'expiration': 600}
        >>> build_payload("aGk=", name="pic")
        {'image': 'aGk=', 'name': 'pic'}
    """
    payload: dict = {"image": image_b64}
    if name is not None:
        payload["name"] = name
    if expiration is not None:
        payload["expiration"] = expiration
    return payload


def extract_url(response_json: dict) -> str:
    """Pull the direct image URL (``data.url``) out of an imgbb response.

    Args:
        response_json: The parsed JSON payload returned by the upload endpoint.

    Returns:
        The direct image URL.

    Raises:
        ValueError: If the payload has no ``data.url`` field.

    Examples:
        >>> extract_url({"data": {"url": "https://i.ibb.co/x/pic.png"}})
        'https://i.ibb.co/x/pic.png'
        >>> extract_url({"success": False})
        Traceback (most recent call last):
        ...
        ValueError: imgbb response did not contain data.url
    """
    url = response_json.get("data", {}).get("url")
    if not url:
        raise ValueError("imgbb response did not contain data.url")
    return url


def read_image(path: Path) -> bytes:
    """Read an image file's raw bytes (isolated side effect).

    Args:
        path: Path to the local image file.

    Returns:
        The file's contents as bytes.
    """
    return path.read_bytes()


def upload_image(
    api_key: str,
    image_b64: str,
    *,
    name: Optional[str] = None,
    expiration: Optional[int] = None,
    timeout: int = 60,
) -> dict:
    """Upload a base64 image to imgbb and return the full parsed response.

    The single place ``requests.post`` is touched, so the encoding/formatting
    helpers stay pure and testable. The key is sent as a query-string param and
    the image (plus optional fields) as form data.

    Args:
        api_key: The imgbb API key.
        image_b64: The base64-encoded image string.
        name: Optional filename to store the image under.
        expiration: Optional auto-delete window in seconds.
        timeout: Per-request timeout in seconds.

    Returns:
        The parsed JSON payload from imgbb.

    Raises:
        requests.RequestException: On network errors or a non-2xx status.
        ValueError: If imgbb reports failure in the response body.
    """
    resp = requests.post(
        UPLOAD_URL,
        params={"key": api_key},
        data=build_payload(image_b64, name=name, expiration=expiration),
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success", False):
        message = payload.get("error", {}).get("message", "unknown error")
        raise ValueError(f"imgbb upload failed: {message}")
    return payload


@app.command()
def main(
    image: Path = typer.Argument(
        ...,
        metavar="IMAGE",
        help="Path to the local image file to upload.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        "-k",
        help=f"imgbb API key; defaults to the {API_KEY_ENV} env var.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="Filename to store on imgbb; defaults to the image's stem.",
    ),
    expiration: Optional[int] = typer.Option(
        None,
        "--expiration",
        min=60,
        max=15552000,
        help="Auto-delete the image after N seconds (60-15552000).",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print imgbb's full raw response JSON instead of just the URL.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show debug-level logging."
    ),
) -> None:
    """Upload a local image to imgbb and print its URL."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{message}")

    key = api_key or os.environ.get(API_KEY_ENV)
    if not key:
        logger.error(
            "No API key: pass --api-key/-k or set the {} env var.", API_KEY_ENV
        )
        raise typer.Exit(code=2)

    if not image.is_file():
        logger.error("Image not found: {}", image)
        raise typer.Exit(code=2)

    eff_name = name if name is not None else image.stem
    logger.debug(
        "uploading {} as name={!r} expiration={}", image, eff_name, expiration
    )

    try:
        image_b64 = to_base64(read_image(image))
        payload = upload_image(
            key, image_b64, name=eff_name, expiration=expiration
        )
    except requests.RequestException as exc:
        logger.error("Upload request failed: {}", exc)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(extract_url(payload))

    logger.info("Uploaded {}", image.name)


if __name__ == "__main__":
    app()
