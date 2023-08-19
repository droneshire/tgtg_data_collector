import argparse
import json
import os
import sys

from tgtg import TgtgClient

from util import file_util, log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Property Guru Bot")

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    parser.add_argument("--email", type=str, help="Email address", required=True)
    parser.add_argument(
        "--credentials-file",
        type=str,
        help="Credentials file store",
        default=os.path.join(root_dir, "tgtg_credentials.json"),
    )
    return parser.parse_args()


def create_account(email: str, credentials_file: str) -> None:
    client = TgtgClient(email)
    credentials = client.get_credentials()

    if credentials:
        log.print_ok(f"Account Credentials for {email}:")
        log.print_bright(f"{json.dumps(credentials, indent=4)}")
    else:
        log.print_fail(f"Failed to create account for {email}!")
        sys.exit(1)

    file_util.make_sure_path_exists(os.path.dirname(credentials_file))

    with open(credentials_file, "w", encoding="utf-8") as outfile:
        json.dump(credentials, outfile)


def main() -> None:
    args = parse_args()

    log.print_ok_blue("Creating TGTG API account...")

    create_account(args.email, args.credentials_file)


if __name__ == "__main__":
    main()
