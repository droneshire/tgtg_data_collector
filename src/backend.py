import datetime
import json
import os
import random
import time
import typing as T

import pytz

from firebase.user import FirebaseUser
from too_good_to_go import data_types as too_good_to_go_data_types
from too_good_to_go.manager import TgtgManager
from util import email, file_util, fmt_util, log


class TgtgCollectorBackend:
    INTERVALS = [1, 2, 3, 4, 6, 8, 12, 24]
    TIME_BETWEEN_FIREBASE_QUERIES = {
        "prod": 60 * 60 * 24,
        "dev": 60 * 1,
    }

    def __init__(
        self,
        email_obj: email.Email,
        tgtg_manager: TgtgManager,
        firebase_user: FirebaseUser,
        tgtg_data_dir: str,
        mode: str = "prod",
        verbose: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.email = email_obj
        self.tgtg_manager = tgtg_manager
        self.firebase_user = firebase_user
        self.tgtg_data_dir = tgtg_data_dir
        self.mode = mode
        self.verbose = verbose
        self.dry_run = dry_run

        self.last_query_firebase_time: T.Optional[float] = None

    def _check_and_run_search_and_email(self) -> None:
        searches: T.Dict[str, too_good_to_go_data_types.Search] = self.firebase_user.get_searches()

        log.print_normal(f"Found {len(searches)} searches")

        for search_hash, search in searches.items():
            self._maybe_run_search(search_hash, search)
            self._maybe_send_email(search_hash, search)

    def _get_tgtg_data_file(self, user: str, uuid: str) -> str:
        user_dir = os.path.join(self.tgtg_data_dir, user)
        file_util.make_sure_path_exists(user_dir, ignore_extension=True)

        tgtg_data_json_file = os.path.join(user_dir, f"tgtg_search_{uuid}.json")
        return tgtg_data_json_file

    def _get_tgtg_csv_file(self, user: str, uuid: str) -> str:
        user_dir = os.path.join(self.tgtg_data_dir, user)
        file_util.make_sure_path_exists(user_dir, ignore_extension=True)

        tgtg_data_csv_file = os.path.join(user_dir, f"tgtg_search_{uuid}.csv")
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

    def _maybe_send_email(self, uuid: str, search: too_good_to_go_data_types.Search) -> None:
        if self.email is None:
            return

        if not search.get("email_data", False):
            return

        food_emojis = ["🍕", "🍔", "🍟", "🍗", "🍖", "🌭", "🍿", "🍛", "🍜", "🍝", "🍤"]

        message = "Hello!\n\n"
        message += "See attached results from your Too Good To Go search:\n\n"
        message += f"Search name: {search['search_name']}\n"
        message += f"Time interval: {search['hour_interval']} hours\n"
        message += f"Start time: {search['hour_start']}\n"
        message += "Search location: \n"
        message += f"{json.dumps(search['region'], indent=4)}\n\n"
        message += "Thanks!\n\n"
        message += "".join(food_emojis)

        log.print_ok(f"Sending email to {search['user']}")

        if self.verbose:
            log.print_normal(f"Message: {message}")

        if self.dry_run:
            log.print_bright("Dry run, not sending email")
            return

        did_send_email = True
        attachments = self._get_attachments(search["user"], uuid)

        if attachments:
            did_send_email = email.send_email(
                [self.email],
                [search["user"]],
                f"Too Good To Go Search Results {random.choice(food_emojis)}",
                attachments=attachments,
                content=message,
                verbose=self.verbose,
            )
        else:
            log.print_warn("No attachments! Not sending email")

        if did_send_email:
            self.firebase_user.update_search_email(
                user=search["user"], search_name=search["search_name"]
            )

    def _maybe_run_search(self, uuid: str, search: too_good_to_go_data_types.Search) -> None:
        timezone = pytz.timezone(search["time_zone"])
        now = datetime.datetime.now()
        now = timezone.localize(now)

        if self.verbose:
            log.print_normal(f"Checking search: {json.dumps(search, indent=4)}")
        else:
            log.print_normal(f"Checking search: {search['search_name']}")

        if not self.is_time_to_search(
            now,
            search["hour_start"],
            search["hour_interval"],
            search["last_search_time"],
            verbose=self.verbose,
        ):
            log.print_warn("Not within interval, skipping")
            return

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
            tgtg_data_json_file = self._get_tgtg_data_file(search["user"], uuid)
            self.tgtg_manager.write_data_to_json(results, tgtg_data_json_file)

        # TODO(ross): this is pretty inefficient, we potentially update the firebase
        # database for each search rather than just doing it user by user at the end, but
        # this module doesn't really have a sense of user, just a list of searches. Would need
        # to make cache the db before running searches and then update the db after running on
        # a user by user basis instead of search by search.
        # import pdb; pdb.set_trace()
        self.firebase_user.update_search_stats(
            search["user"], search["search_name"], time.time(), num_results
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

    @staticmethod
    def is_time_to_search(
        now: datetime.datetime,
        start_hour: int,
        interval_hour: int,
        last_search_time: float,
        verbose: bool = False,
    ) -> bool:
        if interval_hour not in TgtgCollectorBackend.INTERVALS:
            log.print_warn(
                f"Invalid interval: {interval_hour}. "
                f"Valid intervals: {TgtgCollectorBackend.INTERVALS}"
            )
            return False

        lookback_days = 1
        start_time = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        yesterday_start_time = start_time - datetime.timedelta(days=lookback_days)
        num_intervals = 24 // interval_hour
        # we want at least 2 intervals to check against
        range_value = max((lookback_days + 1) * num_intervals, 2)

        interval_times = [
            yesterday_start_time + datetime.timedelta(hours=interval_hour * i)
            for i in range(range_value)
        ]

        last_search_time_datetime = datetime.datetime.fromtimestamp(last_search_time)

        if verbose:
            log.print_ok_blue("Checking if we are within the interval")
            log.print_normal(f"Current time: {now}")
            log.print_normal(f"Today start time: {start_time}")
            log.print_normal(f"Interval start time: {yesterday_start_time}")
            log.print_normal(f"Last search time: {last_search_time_datetime}")
            log.print_normal(f"Interval: {interval_hour}")
            time_since_update = int(now.timestamp() - last_search_time)
            log.print_normal(f"Last search: {fmt_util.get_pretty_seconds(time_since_update)} ago")
            time_since_start_time = int(now.timestamp() - yesterday_start_time.timestamp())
            log.print_normal(
                f"Time since interval time: {fmt_util.get_pretty_seconds(time_since_start_time)}"
            )

        if last_search_time > now.timestamp():
            log.print_warn("Last search time is in the future, skipping")
            return False

        start_of_last_interval = TgtgCollectorBackend.get_start_of_last_interval(
            interval_times, now, verbose
        )

        if start_of_last_interval is None:
            return True

        time_since_last_interval = int(now.timestamp() - start_of_last_interval.timestamp())
        time_since_last_search = int(now.timestamp() - last_search_time)
        if verbose:
            log.print_normal(
                f"Last interval: {fmt_util.get_pretty_seconds(time_since_last_interval)} ago"
            )
            log.print_normal(
                f"Last search: {fmt_util.get_pretty_seconds(time_since_last_search)} ago"
            )
        if (
            start_of_last_interval is not None
            and last_search_time >= start_of_last_interval.timestamp()
        ):
            if verbose:
                log.print_normal("Last search time is in the window, skipping")
            return False

        log.print_ok_arrow("Last search is stale, running search")
        return True

    @staticmethod
    def get_start_of_last_interval(
        interval_times: T.List[datetime.datetime], now: datetime.datetime, verbose: bool = False
    ) -> T.Optional[datetime.datetime]:
        # assumes last search time is within the last 24 hours
        start_of_last_interval = None

        if verbose:
            interval_str = "\n\t".join([str(interval) for interval in interval_times])
            log.print_normal(f"Interval times:\n\t{interval_str}")
            log.print_normal(f"Current time: {now}")

        if len(interval_times) == 1:
            start_of_last_interval = interval_times[0]
            if verbose:
                log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval}")
            return start_of_last_interval

        for i, interval_time in enumerate(interval_times):
            if interval_time < now:
                continue

            if interval_time == now:
                start_of_last_interval = interval_time
                if verbose:
                    log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval}")
                break

            if i == 0:
                # should be impossible to reach based on the creation of the interval times
                continue

            start_of_last_interval = interval_times[i - 1]
            if verbose:
                log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval}")
            break
        return start_of_last_interval

    def init(self) -> None:
        self.tgtg_manager.init()

    def run(self) -> None:
        self._check_from_firebase()
        self._check_and_run_search_and_email()
        self._check_to_firebase()
