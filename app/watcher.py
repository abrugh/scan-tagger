import logging
import threading
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class ScanHandler(FileSystemEventHandler):
    def __init__(self, config, tagger, notifier):
        self.config = config
        self.tagger = tagger
        self.notifier = notifier
        self._processing: set[str] = set()
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix.lower() not in self.config.supported_extensions:
            return

        with self._lock:
            key = str(file_path)
            if key in self._processing:
                return
            self._processing.add(key)

        thread = threading.Thread(
            target=self._process_file, args=(file_path,), daemon=True
        )
        thread.start()

    def _wait_for_stable(self, file_path: Path) -> bool:
        """Poll until file size stops changing (SMB write completion)."""
        prev_size = -1
        stable_count = 0

        for _ in range(60):
            try:
                current_size = file_path.stat().st_size
            except FileNotFoundError:
                logger.warning("File disappeared before processing: %s", file_path.name)
                return False

            if current_size == prev_size and current_size > 0:
                stable_count += 1
                if stable_count >= self.config.stabilization_checks:
                    return True
            else:
                stable_count = 0

            prev_size = current_size
            time.sleep(self.config.stabilization_delay)

        logger.warning("File never stabilized: %s", file_path.name)
        return False

    def _process_file(self, file_path: Path):
        try:
            logger.info("New file detected: %s", file_path.name)

            if not self._wait_for_stable(file_path):
                return

            summary = self.tagger.generate_name(file_path)
            if not summary:
                logger.warning("Empty summary for %s — skipping", file_path.name)
                return

            today = date.today().isoformat()
            suffix = file_path.suffix.lower()
            new_name = f"{today}_{summary}{suffix}"
            new_path = file_path.parent / new_name

            counter = 2
            while new_path.exists():
                new_name = f"{today}_{summary}_{counter}{suffix}"
                new_path = file_path.parent / new_name
                counter += 1

            old_name = file_path.name
            file_path.rename(new_path)
            logger.info("Renamed: %s → %s", old_name, new_path.name)
            self.notifier.notify_success(old_name, new_path.name)

        except Exception as exc:
            logger.exception("Error processing %s", file_path.name)
            self.notifier.notify_failure(file_path.name, exc)
        finally:
            with self._lock:
                self._processing.discard(str(file_path))


def start_watching(config, tagger, notifier):
    """Start the filesystem watcher and return the Observer."""
    watch_path = Path(config.watch_path)
    watch_path.mkdir(parents=True, exist_ok=True)

    handler = ScanHandler(config, tagger, notifier)
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=False)
    observer.start()

    logger.info("Watching %s for new scans...", watch_path)

    if config.process_existing:
        logger.info("Processing existing files...")
        for f in sorted(watch_path.iterdir()):
            if f.is_file() and f.suffix.lower() in config.supported_extensions:
                handler.on_created(
                    SimpleNamespace(is_directory=False, src_path=str(f))
                )

    return observer
