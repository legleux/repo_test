# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project creates and manages signed Debian (DEB) and RPM package repositories, intended for hosting on GitHub Pages. It serves `rippled` (XRP Ledger) binaries as APT/YUM repositories.

## Key Commands

**Run the Python repo builder:**
```bash
python main.py
```

**Docker (builds repo and serves via HTTP):**
```bash
docker build -t repo_test . && docker run -p 8000:8000 repo_test
```

**Install system dependencies (Debian/Ubuntu):**
```bash
./install_dependencies.sh   # installs dpkg-dev, apt-utils
```

**Generate GPG keys (unattended):**
```bash
./generate_gpg_key.sh
# Configure via env vars: NAME_REAL, NAME_EMAIL, KEY_TYPE (ed25519|rsa), EXPIRE, PASSPHRASE, EXPORT_DIR
```

**Shell-based repo setup (alternative to main.py):**
```bash
./setup_repo.sh <deb|rpm> <package-file> [<distro-codename>]
```

## Architecture

There are two parallel implementations for building DEB repositories:

- **`main.py`** — Python implementation (newer). Uses `pathlib`, `subprocess`, and `platform` to detect OS codename/arch, run `dpkg-scanpackages`, generate Release files via `apt-ftparchive`, and GPG-sign them into `InRelease`. Writes APT sources to `/etc/apt/sources.list.d/`. Requires Python 3.14+.

- **`setup_repo.sh`** — Bash implementation (original). Supports both DEB and RPM (`createrepo_c`) repository creation. Outputs DEB822-format `.sources` files.

Both follow the same pipeline: copy `.deb` to `pool/` → `dpkg-scanpackages` → gzip Packages → `apt-ftparchive release` → `gpg --clearsign` for InRelease.

**Repository layout produced:**
```
repo_test/
├── dists/<suite>/<component>/binary-<arch>/  # Packages, Packages.gz
├── dists/<suite>/Release, InRelease          # signed metadata
└── pool/<component>/                         # .deb files
```

**GPG key management:** `generate_gpg_key.sh` generates Ed25519 or RSA keys in batch mode. `expired.sh` generates expired keys for testing. Keys are exported to `gpg_keys/` (gitignored).

## System Requirements

- Python 3.14+ (specified in `.python-version`)
- `dpkg-dev` (for `dpkg-scanpackages`)
- `apt-utils` (for `apt-ftparchive`)
- `gpg` (for signing)
- `createrepo_c` (RPM repos only, used by `setup_repo.sh`)

## Branches

- **`main`** — source code
- **`gh-pages`** — published repository served via GitHub Pages
