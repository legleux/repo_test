import logging
import subprocess
from datetime import UTC, datetime

log = logging.getLogger(__name__)


def import_gpg_key(key_data: bytes) -> dict:
    """Import a GPG key from raw bytes. Returns dict with key_id and output."""
    result = subprocess.run(
        ["gpg", "--batch", "--import"],
        input=key_data,
        capture_output=True,
        text=False,
    )
    stderr = result.stderr.decode(errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"GPG import failed: {stderr}")

    # Parse key ID from stderr (e.g. "gpg: key ABCD1234: ...")
    key_id = None
    for line in stderr.splitlines():
        if "key " in line and ":" in line:
            part = line.split("key ")[1].split(":")[0].strip()
            if part:
                key_id = part
                break

    return {"key_id": key_id, "output": stderr.strip()}


def get_signing_key_info() -> dict | None:
    """Return info about the first available GPG secret key, or None."""
    result = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--list-secret-keys"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None

    info: dict = {}
    for line in result.stdout.splitlines():
        fields = line.split(":")
        record_type = fields[0]
        if record_type == "sec":
            created_ts = fields[5]
            expires_ts = fields[6]
            if created_ts:
                info["created"] = datetime.fromtimestamp(
                    int(created_ts), tz=UTC
                ).strftime("%Y-%m-%d")
            if expires_ts:
                info["expires"] = datetime.fromtimestamp(
                    int(expires_ts), tz=UTC
                ).strftime("%Y-%m-%d")
            else:
                info["expires"] = "never"
        elif record_type == "fpr" and "fingerprint" not in info:
            info["fingerprint"] = fields[9]
        elif record_type == "uid" and "uid" not in info:
            info["uid"] = fields[9]

    return info if info else None
