import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 3


class DebChangeHandler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _schedule_rebuild(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._fire)
            self._timer.start()

    def _fire(self) -> None:
        log.info("Debounce expired, triggering rebuild")
        self._on_change()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and event.src_path.endswith(".deb"):
            log.info("Detected new .deb: %s", event.src_path)
            self._schedule_rebuild()

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and event.src_path.endswith(".deb"):
            log.debug("Detected modified .deb: %s", event.src_path)
            self._schedule_rebuild()

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and event.src_path.endswith(".deb"):
            log.info("Detected deleted .deb: %s", event.src_path)
            self._schedule_rebuild()


def start_watcher(watch_dir: str | Path, on_change: Callable[[], None]) -> Observer:
    watch_dir = Path(watch_dir)
    watch_dir.mkdir(parents=True, exist_ok=True)
    handler = DebChangeHandler(on_change)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()
    log.info("Watching %s for .deb changes", watch_dir)
    return observer


def stop_watcher(observer: Observer) -> None:
    observer.stop()
    observer.join()
    log.info("Watcher stopped")
