#!/bin/bash

set -euo pipefail

pkgs+=(apt-utils)
pkgs+=(dpkg-dev)
pkgs+=(gpg)
pkgs+=(gpg-agent) # no-install-recommends omits

apt-get update
apt-get install -y --no-install-recommends "${pkgs[@]}"
