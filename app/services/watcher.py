import threading
import time
from pathlib import Path

from flask import Flask
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .document_processor import DocumentProcessor


class IncomingPdfHandler(FileSystemEventHandler):
    def __init__(self, app: Flask):
        self.app = app

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

        worker = threading.Thread(target=self._process, args=(source_path,), daemon=True)
        worker.start()

    def _process(self, source_path: str):
        time.sleep(1)
        with self.app.app_context():
            processor = DocumentProcessor()
            processor.process_pdf(source_path)


class FileWatcherService:
    def __init__(self):
        self._observer: Observer | None = None
        self._lock = threading.Lock()

    def start(self, app: Flask) -> None:
        with self._lock:
            if self._observer and self._observer.is_alive():
                return

            watch_dir = Path(app.config["WATCH_FOLDER"])
            watch_dir.mkdir(parents=True, exist_ok=True)

            event_handler = IncomingPdfHandler(app)
            observer = Observer()
            observer.schedule(event_handler, str(watch_dir), recursive=False)
            observer.daemon = True
            observer.start()
            self._observer = observer

    def stop(self) -> None:
        with self._lock:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
