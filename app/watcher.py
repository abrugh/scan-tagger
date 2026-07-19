import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class ScanHandler(FileSystemEventHandler):
    def __init__(self, config, tagger, notifier, reorienter=None):
        self.config = config
        self.tagger = tagger
        self.notifier = notifier
        self.reorienter = reorienter
        self._processing: set[str] = set()
        # Destinations we produce via our own rename — used to ignore the
        # on_moved echo so we don't re-tag (and re-rename) our own output.
        self._self_renamed: set[str] = set()
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        self._enqueue(Path(event.src_path))

    def on_moved(self, event):
        # Some scanners write to a temp file and rename it into place when done.
        # The finished document arrives as a move, not a create.
        if event.is_directory:
            return
        self._enqueue(Path(event.dest_path))

    def _enqueue(self, file_path: Path):
        if file_path.suffix.lower() not in self.config.supported_extensions:
            return

        with self._lock:
            key = str(file_path)
            if key in self._self_renamed:
                # This is the move event for a file we just renamed ourselves.
                self._self_renamed.discard(key)
                return
            if key in self._processing:
                return
            self._processing.add(key)

        thread = threading.Thread(
            target=self._process_file, args=(file_path,), daemon=True
        )
        thread.start()

    def _is_complete(self, file_path: Path) -> bool:
        """Verify the file is a fully-written, parseable document.

        Size/mtime settling alone is not enough: a scanner that pauses between
        pages of a large multi-page scan leaves a size-stable but truncated
        file. A complete PDF has a valid trailer/EOF, and a complete image can
        be fully decoded — so parseability is the real "done" signal.
        """
        suffix = file_path.suffix.lower()
        try:
            if suffix == ".pdf":
                result = subprocess.run(
                    ["pdfinfo", str(file_path)],
                    capture_output=True,
                    timeout=30,
                )
                return result.returncode == 0

            from PIL import Image

            with Image.open(file_path) as img:
                img.verify()
            return True
        except Exception as exc:
            logger.debug(
                "Completeness check not yet passing for %s: %s", file_path.name, exc
            )
            return False

    def _wait_for_stable(self, file_path: Path) -> bool:
        """Wait until the file is fully written and parseable.

        Requires size AND mtime to hold steady for `stabilization_checks`
        consecutive polls, then confirms the document actually parses before
        handing it off. Gives up after `stabilization_timeout` seconds.
        """
        prev_sig = None
        stable_count = 0
        deadline = time.monotonic() + self.config.stabilization_timeout

        while time.monotonic() < deadline:
            try:
                st = file_path.stat()
            except FileNotFoundError:
                logger.warning("File disappeared before processing: %s", file_path.name)
                return False

            sig = (st.st_size, st.st_mtime)
            if sig == prev_sig and st.st_size > 0:
                stable_count += 1
                if stable_count >= self.config.stabilization_checks:
                    if self._is_complete(file_path):
                        return True
                    # Size settled but the document isn't complete yet — the
                    # scanner is likely paused mid multi-page write. Keep waiting.
                    logger.info(
                        "%s is size-stable but not yet complete — still uploading",
                        file_path.name,
                    )
                    stable_count = 0
            else:
                stable_count = 0

            prev_sig = sig
            time.sleep(self.config.stabilization_delay)

        logger.warning("File never stabilized (timeout): %s", file_path.name)
        return False

    def _process_file(self, file_path: Path):
        try:
            logger.info("New file detected: %s", file_path.name)

            if not self._wait_for_stable(file_path):
                return

            if self.reorienter is not None:
                try:
                    self.reorienter.correct(file_path)
                except Exception:
                    # Orientation is best-effort — never let it block tagging.
                    logger.exception("Reorientation failed for %s", file_path.name)

            summary = self.tagger.generate_name(file_path)
            if not summary:
                logger.warning("Empty summary for %s — skipping", file_path.name)
                return

            file_date = datetime.fromtimestamp(file_path.stat().st_mtime).date().isoformat()
            suffix = file_path.suffix.lower()
            new_name = f"{file_date}_{summary}{suffix}"
            new_path = file_path.parent / new_name

            counter = 2
            while new_path.exists():
                new_name = f"{file_date}_{summary}_{counter}{suffix}"
                new_path = file_path.parent / new_name
                counter += 1

            old_name = file_path.name
            with self._lock:
                self._self_renamed.add(str(new_path))
            file_path.rename(new_path)
            logger.info("Renamed: %s → %s", old_name, new_path.name)
            self.notifier.notify_success(old_name, new_path.name)

        except Exception as exc:
            logger.exception("Error processing %s", file_path.name)
            self.notifier.notify_failure(file_path.name, exc)
        finally:
            with self._lock:
                self._processing.discard(str(file_path))


def start_watching(config, tagger, notifier, reorienter=None):
    """Start the filesystem watcher and return the Observer."""
    watch_path = Path(config.watch_path)
    watch_path.mkdir(parents=True, exist_ok=True)

    handler = ScanHandler(config, tagger, notifier, reorienter)
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
