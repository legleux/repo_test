## Is it a repo?
curl -fsI https://legleux.github.io/repo_test/

curl -fsI https://legleux.github.io/repo_test/dists/jammy


## Signing a deb repo

```bash
gpg --default-key F906AEBB47EC2BF44B83950E128658A9711B4929 \
    --clearsign \
    -o dists/jammy/InRelease \
    dists/jammy/Release
```

## Requirements

### deb
from dpkg-dev dpkg-scanpackages
from apt-utils apt-ftparchive
apt install -y dpkg-dev apt-utils
apt install -y --no-install-recommends gpg dpkg-dev apt-utils

apt install -y dpkg-dev apt-utils

### rpm

#### Installing the key

```bash
curl -fsSL https://legleux.github.io/repo_test/repo.gpg \
  | gpg --dearmor \
  | sudo tee /usr/share/keyrings/repo-test.gpg > /dev/null

    Reference it in the repo entry:

deb [arch=amd64 signed-by=/usr/share/keyrings/repo-test.gpg] \
    https://legleux.github.io/repo_test jammy main
```


### TODO

- [ ] Generate `Packages` per $COMPONENT (if serving multiple, i.e. clio,xrpld,iris from same repo)
```bash
for comp in "${COMPONENTS[@]}"; do
  for arch in amd64 arm64; do
    DEB_DIR="dists/$SUITE/$comp/binary-$arch"
    mkdir -p "$DEB_DIR"
    dpkg-scanpackages --multiversion pool /dev/null > "$DEB_DIR/Packages"
    gzip -9c "$DEB_DIR/Packages" > "$DEB_DIR/Packages.gz"
  done
done
```
- [ ]


###
