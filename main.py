import gzip
import logging
import platform
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def detect_codename() -> str:
    return platform.freedesktop_os_release()["VERSION_CODENAME"]


def detect_arch() -> str:
    return subprocess.check_output(
        ["dpkg", "--print-architecture"], text=True
    ).strip()


def rebuild_repo(
    repo_dir: str | Path,
    deb_source_dir: str | Path,
    *,
    project_name: str = "repo_test",
    codename: str | None = None,
    arch: str | None = None,
    component: str = "stable",
    repo_url: str = "http://127.0.0.1",
    sign: bool = True,
    write_sources: bool = False,
    external_entries: list[str] | None = None,
) -> None:
    repo_dir = Path(repo_dir)
    deb_source_dir = Path(deb_source_dir)
    codename = codename or detect_codename()
    arch = arch or detect_arch()
    suite = codename

    deb_dir = repo_dir / "dists" / suite / component / f"binary-{arch}"
    pool_dir = repo_dir / "pool" / component

    deb_dir.mkdir(parents=True, exist_ok=True)
    pool_dir.mkdir(parents=True, exist_ok=True)

    # Copy all .deb files from source dir into pool
    debs = list(deb_source_dir.glob("*.deb"))
    if not debs:
        log.warning("No .deb files found in %s", deb_source_dir)
    for deb in debs:
        log.info("Copying %s -> %s", deb.name, pool_dir)
        shutil.copy2(deb, pool_dir / deb.name)

    # Generate Packages index
    result = subprocess.run(
        ["dpkg-scanpackages", "--multiversion", "pool"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    pkgs = deb_dir / "Packages"
    pkgs.write_text(result.stdout)

    # Append external package entries (URL-backed packages)
    if external_entries:
        with pkgs.open("a") as f:
            for entry in external_entries:
                f.write(entry if entry.endswith("\n\n") else entry.rstrip("\n") + "\n\n")

    with pkgs.open("rb") as f_in:
        with gzip.open(deb_dir / "Packages.gz", "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

    log.info("Packages index written to %s", deb_dir)

    # Generate Release file
    apt_ftparchive_fields = {
        "Origin": project_name,
        "Label": project_name,
        "Suite": suite,
        "Codename": codename,
        "Architectures": arch,
        "Components": component,
        "Description": f"{project_name} ({codename})",
    }
    prefix = "APT::FTPArchive::Release"
    args = []
    for k, v in apt_ftparchive_fields.items():
        args.extend(["-o", f"{prefix}::{k}={v}"])

    release_path = repo_dir / "dists" / suite / "Release"
    inrelease_path = repo_dir / "dists" / suite / "InRelease"

    result = subprocess.run(
        ["apt-ftparchive", *args, "release", str(repo_dir / "dists" / codename)],
        capture_output=True,
        text=True,
    )
    release_path.write_text(result.stdout)
    log.info("Release written to %s", release_path)

    # GPG sign
    if sign:
        inrelease_path.unlink(missing_ok=True)
        try:
            subprocess.run(
                ["gpg", "--clearsign", "-o", str(inrelease_path), str(release_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            if inrelease_path.stat().st_size == 0:
                raise ValueError(f"{inrelease_path} is empty!")
            log.info("InRelease signed at %s", inrelease_path)
        except subprocess.CalledProcessError as e:
            log.error("GPG signing failed (code %d): %s", e.returncode, e.stderr)
        except Exception as e:
            log.error("Signing error: %s", e)
    else:
        log.info("Skipping GPG signing (sign=False)")

    # Write APT sources list entry
    if write_sources:
        repo_name = project_name
        keypath = f"[signed-by=/etc/apt/keyrings/{repo_name}.gpg]"
        sources = Path(f"/etc/apt/sources.list.d/{repo_name}.list")
        repo_source = f"deb {keypath} {repo_url}/{repo_name}/ {suite} {component}\n"
        sources.write_text(repo_source, encoding="utf-8")
        log.info("APT source written to %s", sources)

    log.info("Repository rebuild complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rebuild_repo(
        repo_dir="repo_test",
        deb_source_dir=Path.cwd(),
        sign=True,
        write_sources=True,
    )
