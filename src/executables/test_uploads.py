import argparse
import json
import os
import random
import tempfile

import dotenv

from firebase.storage import FirebaseStorage
from util import log, short_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TGTG Worker")
    parser.add_argument(
        "--file-path",
        type=str,
        help="Path to file to upload",
    )
    parser.add_argument(
        "--user",
        type=str,
        help="User to upload file for",
    )
    parser.add_argument(
        "--num-items",
        type=int,
        help="Number of items to upload",
    )
    return parser.parse_args()


def main() -> None:
    dotenv.load_dotenv()
    args = parse_args()

    user = args.user

    firebase_credentials_file = os.environ["FIREBASE_CREDENTIALS_FILE"]
    firebase_storage_path = os.environ["FIREBASE_STORAGE_PATH"]

    firebase_storage = FirebaseStorage(
        firebase_credentials_file, firebase_storage_path, verbose=True
    )

    if args.file_path:
        attachments = [args.file_path]
    else:
        json_path = tempfile.mktemp(suffix=".json")
        csv_path = tempfile.mktemp(suffix=".csv")

        with open(json_path, "w", encoding="utf-8") as outfile:
            json.dump({"test": "test"}, outfile)

        with open(csv_path, "w", encoding="utf-8") as outfile:
            outfile.write("test,test,test\n")

        attachments = [json_path, csv_path]

    for attachment in attachments:
        url = firebase_storage.upload_file_and_get_url(
            user,
            attachment,
            args.num_items if args.num_items else random.randint(1, 100),
            verbose=True,
        )
        log.print_ok(f"Download url:\n\n{url}\n\n")
        extension = os.path.splitext(attachment)[1]
        string_url = f"{extension.upper()}: {short_url.shorten_url(url)}"
        log.print_bright(string_url)


if __name__ == "__main__":
    main()
