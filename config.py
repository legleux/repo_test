import os
from pathlib import Path

WATCH_DIR = Path(os.environ.get("WATCH_DIR", "./packages"))
REPO_DIR = Path(os.environ.get("REPO_DIR", "./repo_test"))
PROJECT_NAME = os.environ.get("PROJECT_NAME", "repo_test")
COMPONENT = os.environ.get("COMPONENT", "stable")
REPO_URL = os.environ.get("REPO_URL", "http://127.0.0.1")
SIGN = os.environ.get("SIGN", "true").lower() in ("true", "1", "yes")
CODENAME = os.environ.get("CODENAME", "") or None
ARCH = os.environ.get("ARCH", "") or None
