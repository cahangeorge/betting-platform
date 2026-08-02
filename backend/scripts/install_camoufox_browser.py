"""Install the pinned Camoufox browser after verifying its release digest."""

from __future__ import annotations

from hashlib import sha256
from hmac import compare_digest
from typing import BinaryIO

CAMOUFOX_REPOSITORY = "Official"
CAMOUFOX_VERSION = "152.0.4"
CAMOUFOX_BUILD = "beta.28"
CAMOUFOX_SHA256 = "924f3109ccd6d47cd6a0384d67a345fadf975d48b6319f8dbbd5954c588982bd"
CAMOUFOX_URL = (
    "https://github.com/daijro/camoufox/releases/download/v152.0.4-beta.28/camoufox-152.0.4-beta.28-lin.x86_64.zip"
)


def file_sha256(file: BinaryIO) -> str:
    """Return a stream digest without changing its final read position."""
    file.seek(0)
    digest = sha256()
    while chunk := file.read(1024 * 1024):
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()


def install() -> None:
    """Install and activate the exact browser asset accepted for production."""
    from camoufox.multiversion import get_active_path
    from camoufox.pkgman import AvailableVersion, CamoufoxFetcher, RepoConfig, Version

    repo_config = RepoConfig.find_by_name(CAMOUFOX_REPOSITORY)
    if repo_config is None:
        raise RuntimeError(f"Camoufox repository is unavailable: {CAMOUFOX_REPOSITORY}")

    selected_version = AvailableVersion(
        version=Version(version=CAMOUFOX_VERSION, build=CAMOUFOX_BUILD),
        url=CAMOUFOX_URL,
        is_prerelease=False,
        sha256=CAMOUFOX_SHA256,
    )

    class VerifiedCamoufoxFetcher(CamoufoxFetcher):
        @staticmethod
        def download_file(file: BinaryIO, url: str) -> BinaryIO:
            downloaded = CamoufoxFetcher.download_file(file, url)
            actual_digest = file_sha256(downloaded)
            if not compare_digest(actual_digest, CAMOUFOX_SHA256):
                raise RuntimeError(
                    f"Camoufox browser digest mismatch: expected {CAMOUFOX_SHA256}, received {actual_digest}"
                )
            return downloaded

    fetcher = VerifiedCamoufoxFetcher(
        repo_config=repo_config,
        selected_version=selected_version,
    )
    fetcher.install()
    active_path = get_active_path()
    if active_path is None or not (active_path / "camoufox-bin").is_file():
        raise RuntimeError("Pinned Camoufox browser was not activated")
    print(f"Installed verified Camoufox browser at {active_path}")


if __name__ == "__main__":
    install()
