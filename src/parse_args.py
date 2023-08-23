import argparse

from constants import PROJECT_NAME
from util import log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TGTG Client")

    log_dir = log.get_logging_dir(PROJECT_NAME)

    parser.add_argument("--log-dir", default=log_dir)
    parser.add_argument(
        "--log-level",
        type=str,
        help="Logging level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the script without actually sending SMS",
    )

    return parser.parse_args()
