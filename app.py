import logging
import subprocess
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config
import package_store
from gpg_utils import get_signing_key_info, import_gpg_key
from main import rebuild_repo
from watcher import start_watcher, stop_watcher

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_rebuild_lock = threading.Lock()

ALLOWED_KEY_EXTENSIONS = {".asc", ".gpg", ".key", ".pgp"}

# Redirect map: {"/pool/stable/foo.deb": "https://..."}
# Updated in-place when external packages change.
redirect_map: dict[str, str] = {}


def _load_redirect_map() -> None:
    redirect_map.clear()
    redirect_map.update(package_store.get_redirect_map())


def do_rebuild() -> str:
    """Run rebuild_repo in a thread-safe way. Returns 'ok' or 'skipped'."""
    if not _rebuild_lock.acquire(blocking=False):
        log.info("Rebuild already in progress, skipping")
        return "skipped"
    try:
        log.info("Starting repository rebuild")
        ext_entries = [p["entry"] for p in package_store.load_packages()]
        rebuild_repo(
            repo_dir=config.REPO_DIR,
            deb_source_dir=config.WATCH_DIR,
            project_name=config.PROJECT_NAME,
            codename=config.CODENAME,
            arch=config.ARCH,
            component=config.COMPONENT,
            repo_url=config.REPO_URL,
            sign=config.SIGN,
            external_entries=ext_entries or None,
        )
        return "ok"
    except Exception:
        log.exception("Rebuild failed")
        return "error"
    finally:
        _rebuild_lock.release()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config.WATCH_DIR.mkdir(parents=True, exist_ok=True)
    _load_redirect_map()
    observer = start_watcher(config.WATCH_DIR, do_rebuild)
    yield
    stop_watcher(observer)


class RepoServer:
    """Serve repo files with Range-header stripping and redirect support.

    APT sends ``Range: bytes=0-`` and Starlette replies with a
    Content-Range header that APT's HTTP transport rejects, so we strip it.

    For external packages, APT requests pool/component/foo.deb and we
    return a 302 redirect to the real external URL.
    """

    def __init__(self, static_app: ASGIApp, redirects: dict[str, str]) -> None:
        self.static_app = static_app
        self.redirects = redirects

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"range"]
            path = scope["path"]
            if path in self.redirects:
                response = RedirectResponse(self.redirects[path], status_code=302)
                await response(scope, receive, send)
                return
        await self.static_app(scope, receive, send)


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Serve the repo directory so APT can fetch Packages/Release/InRelease/pool
config.REPO_DIR.mkdir(parents=True, exist_ok=True)
repo_files = StaticFiles(directory=config.REPO_DIR)
app.mount(
    f"/{config.PROJECT_NAME}",
    RepoServer(repo_files, redirect_map),
    name="repo",
)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    watch = config.WATCH_DIR
    packages = []
    if watch.is_dir():
        for p in sorted(watch.glob("*.deb")):
            packages.append({"name": p.name, "size": _human_size(p.stat().st_size)})

    external_packages = package_store.load_packages()

    gpg_key = get_signing_key_info()
    sign_enabled = config.SIGN

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "packages": packages,
            "external_packages": external_packages,
            "gpg_key": gpg_key,
            "sign_enabled": sign_enabled,
        },
    )


@app.post("/api/rebuild")
async def api_rebuild():
    status = do_rebuild()
    return {"status": status}


@app.post("/api/upload-deb")
async def api_upload_deb(file: UploadFile):
    if not file.filename or not file.filename.endswith(".deb"):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "File must have .deb extension"},
        )

    safe_name = Path(file.filename).name
    dest = config.WATCH_DIR / safe_name
    config.WATCH_DIR.mkdir(parents=True, exist_ok=True)

    data = await file.read()
    dest.write_bytes(data)
    log.info("Uploaded .deb: %s (%d bytes)", safe_name, len(data))

    return {"status": "ok", "filename": safe_name}


class AddPackageUrlRequest(BaseModel):
    url: str
    metadata_url: str | None = None


@app.post("/api/add-package-url")
async def api_add_package_url(body: AddPackageUrlRequest):
    url = body.url.strip()
    if not url:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "URL is required"},
        )

    metadata_url = body.metadata_url.strip() if body.metadata_url else None
    try:
        entry = package_store.add_package_url(
            url, component=config.COMPONENT, metadata_url=metadata_url,
        )
    except Exception as e:
        log.exception("Failed to add package URL: %s", url)
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": str(e)},
        )

    _load_redirect_map()
    status = do_rebuild()
    return {"status": status, "filename": entry["filename"]}


@app.post("/api/remove-package-url")
async def api_remove_package_url(body: AddPackageUrlRequest):
    """Remove an external package by its URL."""
    packages = package_store.load_packages()
    match = next((p for p in packages if p["url"] == body.url), None)
    if not match:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "detail": "Package URL not found"},
        )

    package_store.remove_package(match["filename"])
    _load_redirect_map()
    status = do_rebuild()
    return {"status": status}


@app.post("/api/upload-gpg-key")
async def api_upload_gpg_key(file: UploadFile):
    if not file.filename:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "No filename provided"},
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_KEY_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "detail": f"Allowed extensions: {', '.join(sorted(ALLOWED_KEY_EXTENSIONS))}",
            },
        )

    key_data = await file.read()
    try:
        import_info = import_gpg_key(key_data)
    except RuntimeError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": str(e)},
        )

    log.info("Imported GPG key: %s", import_info.get("key_id"))
    return {"status": "ok", "import_info": import_info}


@app.get("/api/gpg-key")
async def api_gpg_key():
    result = subprocess.run(
        ["gpg", "--batch", "--export", "--armor"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "detail": "No GPG public key available"},
        )

    name = config.PROJECT_NAME
    return Response(
        content=result.stdout,
        media_type="application/pgp-keys",
        headers={"Content-Disposition": f'attachment; filename="{name}.gpg.asc"'},
    )


@app.get("/api/sources.list")
async def api_sources_list():
    from main import detect_arch, detect_codename

    codename = config.CODENAME or detect_codename()
    arch = config.ARCH or detect_arch()
    name = config.PROJECT_NAME
    component = config.COMPONENT
    url = config.REPO_URL

    signed_by = f"[arch={arch} signed-by=/etc/apt/keyrings/{name}.gpg] " if config.SIGN else ""
    content = f"deb {signed_by}{url.rstrip('/')}/{name}/ {codename} {component}\n"

    return PlainTextResponse(
        content,
        headers={
            "Content-Disposition": f'attachment; filename="{name}.list"',
        },
    )


def main():
    uvicorn.run(app, host="0.0.0.0", port=80)


if __name__ == "__main__":
    main()
