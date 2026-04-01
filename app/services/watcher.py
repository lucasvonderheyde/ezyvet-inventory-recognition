import threading
import time
from pathlib import Path

from flask import Flask
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .document_processor import DocumentProcessor


class IncomingPdfHandler(FileSystemEventHandler):
    def __init__(self, app: Flask, watcher_service: "FileWatcherService"):
        self.app = app
        self.watcher_service = watcher_service

    def on_created(self, event):
        self._handle_event(event)

    def on_moved(self, event):
        self._handle_event(event)

    def _handle_event(self, event):
        if event.is_directory:
            return

        source_path = getattr(event, "dest_path", None) or event.src_path
        if not source_path.lower().endswith(".pdf"):
            return

        self.watcher_service.schedule_path(source_path)


class FileWatcherService:
    def __init__(self):
        self._observer: Observer | None = None
        self._scan_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active_paths: set[str] = set()
        self._app: Flask | None = None

    def start(self, app: Flask) -> None:
        with self._lock:
            if self._observer and self._observer.is_alive():
                return

            watch_dir = Path(app.config["WATCH_FOLDER"])
            watch_dir.mkdir(parents=True, exist_ok=True)

            self._stop_event.clear()
            self._app = app
            event_handler = IncomingPdfHandler(app, self)
            observer = Observer()
            observer.schedule(event_handler, str(watch_dir), recursive=False)
            observer.daemon = True
            observer.start()
            self._observer = observer

            self._scan_thread = threading.Thread(target=self._scan_loop, args=(app,), daemon=True)
            self._scan_thread.start()
            self.scan_once(app)

    def schedule_path(self, source_path: str) -> None:
        normalized_path = str(Path(source_path).resolve())
        with self._lock:
            if normalized_path in self._active_paths:
                return
            self._active_paths.add(normalized_path)

        worker = threading.Thread(target=self._process, args=(normalized_path,), daemon=True)
        worker.start()

    def scan_once(self, app: Flask) -> None:
        watch_dir = Path(app.config["WATCH_FOLDER"])
        for pdf_path in sorted(watch_dir.glob("*.pdf")):
            self.schedule_path(str(pdf_path))

    def _scan_loop(self, app: Flask) -> None:
        interval = app.config["WATCH_FOLDER_SCAN_INTERVAL"]
        while not self._stop_event.wait(interval):
            self.scan_once(app)

    def _process(self, source_path: str) -> None:
        try:
            time.sleep(1)
            if not self._app:
                return
            with self._app.app_context():
                processor = DocumentProcessor()
                processor.process_pdf(source_path)
        finally:
            with self._lock:
                self._active_paths.discard(source_path)

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
            if self._scan_thread and self._scan_thread.is_alive():
                self._scan_thread.join(timeout=5)
                self._scan_thread = None
            self._active_paths.clear()
            self._app = None
