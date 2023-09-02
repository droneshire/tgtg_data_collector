import datetime
import json
import typing as T

import pytz

from firebase.user import FirebaseUser
from too_good_to_go import data_types as too_good_to_go_data_types
from too_good_to_go.manager import TgtgManager
from util import fmt_util, log


class TgtgCollectorBackend:
    def __init__(
        self,
        tgtg_manager: TgtgManager,
        firebase_user: FirebaseUser,
        tgtg_data_json_file: str,
        verbose: bool = False,
    ) -> None:
        self.tgtg_manager = tgtg_manager
        self.firebase_user = firebase_user
        self.tgtg_data_json_file = tgtg_data_json_file
        self.verbose = verbose

    def _check_and_run_searches(self) -> None:
        searches: T.List[too_good_to_go_data_types.Search] = self.firebase_user.get_searches()

        for search in searches:
            self._run_search(search)

    def _run_search(self, search: too_good_to_go_data_types.Search) -> None:
        if self.verbose:
            log.print_normal(f"Running search: {json.dumps(search, indent=4)}")

        timezone = pytz.timezone(search["time_zone"])
        now = datetime.datetime.now(tz=timezone)

        if self.is_within_interval(
            now, search["hour_start"], search["hour_interval"], search["last_search_time"], timezone
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

        if self.verbose:
            log.print_normal(f"Found {len(results)} results")

        self.tgtg_manager.write_data_to_json(results, self.tgtg_data_json_file)

    @staticmethod
    def is_within_interval(
        now: datetime.datetime,
        start_hour: int,
        interval_hour: int,
        last_search_time: float,
        time_zone: T.Any,
        verbose: bool = False,
    ) -> bool:
        lookback_days = 1
        start_time = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        yesterday_start_time = start_time - datetime.timedelta(days=lookback_days)
        interval_times = [
            yesterday_start_time + datetime.timedelta(hours=interval_hour * i)
            for i in range(lookback_days * 24 // interval_hour)
        ]

        last_search_time_datetime = datetime.datetime.fromtimestamp(last_search_time, tz=time_zone)

        if verbose:
            log.print_ok_blue("Checking if we are within the interval")
            log.print_normal(f"Current time: {now}")
            log.print_normal(f"Today start time: {start_time}")
            log.print_normal(f"Interval start time: {yesterday_start_time}")
            log.print_normal(f"Interval: {interval_hour}")
            time_since_update = int(now.timestamp() - last_search_time)
            log.print_normal(f"Last search: {fmt_util.get_pretty_seconds(time_since_update)} ago")
            log.print_normal(f"Last search time: {last_search_time_datetime}")

        if last_search_time_datetime > now:
            log.print_warn("Last search time is in the future, skipping")
            return True

        # assumes last search time is within the last 24 hours
        start_of_last_interval = None
        for i, interval_time in enumerate(interval_times):
            if interval_time < now:
                continue

            if interval_time == now:
                start_of_last_interval = interval_time
                log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval}")
                break

            if i == 0:
                # should be impossible to reach based on the creation of the interval times
                continue

            start_of_last_interval = interval_times[i - 1]
            log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval}")
            break

        if (
            start_of_last_interval is not None
            and last_search_time_datetime >= start_of_last_interval
        ):
            if verbose:
                log.print_normal("Last search time is in the window, skipping")
            return True

        log.print_ok_arrow("Last search is stale, running search")
        return False

    def init(self) -> None:
        self.tgtg_manager.init()

    def run(self) -> None:
        self.firebase_user.health_ping()
        self._check_and_run_searches()
