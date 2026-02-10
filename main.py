from pathlib import Path
import subprocess
import platform
import re
import shutil
import gzip

project_name = "repo_test"
repo_name = project_name
repo_url = "http://127.0.0.1"
repo_dir = repo_name
#echo "Setting up DEB repo"
# os_release = Path("/etc/os-release").read_text()
# match = re.search(r'^VERSION_CODENAME=(.+)$', os_release, re.MULTILINE)
# if match:
#     codename = match.group(1)
#     print(codename)

codename = platform.freedesktop_os_release()['VERSION_CODENAME']

# arch_map = {
#     'x86_64': 'amd64',
#     'aarch64': 'arm64',
#     'armv7l': 'armhf',
#     'i686': 'i386',
# }
# arch = arch_map.get(platform.machine(), platform.machine())
## or just
arch=subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()

component="stable"
suite=codename
deb_dir=f"{repo_dir}/dists/{suite}/{component}/binary-{arch}"
pool_dir=f"{repo_dir}/pool/{component}"

def create_dirs(paths: list):
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)
create_dirs([deb_dir, pool_dir])

# def copy_pkgs()
package="rippled_3.1.0-1_amd64.deb"
# Copy with pathlib
shutil.copy2(Path(package), Path(f"{pool_dir}/{package}"))

result = subprocess.run(
    [
        'dpkg-scanpackages',
        '--multiversion',
        "pool",
        ],
    cwd=repo_dir,
    capture_output=True,
    text=True
)
pkgs_path = Path(f"{repo_dir}/dists/{suite}/{component}/binary-{arch}")
pkgs = pkgs_path /  "Packages"
# Path(pkgs_path).mkdir(parents=True, exist_ok=True)
pkgs.write_text(result.stdout)

with open(pkgs_path / 'Packages', 'rb') as f_in:
    with gzip.open(pkgs_path / 'Packages.gz', 'wb', compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

apt_ftparchive_prefix = "APT::FTPArchive::Release"
apt_ftparchive_field = {
    "Origin": project_name,
    "Label": project_name,
    "Suite": suite,
    "Codename": codename,
    "Architectures": arch,
    "Components": component,
    "Description": "A test repo!"
}
release = Path(f"{repo_dir}/dists/{suite}/Release")
inrelease = Path(f"{repo_dir}/dists/{suite}/InRelease")
apt_ftparchive_bin = "apt-ftparchive"
args = []
with release.open("w") as r:
    for k, v in apt_ftparchive_field.items():
        args.extend(["-o", f"{apt_ftparchive_prefix}::{k}={v}"])

apt_ftparchive_cmd = [apt_ftparchive_bin, *args, "release", f"{repo_dir}/dists/{codename}"] # > $REPO_DIR/dists/jammy/Release"
result = subprocess.run(
    apt_ftparchive_cmd,
    capture_output = True,
    text = True
)

release.write_text(result.stdout)

gpg_cmd=["gpg", "--clearsign", "-o", inrelease, release]
try:
    result = subprocess.run(
        gpg_cmd,
        check = True,
        capture_output = True,
        text = True
    )
    if Path(inrelease).stat().st_size == 0:
        # print(f"result: {result}")
        # print(f"STDOUT: {result.stdout}")
        # print(f"STDERR: {result.stderr}")
        raise ValueError(f"{inrelease} is empty!")
except subprocess.CalledProcessError as e:
    print(f"Command failed with code {e.returncode}")
    print(f"Error: {e.stderr}")
except Exception as e:
    print(f"ERROR! {e}")
    print(f"{inrelease} file not written!")

if trusted := False:
    keypath = "[trusted=yes]"
else:
    keypath = f"[signed-by=/etc/apt/keyrings/{repo_name}.gpg]"

sources = Path(f"/etc/apt/sources.list.d/{repo_name}.list")
repo_source = f"deb {keypath} {repo_url}/{repo_name}/ {suite} {component}\n"

sources.write_text(repo_source, encoding="utf-8")

# APT::FTPArchive::Release::Origin "Repo Test";
# APT::FTPArchive::Release::Label "Repo Test";
# APT::FTPArchive::Release::Suite $DISTRO_CODENAME;
# APT::FTPArchive::Release::Codename $DISTRO_CODENAME;
# APT::FTPArchive::Release::Architectures $archs;
# APT::FTPArchive::Release::Components $COMPONENT;
# APT::FTPArchive::Release::Description "Repo Test (${DISTRO_CODENAME})";
