import argparse
import os

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
        "--mode",
        type=str,
        help="Mode to run in",
        default="prod",
        choices=["prod", "dev"],
    )
    parser.add_argument(
        "--tgtg-data-dir",
        type=str,
        help="Directory to store TGTG data",
        default=os.path.join(log_dir, "tgtg_data"),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the script without actually sending SMS",
    )
    parser.add_argument(
        "--time-between-loop",
        type=int,
        help="Time between each loop in seconds",
        default=60,
    )
    parser.add_argument(
        "--use-proxies",
        action="store_true",
        help="Use proxies for requests",
    )
    return parser.parse_args()
