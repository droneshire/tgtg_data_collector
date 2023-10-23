import argparse
import json
import os

import dotenv

from backend import TgtgCollectorBackend
from constants import PROJECT_NAME
from firebase.user import FirebaseUser
from parse_args import parse_args
from too_good_to_go.manager import TgtgManager
from util import email, file_util, log, wait


def get_firebase_host_url(firebase_credentials_file: str) -> str:
    with open(firebase_credentials_file, encoding="utf-8") as infile:
        data = json.load(infile)
        project_name = data["project_id"]
        url = f"https://{project_name}.web.app/"
    return url


def run_loop(args: argparse.Namespace) -> None:
    file_util.make_sure_path_exists(args.tgtg_data_dir)

    sender_email = email.Email(
        {
            "address": os.environ["SENDER_EMAIL_ADDRESS"],
            "password": os.environ["SENDER_EMAIL_PASSWORD"],
            "quiet": args.dry_run,
        }
    )
    tgtg_manager = TgtgManager(
        os.environ["TGTG_DEFAULT_API_EMAIL"],
        os.environ["TGTG_DEFAULT_API_CREDENTIALS_FILE"],
        allow_create=True,
        use_proxies=args.use_proxies,
    )
    firebase_credentials_file = os.environ["FIREBASE_CREDENTIALS_FILE"]
    firebase_storage_path = os.environ["FIREBASE_STORAGE_PATH"]
    firebase_user = FirebaseUser(
        firebase_credentials_file, firebase_storage_path, verbose=args.verbose
    )
    backend = TgtgCollectorBackend(
        sender_email,
        tgtg_manager=tgtg_manager,
        firebase_user=firebase_user,
        tgtg_data_dir=args.tgtg_data_dir,
        mode=args.mode,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    url = get_firebase_host_url(firebase_credentials_file)
    log.print_bright(f"Web server can be found at: {url}")

    backend.init()

    while True:
        backend.run()
        wait.wait(args.time_between_loop)


def main() -> None:
    dotenv.load_dotenv(".env")
    args = parse_args()

    log.setup_log(args.log_level, args.log_dir, PROJECT_NAME)
    log.print_ok_blue("Starting TGTG data collection client...")

    bot_pidfile = os.environ.get("BOT_PIDFILE", "tgtg_worker.pid")

    with open(bot_pidfile, "w", encoding="utf-8") as outfile:
        outfile.write(str(os.getpid()))

    try:
        run_loop(args)
    except KeyboardInterrupt:
        os.remove(bot_pidfile)


if __name__ == "__main__":
    main()
