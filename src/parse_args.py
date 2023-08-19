import argparse

from constants import PROJECT_NAME
from util import log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Property Guru Bot")

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
    parser.add_argument(
        "--lattitude",
        type=float,
        help="Lattitude of the location to search for",
    )
    parser.add_argument(
        "--longitude",
        type=float,
        help="Longitude of the location to search for",
    )
    parser.add_argument(
        "--radius",
        type=int,
        help="Radius of the location to search for",
    )
    return parser.parse_args()
