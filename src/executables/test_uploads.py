import json
import os
import random
import tempfile

import dotenv

from firebase.user import FirebaseUser
from util import log, short_url


def main() -> None:
    dotenv.load_dotenv()

    user = os.environ["SENDER_EMAIL_ADDRESS"]

    firebase_credentials_file = os.environ["FIREBASE_CREDENTIALS_FILE"]
    firebase_storage_path = os.environ["FIREBASE_STORAGE_PATH"]

    firebase_user = FirebaseUser(firebase_credentials_file, firebase_storage_path, verbose=True)

    json_path = tempfile.mktemp(suffix=".json")
    csv_path = tempfile.mktemp(suffix=".csv")

    with open(json_path, "w", encoding="utf-8") as outfile:
        json.dump({"test": "test"}, outfile)

    with open(csv_path, "w", encoding="utf-8") as outfile:
        outfile.write("test,test,test\n")

    for attachment in [json_path, csv_path]:
        url = firebase_user.upload_file_and_get_url(
            user, attachment, random.randint(1, 100), verbose=True
        )
        log.print_ok(f"Download url:\n\n{url}\n\n")
        extension = os.path.splitext(attachment)[1]
        string_url = f"{extension.upper()}: {short_url.shorten_url(url)}"
        log.print_bright(string_url)


if __name__ == "__main__":
    main()
