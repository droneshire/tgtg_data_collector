import argparse
import dotenv
import os
import sys

from random_word import RandomWords

from too_good_to_go.manager import TgtgManager
from util import log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Property Guru Bot")

    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser.add_argument("--email", type=str, help="Email address", required=True)
    parser.add_argument(
        "--credentials-file",
        type=str,
        help="Credentials file store",
        default=os.path.join(
            root_dir, os.environ.get("TGTG_DEFAULT_CREDENTIALS_FILE", "tgtg_credentials.json")
        ),
    )
    parser.add_argument(
        "--number-of-credentials",
        type=int,
        help="Number of credentials to create from this email address (uses aliases)",
        default=1,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dotenv.load_dotenv(".env")

    log.print_ok_blue(f"Creating TGTG API account(s) for {args.email}...")

    emails = [args.email]
    for _ in range(args.number_of_credentials - 1):
        random_prefix = RandomWords().get_random_word()
        email_base = args.email.split("@")[0]
        email_suffix = args.email.split("@")[1]
        new_email = f"{email_base}+{random_prefix}@{email_suffix}"
        emails.append(new_email)

    credentials = []

    chrome_paths = {
        "browser": os.environ.get("CHROME_PATH_BROWSER", ""),
        "driver": os.environ.get("CHROME_PATH_DRIVER", ""),
    }

    for email in emails:
        manager = TgtgManager(
            email, args.credentials_file, chrome_paths=chrome_paths, allow_create=True
        )
        credential = manager.create_account()
        if not credential:
            log.print_warn(f"Failed to create account for {email}")
            continue
        credentials.append(credential)

    if not credentials:
        sys.exit(1)


if __name__ == "__main__":
    main()
