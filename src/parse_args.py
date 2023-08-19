import argparse
import os
import random
import string

from config import PROJECT_NAME
from util import log


def generate_random_string(length: int) -> str:
    # Define the characters you want to include in the random string
    characters = string.ascii_letters + string.digits

    # Generate the random string
    random_string = "".join(random.choice(characters) for _ in range(length))

    return random_string[0].upper() + random_string + "!"


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
        "--email",
        type=str,
        help="Email address to login with",
        default=os.environ.get("GMAIL_MAIN_EMAIL"),
    )
    parser.add_argument(
        "--backup-email",
        type=str,
        help="Backup email address to register with",
        default=os.environ.get("GMAIL_BACKUP_EMAIL"),
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Password to login all accounts with",
        default=generate_random_string(10),
    )
    parser.add_argument(
        "--manual-input",
        action="store_true",
        help="Manually input codes instead of email parser",
    )
    parser.add_argument(
        "--close-on-exit",
        action="store_true",
        help="Close the browser on exit",
    )
    parser.add_argument(
        "--save-after-read",
        action="store_true",
        help="Save email after reading instead of deleting",
    )
    return parser.parse_args()
