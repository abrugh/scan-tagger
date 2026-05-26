import logging
import signal
import sys

from .config import Config
from .tagger import Tagger
from .watcher import start_watching


def main():
    config = Config.load()

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("scan-tagger")

    logger.info("scan-tagger starting up")
    logger.info("Watch path: %s", config.watch_path)
    logger.info("Azure deployment: %s", config.azure_openai_deployment)

    tagger = Tagger(config)
    observer = start_watching(config, tagger)

    def shutdown(signum, frame):
        logger.info("Shutting down...")
        observer.stop()
        observer.join()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
