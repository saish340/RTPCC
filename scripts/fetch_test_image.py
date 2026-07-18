"""Download one freely reusable crowd image for the CSRNet sanity check."""

from __future__ import annotations

from pathlib import Path

import requests


# Wikimedia Commons CC0 image. Special:FilePath is a stable direct-download
# endpoint and redirects to the current media file location.
SOURCES = (
    "https://commons.wikimedia.org/wiki/Special:FilePath/Street_Crowd.jpg?width=1024",
    # Fallback: another freely reusable Commons crowd photograph.
    "https://commons.wikimedia.org/wiki/Special:FilePath/Crowd_of_people.jpg?width=960",
)
DESTINATION = Path("data/test_images/test.jpg")
TIMEOUT_SECONDS = 30
HEADERS = {"User-Agent": "RTPCC-CSRNet-Test-Image/0.1 (local development)"}


def download_image(destination: Path = DESTINATION) -> Path:
    """Download the first available sample image and return its local path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(destination.suffix + ".part")
    failures: list[str] = []

    for url in SOURCES:
        try:
            with requests.get(url, stream=True, timeout=TIMEOUT_SECONDS, headers=HEADERS) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if not content_type.startswith("image/"):
                    raise ValueError(f"expected an image response, received {content_type or 'unknown content type'}")
                with temporary_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            output.write(chunk)
            if temporary_path.stat().st_size == 0:
                raise ValueError("downloaded file was empty")
            temporary_path.replace(destination)
            print(f"Downloaded: {destination.resolve()}")
            print(f"Size: {destination.stat().st_size:,} bytes")
            print(f"Source: {url}")
            return destination
        except (OSError, ValueError, requests.RequestException) as exc:
            temporary_path.unlink(missing_ok=True)
            failures.append(f"{url} ({exc})")

    details = "\n  ".join(failures)
    raise RuntimeError(f"Could not download a test crowd image. Tried:\n  {details}")


if __name__ == "__main__":
    try:
        download_image()
    except RuntimeError as exc:
        raise SystemExit(f"Download failed: {exc}") from exc
