"""Manage external package entries backed by external_packages.json.

Supports two modes for adding packages:
1. With a metadata URL (e.g. Artifactory storage API): fetches size/checksums
   from the API, then Range-requests ~64KB of the .deb to extract control fields.
2. Without metadata: full download to extract control + compute hashes.
"""

import gzip
import hashlib
import io
import json
import lzma
import logging
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen, urlretrieve

log = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "external_packages.json"

# How many bytes to Range-request for extracting control fields.
_RANGE_BYTES = 65536


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_packages() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    return json.loads(STORE_PATH.read_text())


def save_packages(packages: list[dict]) -> None:
    STORE_PATH.write_text(json.dumps(packages, indent=2) + "\n")


# ---------------------------------------------------------------------------
# ar / control extraction (no full download needed)
# ---------------------------------------------------------------------------

def _extract_control_from_deb_bytes(data: bytes) -> str:
    """Parse the ar archive header of a .deb and extract the control file."""
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("Not a valid .deb (ar archive)")

    pos = 8  # skip ar magic
    while pos + 60 <= len(data):
        name = data[pos : pos + 16].decode("ascii").strip().rstrip("/")
        size = int(data[pos + 48 : pos + 58].decode("ascii").strip())
        fmag = data[pos + 58 : pos + 60]
        if fmag != b"`\n":
            raise ValueError(f"Bad ar member header at offset {pos}")

        data_start = pos + 60
        data_end = data_start + size

        if name.startswith("control.tar"):
            if data_end > len(data):
                raise ValueError(
                    "Range download too small to contain full control archive "
                    f"(need {data_end} bytes, got {len(data)})"
                )

            member_data = data[data_start:data_end]

            # Decompress
            if name.endswith(".gz"):
                member_data = gzip.decompress(member_data)
            elif name.endswith(".xz"):
                member_data = lzma.decompress(member_data)
            elif name.endswith(".zst"):
                import zstandard  # optional dep
                member_data = zstandard.ZstdDecompressor().decompress(member_data)

            with tarfile.open(fileobj=io.BytesIO(member_data)) as tf:
                for ti in tf:
                    if ti.name in ("./control", "control"):
                        f = tf.extractfile(ti)
                        if f is None:
                            raise ValueError("control is not a regular file")
                        return f.read().decode("utf-8")
            raise ValueError("control file not found inside control.tar")

        # Advance to next member (ar pads to even boundary)
        pos = data_end + (data_end % 2)

    raise ValueError("control.tar not found in .deb")


# ---------------------------------------------------------------------------
# Metadata fetching
# ---------------------------------------------------------------------------

def _fetch_metadata(metadata_url: str) -> dict:
    """Fetch size + checksums from an Artifactory-style storage API."""
    req = Request(metadata_url)
    with urlopen(req) as resp:  # noqa: S310
        info = json.loads(resp.read())

    checksums = info["checksums"]
    return {
        "size": int(info["size"]),
        "md5": checksums["md5"],
        "sha1": checksums["sha1"],
        "sha256": checksums["sha256"],
        "download_url": info["downloadUri"],
    }


def _fetch_control_via_range(download_url: str) -> str:
    """Range-request the first chunk of a .deb and extract control fields."""
    req = Request(download_url)
    req.add_header("Range", f"bytes=0-{_RANGE_BYTES - 1}")
    with urlopen(req) as resp:  # noqa: S310
        data = resp.read(_RANGE_BYTES)
    return _extract_control_from_deb_bytes(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_package_url(
    url: str,
    component: str = "stable",
    *,
    metadata_url: str | None = None,
) -> dict:
    """Add an external package entry.

    *url* is used as the download/redirect target for APT clients.

    If *metadata_url* is given (e.g. Artifactory storage API), size and
    checksums are fetched from there and only ~64 KB of the .deb is
    downloaded to extract Debian control fields.

    Without *metadata_url*, the full .deb is downloaded to compute hashes.
    """
    if metadata_url:
        return _add_from_metadata(url, component, metadata_url)
    return _add_from_full_download(url, component)


def _add_from_metadata(url: str, component: str, metadata_url: str) -> dict:
    log.info("Fetching metadata from %s", metadata_url)
    meta = _fetch_metadata(metadata_url)

    download_url = meta["download_url"] or url
    log.info("Range-requesting control fields from %s", download_url)
    control = _fetch_control_via_range(download_url)

    basename = download_url.rsplit("/", 1)[-1].split("?")[0]
    filename = f"pool/{component}/{basename}"

    entry_text = _build_entry(control, filename, meta["size"], meta["md5"], meta["sha1"], meta["sha256"])
    # The redirect should point to the actual download URL
    entry = {"url": download_url, "filename": filename, "entry": entry_text}
    _upsert(entry)
    return entry


def _add_from_full_download(url: str, component: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".deb") as tmp:
        log.info("Downloading %s", url)
        urlretrieve(url, tmp.name)  # noqa: S310

        result = subprocess.run(
            ["dpkg-deb", "--field", tmp.name],
            capture_output=True,
            text=True,
            check=True,
        )
        control = result.stdout
        data = Path(tmp.name).read_bytes()

    size = len(data)
    md5 = hashlib.md5(data).hexdigest()
    sha1 = hashlib.sha1(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()

    basename = url.rsplit("/", 1)[-1].split("?")[0]
    filename = f"pool/{component}/{basename}"

    entry_text = _build_entry(control, filename, size, md5, sha1, sha256)
    entry = {"url": url, "filename": filename, "entry": entry_text}
    _upsert(entry)
    return entry


def _build_entry(control: str, filename: str, size: int, md5: str, sha1: str, sha256: str) -> str:
    lines = control.rstrip("\n").split("\n")
    lines.append(f"Filename: {filename}")
    lines.append(f"Size: {size}")
    lines.append(f"MD5sum: {md5}")
    lines.append(f"SHA1: {sha1}")
    lines.append(f"SHA256: {sha256}")
    return "\n".join(lines) + "\n"


def _upsert(entry: dict) -> None:
    packages = load_packages()
    packages = [p for p in packages if p["filename"] != entry["filename"]]
    packages.append(entry)
    save_packages(packages)
    log.info("Added external package: %s -> %s", entry["filename"], entry["url"])


def get_redirect_map() -> dict[str, str]:
    """Return {"/pool/component/foo.deb": "https://..."} for all entries."""
    return {f"/{e['filename']}": e["url"] for e in load_packages()}


def remove_package(filename: str) -> bool:
    """Remove entry by filename (e.g. 'pool/stable/foo.deb'). Returns True if found."""
    packages = load_packages()
    filtered = [p for p in packages if p["filename"] != filename]
    if len(filtered) == len(packages):
        return False
    save_packages(filtered)
    return True
