import json
import os
import random
import time
import typing as T

import pytz

from firebase.storage import FirebaseStorage
from firebase.user import FirebaseUser
from search_context.google_places import GooglePlacesAPI
from search_context.us_census import USCensusAPI
from search_context.util import (
    METERS_PER_MILE,
    get_city_center_coordinates,
    get_search_grid_details,
)
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
        firebase_cloud_storage: FirebaseStorage,
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
        self.firebase_cloud_storage = firebase_cloud_storage
        self.census_api = census_api
        self.google_places_api = google_places_api
        self.firebase_user.send_email_callback = self._maybe_send_email_or_upload
        self.tgtg_data_dir = tgtg_data_dir
        self.mode = mode
        self.verbose = verbose
        self.dry_run = dry_run
        self.time_between_searches = self.TIME_BETWEEN_SEARCHES

        self.last_query_firebase_time: T.Optional[float] = None

    def _get_file_basename(self, search: too_good_to_go_data_types.Search, uuid: str) -> str:
        name_construct = [
            "tgtg_search",
            search["search_name"],
            str(search["region"]["latitude"]),
            str(search["region"]["longitude"]),
            str(search["region"]["radius"]),
            uuid,
        ]

        return "_".join(name_construct)

    def _check_and_run_search_and_email(self) -> None:
        searches: T.Dict[str, too_good_to_go_data_types.Search] = self.firebase_user.get_searches()

        log.print_normal(f"Found {len(searches)} searches")

        for search_hash, search in searches.items():
            self._maybe_run_search(search_hash, search)
            self._maybe_send_email_or_upload(search_hash, search)
            self._maybe_delete_search_files(search_hash, search)
            wait.wait(self.time_between_searches)

    def _check_and_maybe_run_search_context_job(self) -> None:
        search_contexts: T.List[too_good_to_go_data_types.SearchContext] = (
            self.firebase_user.get_search_contexts()
        )
        self._maybe_run_search_context_jobs(search_contexts)

    def _get_tgtg_data_file(self, user: str, filename: str) -> str:
        user_dir = os.path.join(self.tgtg_data_dir, user)
        file_util.make_sure_path_exists(user_dir, ignore_extension=True)

        tgtg_data_json_file = os.path.join(user_dir, f"{filename}.json")
        return tgtg_data_json_file

    def _get_tgtg_csv_file(self, user: str, filename: str) -> str:
        user_dir = os.path.join(self.tgtg_data_dir, user)
        file_util.make_sure_path_exists(user_dir, ignore_extension=True)

        tgtg_data_csv_file = os.path.join(user_dir, f"{filename}.csv")
        return tgtg_data_csv_file

    def _get_attachments(self, user: str, filename: str) -> T.List[str]:
        attachments = []

        tgtg_data_json_file = self._get_tgtg_data_file(user, filename)
        if os.path.isfile(tgtg_data_json_file):
            attachments.append(tgtg_data_json_file)

        tgtg_data_csv_file = self._get_tgtg_csv_file(user, filename)
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
        expire_time_seconds = int(self.firebase_cloud_storage.EXP_TIME_MINUTES * 60.0)
        expire_time_pretty = get_pretty_seconds(expire_time_seconds, use_days=True)
        message += f"Download links (which expire in {expire_time_pretty}):\n\n"
        for url in urls:
            message += f"- {url}\n"
        message += "\n"
        message += "Thanks!\n\n"
        message += "".join(self.FOOD_EMOJIS)

        return message

    def _upload_files(self, uuid: str, search: too_good_to_go_data_types.Search) -> T.List[str]:
        attachments = self._get_attachments(search["user"], self._get_file_basename(search, uuid))

        log.print_bold(f"Uploading {len(attachments)} files for {uuid}")

        urls = []
        for attachment in attachments:
            try:
                url = self.firebase_cloud_storage.upload_file_and_get_url(
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

        blob_name = self._get_file_basename(search, uuid)
        attachments = self._get_attachments(search["user"], blob_name)

        log.print_bold(f"Deleting {len(attachments)} files for {uuid}")

        for attachment in attachments:
            try:
                self.firebase_cloud_storage.delete_search_uploads(search["user"], blob_name)
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

            tgtg_data_csv_file = self._get_tgtg_csv_file(
                search["user"], self._get_file_basename(search, uuid)
            )
            self.tgtg_manager.write_data_to_csv(results, tgtg_data_csv_file, timezone)

        # TODO(ross): this is pretty inefficient, we potentially update the firebase
        # database for each search rather than just doing it user by user at the end, but
        # this module doesn't really have a sense of user, just a list of searches. Would need
        # to make cache the db before running searches and then update the db after running on
        # a user by user basis instead of search by search.
        self.firebase_user.update_search_stats(
            search["user"], search["search_name"], time.time(), num_results, uuid
        )

    def _maybe_run_search_context_jobs(
        self, search_contexts: T.List[too_good_to_go_data_types.SearchContext]
    ) -> None:
        for search_context in search_contexts:
            if not search_context["trigger_search"]:
                continue

            city = search_context["city"]

            log.print_bright(f"Found {city} search contexts trigger")

            if self.verbose:
                log.print_normal(f"{json.dumps(search_context, indent=4)}")

            city_center_coordinates = get_city_center_coordinates(city)

            if city_center_coordinates is None:
                center_lat = 0.0
                center_lon = 0.0
            else:
                center_lat, center_lon = city_center_coordinates

            sent_city_center_coordinates = search_context["city_center"]
            sent_center_lat, sent_center_lon = sent_city_center_coordinates
            max_grid_resolution_width_meters = search_context["grid_width_meters"]
            radius_meters = search_context["radius_miles"] * METERS_PER_MILE
            max_cost_per_city = search_context["max_cost_per_city"]
            cost_per_search = search_context["cost_per_square"]

            if sent_center_lat != center_lat or sent_center_lon != center_lon:
                log.print_warn(
                    "Search context does not match current user or city center coordinates: "
                    f"{sent_city_center_coordinates} vs {city_center_coordinates}"
                )

            # Get the maximum width of the viewport for our search to have good resolution
            # since places api limits the search results to 20 max regardless of the radius
            log.print_normal(f"Using city center: {sent_city_center_coordinates}")
            log.print_normal(f"Using maximum viewpoint width: {max_grid_resolution_width_meters}")
            log.print_normal(f"Using radius: {radius_meters}")
            log.print_normal(f"Using max cost per city: {max_cost_per_city}")
            log.print_normal(f"Using cost per search: {cost_per_search}")

            grid, city_center_coordinates, num_grid_squares, total_cost, new_radius_meters = (
                get_search_grid_details(
                    city,
                    max_grid_resolution_width_meters,
                    radius_meters,
                    max_cost_per_city,
                    cost_per_search,
                )
            )

            log.print_ok_blue(f"Final radius: {new_radius_meters / METERS_PER_MILE:.2f} miles")
            log.print_ok_blue(f"Number of grid squares: {num_grid_squares}")
            log.print_ok_blue(f"Grid size: {len(grid)}")
            log.print_ok_blue(f"Grid resolution: {max_grid_resolution_width_meters} meters")
            log.print_ok_blue(f"Total cost: ${total_cost:.2f}")

            # TODO(ross): now run the actual search and store/publish the results, will need to
            # update the firebase db with the results and this will need to be kicked off in
            # its own thread or process so that we can continue to check for new searches as it
            # will take a while to run the search and we don't want to block the main loop

            self.firebase_user.clear_search_context(search_context["user"], search_context["city"])

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
        self._check_and_maybe_run_search_context_job()
        self._check_to_firebase()
