import logging
import signal
import sys

from .config import Config
from .notifier import DailySummaryThread, Notifier
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

    notifier = Notifier(config)
    tagger = Tagger(config)
    observer = start_watching(config, tagger, notifier)

    # Daily summary thread
    summary_thread = DailySummaryThread(notifier, config.daily_summary_hour)
    summary_thread.start()

    if config.notify_on_startup:
        notifier.notify_startup()

    channels = []
    if config.discord_webhook_url:
        channels.append("Discord")
    if config.signal_recipient:
        channels.append("Signal")
    logger.info("Notifications: %s", ", ".join(channels) if channels else "disabled")

    def shutdown(signum, frame):
        logger.info("Shutting down...")
        summary_thread.stop()
        observer.stop()
        observer.join()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        observer.join()
    except KeyboardInterrupt:
        summary_thread.stop()
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
