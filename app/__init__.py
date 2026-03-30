import logging
from pathlib import Path

from flask import Flask

from .config import Config
from .models import db
from .routes import main_bp
from .services.watcher import FileWatcherService

watcher_service = FileWatcherService()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    configure_logging(app)
    ensure_storage_dirs(app)

    db.init_app(app)

    with app.app_context():
        db.create_all()

    app.register_blueprint(main_bp)

    if app.config["WATCHER_ENABLED"]:
        watcher_service.start(app)
        app.logger.info("Folder watcher enabled for %s", app.config["WATCH_FOLDER"])
    else:
        app.logger.info("Folder watcher disabled by configuration")

    return app


def configure_logging(app: Flask) -> None:
    level_name = app.config.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app.logger.setLevel(level)


def ensure_storage_dirs(app: Flask) -> None:
    folder_keys = [
        "WATCH_FOLDER",
        "PROCESSING_FOLDER",
        "REVIEWED_FOLDER",
        "ERROR_FOLDER",
    ]
    for key in folder_keys:
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)
