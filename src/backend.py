import json
import os
import random
import time
import typing as T

import pytz

from demographics.google_places import GooglePlacesAPI
from demographics.us_census import USCensusAPI
from firebase.user import FirebaseUser
from too_good_to_go import data_types as too_good_to_go_data_types
from too_good_to_go.manager import TgtgManager
from too_good_to_go.search_interval import is_time_to_search
from util import email, file_util, fmt_util, log, short_url, wait
from util.fmt_util import get_pretty_seconds


class TgtgCollectorBackend:
    TIME_BETWEEN_FIREBASE_QUERIES = {
        "prod": 60 * 60 * 24,
        "dev": 60 * 1,
    }
    FOOD_EMOJIS = ["🍕", "🍔", "🍟", "🍗", "🍖", "🌭", "🍿", "🍛", "🍜", "🍝", "🍤"]
    TIME_BETWEEN_SEARCHES = 2

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        email_obj: email.Email,
        tgtg_manager: TgtgManager,
        firebase_user: FirebaseUser,
        census_api: USCensusAPI,
        google_places_api: GooglePlacesAPI,
        tgtg_data_dir: str,
        mode: str = "prod",
        verbose: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.email = email_obj
        self.tgtg_manager = tgtg_manager
        self.firebase_user = firebase_user
        self.census_api = census_api
        self.google_places_api = google_places_api
        self.firebase_user.send_email_callback = self._maybe_send_email_or_upload
        self.tgtg_data_dir = tgtg_data_dir
        self.mode = mode
        self.verbose = verbose
        self.dry_run = dry_run
        self.time_between_searches = self.TIME_BETWEEN_SEARCHES

        self.last_query_firebase_time: T.Optional[float] = None

    def _get_file_basename(self, uuid: str) -> str:
        return f"tgtg_search_{uuid}"

    def _check_and_run_search_and_email(self) -> None:
        searches: T.Dict[str, too_good_to_go_data_types.Search] = self.firebase_user.get_searches()

        log.print_normal(f"Found {len(searches)} searches")

        for search_hash, search in searches.items():
            self._maybe_run_search(search_hash, search)
            self._maybe_send_email_or_upload(search_hash, search)
            self._maybe_delete_search_files(search_hash, search)
            wait.wait(self.time_between_searches)

    def _get_tgtg_data_file(self, user: str, uuid: str) -> str:
        user_dir = os.path.join(self.tgtg_data_dir, user)
        file_util.make_sure_path_exists(user_dir, ignore_extension=True)

        tgtg_data_json_file = os.path.join(user_dir, f"{self._get_file_basename(uuid)}.json")
        return tgtg_data_json_file

    def _get_tgtg_csv_file(self, user: str, uuid: str) -> str:
        user_dir = os.path.join(self.tgtg_data_dir, user)
        file_util.make_sure_path_exists(user_dir, ignore_extension=True)

        tgtg_data_csv_file = os.path.join(user_dir, f"{self._get_file_basename(uuid)}.csv")
        return tgtg_data_csv_file

    def _get_attachments(self, user: str, uuid: str) -> T.List[str]:
        attachments = []

        tgtg_data_json_file = self._get_tgtg_data_file(user, uuid)
        if os.path.isfile(tgtg_data_json_file):
            attachments.append(tgtg_data_json_file)

        tgtg_data_csv_file = self._get_tgtg_csv_file(user, uuid)
        if os.path.isfile(tgtg_data_csv_file):
            attachments.append(tgtg_data_csv_file)

        return attachments

    def _format_email(self, search: too_good_to_go_data_types.Search, urls: T.List[str]) -> str:
        message = "Hello!\n\n"
        message += "See attached results from your Too Good To Go search:\n\n"
        message += f"Search name: {search['search_name']}\n"
        message += f"Time interval: {search['hour_interval']} hours\n"
        message += f"Start time: {search['hour_start']}\n"
        message += "Search location: \n"
        message += f"{json.dumps(search['region'], indent=4)}\n\n"
        expire_time_seconds = int(self.firebase_user.EXP_TIME_MINUTES * 60.0)
        expire_time_pretty = get_pretty_seconds(expire_time_seconds, use_days=True)
        message += f"Download links (which expire in {expire_time_pretty}):\n\n"
        for url in urls:
            message += f"- {url}\n"
        message += "\n"
        message += "Thanks!\n\n"
        message += "".join(self.FOOD_EMOJIS)

        return message

    def _upload_files(self, uuid: str, search: too_good_to_go_data_types.Search) -> T.List[str]:
        attachments = self._get_attachments(search["user"], uuid)

        log.print_bold(f"Uploading {len(attachments)} files for {uuid}")

        urls = []
        for attachment in attachments:
            try:
                url = self.firebase_user.get_upload_file_url(
                    search["user"], attachment, search["num_results"]
                )
                extension = os.path.splitext(attachment)[1]
                string_url = f"{extension.upper()}: {short_url.shorten_url(url)}"
                log.print_bright(string_url)
                urls.append(string_url)
            except Exception as exception:  # pylint: disable=broad-except
                log.print_warn(f"Failed to upload file: {exception}")

        return urls

    def _maybe_send_email_or_upload(
        self, uuid: str, search: too_good_to_go_data_types.Search
    ) -> None:
        if not search.get("upload_only", False) and not search.get("email_data", False):
            return

        urls = self._upload_files(uuid, search)

        if self.email is None:
            return

        if not search.get("email_data", False):
            return

        log.print_ok(f"Sending email to {search['user']}")

        if not urls:
            log.print_warn("No attachments! Not sending email")
            return

        message = self._format_email(search, urls)

        if self.verbose:
            log.print_normal(f"Message: {message}")

        if self.dry_run:
            log.print_bright("Dry run, not sending email")
            return

        did_send_email = email.send_email(
            [self.email],
            [search["user"]],
            f"Too Good To Go Search Results {random.choice(self.FOOD_EMOJIS)}",
            content=message,
            verbose=self.verbose,
        )

        if not did_send_email:
            return

        self.firebase_user.update_search_email(
            user=search["user"], search_name=search["search_name"]
        )

    def _maybe_delete_search_files(
        self, uuid: str, search: too_good_to_go_data_types.Search
    ) -> None:
        if not search.get("erase_data", False):
            return

        attachments = self._get_attachments(search["user"], uuid)

        log.print_bold(f"Deleting {len(attachments)} files for {uuid}")

        for attachment in attachments:
            try:
                self.firebase_user.delete_search_uploads(
                    search["user"], self._get_file_basename(uuid)
                )
            except Exception as exception:  # pylint: disable=broad-except
                log.print_warn(f"Failed to delete uploads: {exception}")

            # NOTE: removing the file clears any internal cache, so we don't need to
            # do anything else to internal state
            os.remove(attachment)

        self.firebase_user.update_after_data_erase(search["user"], search["search_name"])

    def _maybe_run_search(self, uuid: str, search: too_good_to_go_data_types.Search) -> None:
        timezone = pytz.timezone(search["time_zone"])

        if self.verbose:
            log.print_bright(f"Checking search: {json.dumps(search, indent=4)}")
        else:
            log.print_bright(f"Checking search: {search['search_name']}")

        if not is_time_to_search(
            time.time(),
            search["hour_start"],
            search["hour_interval"],
            search["last_search_time"],
            timezone,
            verbose=self.verbose,
        ):
            log.print_warn("Not within interval, skipping search.")

            if self.verbose:
                log.print_normal("Inputs:")
                log.print_normal(f"Time: {time.time()}")
                log.print_normal(f"Start hour: {search['hour_start']}")
                log.print_normal(f"Interval hour: {search['hour_interval']}")
                log.print_normal(f"Last search time: {search['last_search_time']}")
                log.print_normal(f"Timezone: {timezone}")
            return

        log.print_ok("Within interval, running search.")

        region_dict = search["region"]

        region = too_good_to_go_data_types.Region(
            latitude=region_dict["latitude"],
            longitude=region_dict["longitude"],
            radius=region_dict["radius"],
        )
        results: too_good_to_go_data_types.GetItemResponse = self.tgtg_manager.search_region(
            region=region
        )

        num_results = len(results["results"])

        log.print_normal(f"Found {num_results} results")

        if num_results == 0:
            log.print_warn("No results found, not saving anything")
        else:
            if search["store_raw_data"]:
                tgtg_data_json_file = self._get_tgtg_data_file(search["user"], uuid)
                self.tgtg_manager.write_data_to_json(results, tgtg_data_json_file, timezone)

            # for result in results["results"]:
            #     address = str(result["store"]["store_location"]["address"]["address_line"])
            #     # TODO(ross): get the data we actually care about once we know it
            #     # and store it properly
            #     census_data = self.census_api.get_census_data("B01001_001E", address)
            #     # google_data = self.google_places_api.search_places(address)
            #     log.print_normal(f"Census data: {census_data}")
            #     log.print_normal(f"Google data: {google_data}")

            tgtg_data_csv_file = self._get_tgtg_csv_file(search["user"], uuid)
            self.tgtg_manager.write_data_to_csv(results, tgtg_data_csv_file, timezone)

        # TODO(ross): this is pretty inefficient, we potentially update the firebase
        # database for each search rather than just doing it user by user at the end, but
        # this module doesn't really have a sense of user, just a list of searches. Would need
        # to make cache the db before running searches and then update the db after running on
        # a user by user basis instead of search by search.
        self.firebase_user.update_search_stats(
            search["user"], search["search_name"], time.time(), num_results, uuid
        )

    def _check_to_firebase(self) -> None:
        self.firebase_user.health_ping()

    def _check_from_firebase(self) -> None:
        self._maybe_get_synchronous_update_from_firebase()
        self.firebase_user.check_and_maybe_handle_firebase_db_updates()

    def _maybe_get_synchronous_update_from_firebase(self) -> None:
        update_from_firebase = False
        if self.last_query_firebase_time is None:
            update_from_firebase = True
        else:
            time_since_last_update = time.time() - self.last_query_firebase_time
            update_from_firebase = (
                time_since_last_update > self.TIME_BETWEEN_FIREBASE_QUERIES[self.mode]
            )

        if update_from_firebase:
            self.last_query_firebase_time = time.time()
            self.firebase_user.update_watchers()
        else:
            time_till_next_update = int(
                self.TIME_BETWEEN_FIREBASE_QUERIES[self.mode] - time_since_last_update
            )
            next_update_str = fmt_util.get_pretty_seconds(time_till_next_update)
            log.print_normal(f"Next firebase manual refresh in {next_update_str}")

    def init(self) -> None:
        self.tgtg_manager.init()

    def run(self) -> None:
        self.tgtg_manager.run()
        self._check_from_firebase()
        self._check_and_run_search_and_email()
        self._check_to_firebase()
