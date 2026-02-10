#!/bin/bash

set -euo pipefail

pkgs+=(dpkg-dev)
pkgs+=(apt-utils)

apt-get update
apt-get install -y --no-install-recommends "${pkgs[@]}"
