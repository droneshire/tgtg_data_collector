import datetime
import json
import typing as T

import pytz

from firebase.user import FirebaseUser
from too_good_to_go import data_types as too_good_to_go_data_types
from too_good_to_go.manager import TgtgManager
from util import fmt_util, log


class TgtgCollectorBackend:
    INTERVALS = [1, 2, 3, 4, 6, 8, 12, 24]

    def __init__(
        self,
        tgtg_manager: TgtgManager,
        firebase_user: FirebaseUser,
        tgtg_data_json_file: str,
        verbose: bool = False,
    ) -> None:
        self.tgtg_manager = tgtg_manager
        self.firebase_user = firebase_user
        self.tgtg_data_dir = tgtg_data_dir
        self.verbose = verbose

    def _check_and_run_searches(self) -> None:
        searches: T.List[too_good_to_go_data_types.Search] = self.firebase_user.get_searches()

        for search in searches:
            self._maybe_run_search(search)

    def _maybe_run_search(self, search: too_good_to_go_data_types.Search) -> None:
        if self.verbose:
            log.print_normal(f"Running search: {json.dumps(search, indent=4)}")

        timezone = pytz.timezone(search["time_zone"])
        now = datetime.datetime.now()
        now = timezone.localize(now)

        if not self.is_time_to_search(
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

        if len(results) == 0:
            log.print_warn("No results found, not saving anything")
            return

        tgtg_data_json_file = os.path.join(
            self.tgtg_data_dir, f"tgtg_search_{search['uuid']}_{search['user']}.json"
        )
        self.tgtg_manager.write_data_to_json(results, tgtg_data_json_file)

    @staticmethod
    def is_time_to_search(
        now: datetime.datetime,
        start_hour: int,
        interval_hour: int,
        last_search_time: float,
        time_zone: T.Any,
        verbose: bool = False,
    ) -> bool:
        if interval_hour not in TgtgCollectorBackend.INTERVALS:
            log.print_warn(f"Invalid interval: {interval_hour}")
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
        last_search_time_datetime = time_zone.localize(last_search_time_datetime)

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

        if last_search_time_datetime > now:
            log.print_warn("Last search time is in the future, skipping")
            return False

        start_of_last_interval = TgtgCollectorBackend.get_start_of_last_interval(
            interval_times, now, verbose
        )

        if start_of_last_interval is None:
            return True

        time_since_last_interval = int(now.timestamp() - start_of_last_interval.timestamp())
        log.print_normal(
            f"Last interval: {fmt_util.get_pretty_seconds(time_since_last_interval)} ago"
        )
        if (
            start_of_last_interval is not None
            and last_search_time_datetime >= start_of_last_interval
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
            log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval}")
            return start_of_last_interval

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
        return start_of_last_interval

    def init(self) -> None:
        self.tgtg_manager.init()

    def run(self) -> None:
        self.firebase_user.health_ping()
        self._check_and_run_searches()
