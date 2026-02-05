#!/usr/bin/env bash

# This script sets up a GitHub Pages-based RPM or DEB repository.
# Usage: ./setup_repo.sh <deb|rpm> <package-file> [<distro-codename>]

set -euo pipefail

REPO_TYPE="$1"
PACKAGE_FILE="$2"
DISTRO_CODENAME="${3:-stable}"

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
    mkdir -p "$DEB_DIR"
    cp "$PACKAGE_FILE" "$DEB_DIR/"
    echo "Generating Packages.gz"
    dpkg-scanpackages --multiversion "$DEB_DIR" /dev/null | gzip -9c > "$DEB_DIR/Packages.gz"
    ;;
  *)
    echo "Unknown repo type: $REPO_TYPE"
    exit 1
    ;;
esac

echo "Repository setup complete in ./$REPO_DIR"
echo "Now commit and push this directory to GitHub Pages."
echo
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

  echo "deb [trusted=yes] https://<user>.github.io/<repo>/ $DISTRO_CODENAME main" | sudo tee /etc/apt/sources.list.d/myrepo.list
EOF
