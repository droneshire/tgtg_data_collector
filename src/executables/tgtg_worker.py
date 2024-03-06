import argparse
import json
import os
from datetime import datetime

import dotenv

from backend import TgtgCollectorBackend
from constants import PROJECT_NAME
from firebase.storage import FirebaseStorage
from firebase.user import FirebaseUser
from parse_args import parse_args
from search_context.google_places import GooglePlacesAPI
from search_context.us_census import USCensusAPI
from too_good_to_go.manager import TgtgManager
from util import email, file_util, log, wait


def get_firebase_host_url(firebase_credentials_file: str) -> str:
    with open(firebase_credentials_file, encoding="utf-8") as infile:
        data = json.load(infile)
        project_name = data["project_id"]
        url = f"https://{project_name}.web.app/"
    return url


def run_loop(args: argparse.Namespace, bot_pidfile: str) -> None:
    file_util.make_sure_path_exists(args.tgtg_data_dir)

    sender_email = email.Email(
        {
            "address": os.environ["SENDER_EMAIL_ADDRESS"],
            "password": os.environ["SENDER_EMAIL_PASSWORD"],
            "quiet": args.dry_run,
        }
    )

    chrome_paths = {
        "browser": os.environ.get("CHROME_PATH_BROWSER", ""),
        "driver": os.environ.get("CHROME_PATH_DRIVER", ""),
    }

    tgtg_manager = TgtgManager(
        os.environ["TGTG_DEFAULT_API_EMAIL"],
        os.environ["TGTG_DEFAULT_API_CREDENTIALS_FILE"],
        chrome_paths=chrome_paths,
        allow_create=True,
        use_proxies=args.use_proxies,
    )
    firebase_credentials_file = os.environ["FIREBASE_CREDENTIALS_FILE"]
    firebase_storage_path = os.environ["FIREBASE_STORAGE_PATH"]
    firebase_cloud_storage = FirebaseStorage(firebase_credentials_file, firebase_storage_path)
    firebase_user = FirebaseUser(firebase_credentials_file, verbose=args.verbose)
    census_api = USCensusAPI(os.environ["CENSUS_API_KEY"])
    google_places_api = GooglePlacesAPI(os.environ["GOOGLE_MAPS_PLACES_API_KEY"])

    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = log.get_logging_dir(PROJECT_NAME)
    search_results_dir = os.path.join(log_dir, "search_context_results")
    file_util.make_sure_path_exists(search_results_dir)
    default_results_csv = os.path.join(search_results_dir, f"search_{date_str}.csv")

    backend = TgtgCollectorBackend(
        sender_email,
        tgtg_manager=tgtg_manager,
        firebase_user=firebase_user,
        firebase_cloud_storage=firebase_cloud_storage,
        census_api=census_api,
        google_places_api=google_places_api,
        tgtg_data_dir=args.tgtg_data_dir,
        mode=args.mode,
        results_csv=default_results_csv,
        run_in_thread=args.run_in_thread,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    url = get_firebase_host_url(firebase_credentials_file)
    log.print_bright(f"Web server can be found at: {url}")

    backend.init()

    # run through first iteration, then create the pidfile
    backend.run()

    with open(bot_pidfile, "w", encoding="utf-8") as outfile:
        outfile.write(str(os.getpid()))

    while True:
        backend.run()
        wait.wait(args.time_between_loop)


def main() -> None:
    dotenv.load_dotenv(".env")
    args = parse_args()

    log.setup_log(args.log_level, args.log_dir, PROJECT_NAME)
    log.print_ok_blue("Starting TGTG data collection client...")

    bot_pidfile = os.environ.get("BOT_PIDFILE", "tgtg_worker.pid")

    try:
        run_loop(args, bot_pidfile)
    except KeyboardInterrupt:
        os.remove(bot_pidfile)


if __name__ == "__main__":
    main()
