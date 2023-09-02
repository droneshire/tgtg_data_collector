import argparse
import os
import sys

import dotenv

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dotenv.load_dotenv(".env")

    log.print_ok_blue(f"Creating TGTG API account for {args.email}...")

    manager = TgtgManager(args.email, args.credentials_file, allow_create=True)
    credentials = manager.create_account()

    if not credentials:
        sys.exit(1)


if __name__ == "__main__":
    main()
