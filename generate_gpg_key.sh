#!/usr/bin/env bash
set -euo pipefail

# Unattended GPG key generation (GnuPG 2.1+)
#
# Produces:
#   - a new keypair in your default GNUPGHOME (or custom, if set)
#   - optional: exports ascii-armored public + secret keys to files
#
# Usage examples:
#   ./gen_gpg_key_unattended.sh
#   NAME_REAL="Michael Legleux" NAME_EMAIL="legleux@gmail.com" PASSPHRASE="..." ./gen_gpg_key_unattended.sh
#   GNUPGHOME=/tmp/gnupg-test ./gen_gpg_key_unattended.sh
#
# Notes:
# - If PASSPHRASE is empty, the key will be unprotected (not recommended).
# - For CI, prefer setting GNUPGHOME to an isolated directory.

# ---- config (override via env) ----
NAME_REAL="${NAME_REAL:-testy}"
NAME_EMAIL="${NAME_EMAIL:-test@example.invalid}"
NAME_COMMENT="${NAME_COMMENT:-unattended}"
KEY_TYPE="${KEY_TYPE:-ed25519}"        # ed25519 or rsa
KEY_LENGTH="${KEY_LENGTH:-4096}"       # only used for rsa
EXPIRE="${EXPIRE:-5y}"                 # 0 for no expiration, accepts d and m
PASSPHRASE="${PASSPHRASE:-}"           # should probably be set
EXPORT_DIR="${EXPORT_DIR:-gpg_keys}"           # export keys

EXPIRED="${EXPIRED:-false}"

# -----------------------------------
# set -x
check_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    # return 1
    }
}

check_cmd gpg
if [[ $- != *i* ]] && [[ ! -t 0 ]]; then
  echo "We're not interactive?"
  # Probably not human running so let's just install
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y --quiet gpg
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq gpg
  fi
else
  echo "Probably interactive"
fi
# We need to make gpg non-interactive
# export GPG_TTY="${GPG_TTY:-$(tty 2>/dev/null || true)}"


generate_key() {
  # set -x
  if [[ -n "${GNUPGHOME:-}" ]]; then
    mkdir -p "$GNUPGHOME"
    chmod 700 "$GNUPGHOME"
  fi
  gpg_args=(--batch --yes --pinentry-mode loopback)

  tmpfile="$(mktemp)"
  cleanup() { rm -f "$tmpfile"; }
  trap cleanup EXIT

  if $EXPIRED; then
    e=$(date -u -d "yesterday + 2 minutes" +"%Y%m%dT%H%M%S")
    gpg_args+=(--faked-system-time "$e")
    EXPIRE=1d
  fi

  # Create a batch file to run gpg keygen
  if [[ "$KEY_TYPE" == "rsa" ]]; then
    cat >"$tmpfile" <<EOF
%echo Generating an unattended RSA key
Key-Type: RSA
Key-Length: ${KEY_LENGTH}
Subkey-Type: RSA
Subkey-Length: ${KEY_LENGTH}
Name-Real: ${NAME_REAL}
Name-Comment: ${NAME_COMMENT}
Name-Email: ${NAME_EMAIL}
Expire-Date: ${EXPIRE}
%no-protection
%commit
%echo done
EOF
  else
    cat >"$tmpfile" <<EOF
%echo Generating an unattended Ed25519 key
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: cert,sign
Subkey-Type: eddsa
Subkey-Curve: ed25519
Subkey-Usage: sign
Name-Real: ${NAME_REAL}
Name-Comment: ${NAME_COMMENT}
Name-Email: ${NAME_EMAIL}
Expire-Date: ${EXPIRE}
%no-protection
%commit
%echo done
EOF
  fi


  if [[ -n "$PASSPHRASE" ]]; then
    # Remove %no-protection
    sed -i '/^%no-protection$/d' "$tmpfile"
    gpg_args+=(--passphrase "$PASSPHRASE")
  else
    echo "!!! PASSPHRASE is empty !!! generating an unprotected secret key." >&2
  fi

  gpg "${gpg_args[@]}" --generate-key "$tmpfile"

  # Show our work in the form of the key's fingerprint
  fpr="$(
    gpg --batch --with-colons --list-secret-keys "${NAME_EMAIL}" \
      | awk -F: '$1=="fpr"{print $10; exit}'
  )"

  if [[ -z "$fpr" ]]; then
    echo "Error: could not find generated key fingerprint." >&2
    exit 1
  fi

  echo "Generated key fingerprint: $fpr"

  if [[ -n "$EXPORT_DIR" ]]; then
    mkdir -p "$EXPORT_DIR"
    chmod 700 "$EXPORT_DIR"

    gpg --batch --yes --armor --export "$fpr" > "$EXPORT_DIR/public.asc"

    if [[ -n "$PASSPHRASE" ]]; then
      gpg --batch --yes --pinentry-mode loopback --passphrase "$PASSPHRASE" \
        --armor --export-secret-keys "$fpr" > "$EXPORT_DIR/secret.asc"
    else
      gpg --batch --yes --armor --export-secret-keys "$fpr" > "$EXPORT_DIR/secret.asc"
    fi

    chmod 600 "$EXPORT_DIR/secret.asc"
    echo "Exported:"
    echo "  $EXPORT_DIR/public.asc"
    echo "  $EXPORT_DIR/secret.asc"
  fi
}

generate_key
