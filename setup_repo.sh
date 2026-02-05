#!/usr/bin/env bash

# This script sets up a GitHub Pages-based RPM or DEB repository.
# Usage: ./setup_repo.sh <deb|rpm> <package-file> [<distro-codename>]

set -euo pipefail
REPO_TYPE="$1"
PACKAGE_FILE="$2"
# DISTRO_CODENAME="${3:-stable}" #"component" ?
DISTRO_CODENAME="${3}"

if [ -z $DISTRO_CODENAME ]; then
  . /etc/os-release
  DISTRO_CODENAME=$VERSION_CODENAME
fi

SUITE=$DISTRO_CODENAME
COMPONENT="main"

USER="legleux"
REPO="repo_test"

REPO_DIR="repo"
mkdir -p "$REPO_DIR"
touch "$REPO_DIR/.nojekyll"

case "$REPO_TYPE" in
  rpm)
    echo "Setting up RPM repo"
    cp "$PACKAGE_FILE" "$REPO_DIR/"
    createrepo_c "$REPO_DIR"
    ;;
  deb)
    echo "Setting up DEB repo"
    ARCH=$(dpkg --print-architecture)
    DEB_DIR="$REPO_DIR/dists/$DISTRO_CODENAME/main/binary-$ARCH"
    POOL_DIR="$REPO_DIR/pool/main"

    DEB822=true

    mkdir -p "$DEB_DIR" "$POOL_DIR"

    cp -f "$PACKAGE_FILE" "$POOL_DIR/"

    echo "Generating Packages and Packages.gz"
    (
      cd "$REPO_DIR" || exit 1
      dpkg-scanpackages --multiversion pool /dev/null > "dists/$DISTRO_CODENAME/main/binary-$ARCH/Packages"
    )
    gzip -9c "$DEB_DIR/Packages" > "$DEB_DIR/Packages.gz"

    # Test created
    test -f $REPO_DIR/pool/main/${PACKAGE_FILE} && echo OK || echo MISSING
    # Check which arch's we have available
    archs=$(
      find "dists/$SUITE/${COMPONENT}" -maxdepth 1 -type d -name 'binary-*' -printf '%f\n' \
      | sed 's/^binary-//' \
      | sort -u \
      | tr '\n' ' '
    )

    ## Create Release file
    cat >"apt-ftparchive.conf" <<EOF
APT::FTPArchive::Release::Origin "Repo Test";
APT::FTPArchive::Release::Label "Repo Test";
APT::FTPArchive::Release::Suite $DISTRO_CODENAME;
APT::FTPArchive::Release::Codename $DISTRO_CODENAME;
APT::FTPArchive::Release::Architectures $archs;
APT::FTPArchive::Release::Component $COMPONENT;
APT::FTPArchive::Release::Description "Repo Test (${DISTRO_CODENAME})";
EOF
    apt-ftparchive release $REPO_DIR/dists/jammy > $REPO_DIR/dists/jammy/Release

    # Generate the `InRelease` file
    gpg --clearsign -o "$REPO_DIR/dists/$SUITE/InRelease" "$REPO_DIR/dists/$SUITE/Release"
    ;;
  *)
    echo "Unknown repo type: $REPO_TYPE"
    exit 1
    ;;
esac

echo "Repository setup complete in ./$REPO_DIR"
echo "Now commit and push this directory to GitHub Pages."
echo
sudo="sudo"
if $(id -u); then
  sudo=""
fi
cat <<EOF
To publish to GitHub Pages:

  git init
  git checkout -b gh-pages
  cp -r $REPO_DIR/* .
  git add .
  git commit -m "Publish $REPO_TYPE repo"
  git remote add origin <your-repo-url>
  git push -f origin gh-pages

Then add to your package manager:

For RPM (YUM/DNF):

  [myrepo]
  name=My GitHub RPM Repo
  baseurl=https://<user>.github.io/<repo>/
  enabled=1
  gpgcheck=0

For DEB (APT):

  echo "deb [trusted=yes] https://$USER.github.io/$REPO/ $SUITE ${COMPONENT}" | ${sudo} tee /etc/apt/sources.list.d/${REPO}.list"
EOF

OUTPUT_SRC_DIR=$PWD # typically /etc/apt/sources.list.d
if $DEB822;then
  cat >"$OUTPUT_SRC_DIR/${REPO}.sources" <<EOF
Types: deb
URIs: https://$USER.github.io/$REPO/
Suites: $SUITE
Components: $COMPONENT
Trusted: yes
EOF
else
  cat >"$OUTPUT_SRC_DIR/${REPO}.list" <<EOF
echo "deb [trusted=yes] https://$USER.github.io/$REPO/ $SUITE ${COMPONENT}" | "${sudo}" tee "/etc/apt/sources.list.d/${REPO}.list"
EOF

fi
