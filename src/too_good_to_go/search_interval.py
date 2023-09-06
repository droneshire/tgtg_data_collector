import datetime
import typing as T

from util import fmt_util, log

INTERVALS = [1, 2, 3, 4, 6, 8, 12, 24]
LOOKBACK_DAYS = 1
SECONDS_PER_DAY = 60 * 60 * 24
SECONDS_PER_HOUR = 60 * 60
SECONDS_PER_MINUTE = 60


def convert_datetime_list_to_timestamp_list(
    datetime_list: T.List[datetime.datetime],
) -> T.List[float]:
    return [datetime.timestamp() for datetime in datetime_list]


def get_start_of_last_interval(
    interval_times: T.List[float], now_uclock: float, verbose: bool = False
) -> T.Optional[float]:
    # assumes last search time is within the last 24 hours
    start_of_last_interval: T.Optional[float] = None

    if verbose:
        interval_str = "\n\t".join([str(interval) for interval in interval_times])
        log.print_normal(f"Interval times:\n\t{interval_str}")
        log.print_normal(f"Current time: {datetime.datetime.fromtimestamp(now_uclock)}")

    if len(interval_times) == 1:
        start_of_last_interval = interval_times[0]
        if verbose:
            start_of_last_interval_date = datetime.datetime.fromtimestamp(start_of_last_interval)
            log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval_date}")
        return start_of_last_interval

    for i, interval_time in enumerate(interval_times):
        if interval_time < now_uclock:
            continue

        if interval_time == now_uclock:
            start_of_last_interval = interval_time
            if verbose:
                start_of_last_interval_date = datetime.datetime.fromtimestamp(
                    start_of_last_interval
                )
                log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval_date}")
            break

        if i == 0:
            # should be impossible to reach based on the creation of the interval times
            continue

        start_of_last_interval = interval_times[i - 1]
        start_of_last_interval_date = datetime.datetime.fromtimestamp(start_of_last_interval)
        if verbose:
            log.print_ok_blue_arrow(f"Last interval: {start_of_last_interval_date}")
        break

    return start_of_last_interval


def get_localized_start_time(
    now_uclock: float, start_hour: int, time_zone: T.Any, verbose: bool = False
) -> float:
    now = datetime.datetime.fromtimestamp(now_uclock)
    now = time_zone.localize(now)

    start_time = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    start_time_uclock = start_time.timestamp()

    if verbose:
        log.print_normal(f"Current time: {now}, {now_uclock}")
        log.print_normal(f"Today start time: {start_time}, {start_time_uclock}")
        log.print_normal(f"Start hour: {start_hour}")

    return start_time_uclock


def is_time_to_search(
    now_uclock: float,
    start_hour: int,
    interval_hour: int,
    last_search_time: float,
    time_zone: T.Any,
    verbose: bool = False,
) -> bool:
    if interval_hour not in INTERVALS:
        log.print_warn(f"Invalid interval: {interval_hour}. " f"Valid intervals: {INTERVALS}")
        return False

    lookback_days = LOOKBACK_DAYS

    start_time_uclock = get_localized_start_time(now_uclock, start_hour, time_zone, verbose)

    yesterday_start_time = start_time_uclock - SECONDS_PER_DAY * lookback_days
    num_intervals = 24 // interval_hour
    # we want at least 2 intervals to check against
    range_value = max((lookback_days + 1) * num_intervals, 2)

    interval_times = [
        yesterday_start_time + i * SECONDS_PER_HOUR * interval_hour for i in range(range_value)
    ]

    last_search_time_datetime = datetime.datetime.fromtimestamp(last_search_time)

    if verbose:
        log.print_ok_blue("Checking if we are within the interval")
        log.print_normal(
            f"Interval start time: {datetime.datetime.fromtimestamp(yesterday_start_time)}, "
            f"{yesterday_start_time}"
        )
        log.print_normal(f"Last search time: {last_search_time_datetime}")
        log.print_normal(f"Interval: {interval_hour}")
        time_since_update = int(now_uclock - last_search_time)
        log.print_normal(f"Last search: {fmt_util.get_pretty_seconds(time_since_update)} ago")
        time_since_interval_start_time = int(now_uclock - yesterday_start_time)
        log.print_normal(
            f"Time since interval time: {fmt_util.get_pretty_seconds(time_since_interval_start_time)}"
        )

    if last_search_time > now_uclock:
        log.print_warn("Last search time is in the future, skipping")
        return False

    start_of_last_interval = get_start_of_last_interval(interval_times, now_uclock, verbose)

    if start_of_last_interval is None:
        return True

    time_since_last_interval = int(now_uclock - start_of_last_interval)
    time_since_last_search = int(now_uclock - last_search_time)

    if verbose:
        log.print_normal(
            f"Last interval: {fmt_util.get_pretty_seconds(time_since_last_interval)} ago"
        )
        log.print_normal(f"Last search: {fmt_util.get_pretty_seconds(time_since_last_search)} ago")
    if start_of_last_interval is not None and last_search_time >= start_of_last_interval:
        if verbose:
            log.print_normal("Last search time is in the window, skipping")
        return False

    if verbose:
        log.print_ok_arrow("Last search is stale, running search")
    return True
