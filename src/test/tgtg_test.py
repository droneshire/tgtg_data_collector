import datetime
import os
import tempfile
import typing as T
import unittest

import pytz

from firebase.user import FirebaseUser
from too_good_to_go.data_types import Search
from too_good_to_go.search_interval import (
    INTERVALS,
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
    get_start_of_last_interval,
    is_time_to_search,
)
from util import log


class TgtgTest(unittest.TestCase):
    test_email: str = "test@gmail.com"
    verbose: bool = False
    time_zone = pytz.timezone("America/Los_Angeles")
    time_zone_other = pytz.timezone("America/New_York")

    def setUp(self) -> None:
        # pylint: disable=consider-using-with
        self.temp_credentials_file = tempfile.NamedTemporaryFile(
            delete=False, suffix="_credentials.json"
        )

        with open(self.temp_credentials_file.name, "w", encoding="utf-8") as outfile:
            outfile.write("{}")

    def tearDown(self) -> None:
        if self.temp_credentials_file and os.path.isfile(self.temp_credentials_file.name):
            os.remove(self.temp_credentials_file.name)

    def test_uuid(self) -> None:
        search: Search = Search(
            {
                "user": self.test_email,
                "search_name": "",
                "region": {
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "radius": 3,
                },
                "hour_start": 4,
                "hour_interval": 5,
                "time_zone": "America/Los_Angeles",
                "last_search_time": 0,
                "email_data": False,
            }
        )

        uuid = FirebaseUser.get_uuid(search)
        self.assertEqual(uuid, "3341a7c22ee8f9232391875d4973018c")

    def test_timezone_changes(self) -> None:
        start_time = datetime.datetime(2023, 1, 1, 0, 0, 0, 0)
        start_time_local = self.time_zone.localize(start_time)

        start_time_other = self.time_zone_other.localize(start_time)

        start_time_local_uclock = start_time_local.timestamp()
        start_time_other_uclock = start_time_other.timestamp()

        self.assertAlmostEqual(start_time_local_uclock - start_time_other_uclock, 3 * 60 * 60, 1)

    def test_finding_interval(self) -> None:
        test_cases: T.List[T.Tuple[T.List[float], float, float, int, int]] = []

        start_time = datetime.datetime(2023, 1, 1, 0, 0, 0, 0)
        start_time = self.time_zone.localize(start_time)
        start_time_uclock = start_time.timestamp()

        for interval_hour in INTERVALS:
            time_intervals = [
                start_time_uclock + i * SECONDS_PER_HOUR * interval_hour
                for i in range(max(24 // interval_hour, 2))
            ]

            for hour in range(interval_hour):
                now_uclock = start_time_uclock + hour * SECONDS_PER_HOUR
                test_cases.append(
                    (time_intervals, now_uclock, start_time_uclock, interval_hour, hour)
                )

            now_uclock = start_time_uclock + interval_hour * SECONDS_PER_HOUR
            test_cases.append(
                (
                    time_intervals,
                    now_uclock,
                    start_time_uclock + SECONDS_PER_HOUR * interval_hour,
                    interval_hour,
                    interval_hour,
                )
            )

            for case in test_cases:
                start_of_matching_interval = get_start_of_last_interval(case[0], case[1])
                self.assertIsNotNone(start_of_matching_interval)

                if start_of_matching_interval is None:
                    continue

                if self.verbose:
                    start_of_matching_interval_date = datetime.datetime.fromtimestamp(
                        start_of_matching_interval
                    )
                    log.print_normal(
                        f"Start time: {datetime.datetime.fromtimestamp(case[2])},  "
                        f"interval: {case[3]}, "
                        f"offset: {case[4]} now: {datetime.datetime.fromtimestamp(case[1])},"
                        f" start of matching interval: {start_of_matching_interval_date}"
                    )
                self.assertEqual(start_of_matching_interval, case[2])

    def test_time_within_divisors_of_24(self) -> None:
        test_cases: T.List[T.Tuple[float, int, int, float, bool]] = []

        test_start_hour = 6
        last_search_time_start = datetime.datetime(2023, 1, 1, test_start_hour, 0, 0, 0)
        last_search_time_start_uclock = last_search_time_start.timestamp()

        intervals = range(25)

        for interval in intervals:
            test_cases.append(
                (
                    last_search_time_start_uclock + SECONDS_PER_HOUR * interval,
                    test_start_hour,
                    interval,
                    last_search_time_start_uclock,
                    interval in INTERVALS,
                )
            )
        for test_case in test_cases:
            result = is_time_to_search(
                now_uclock=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=self.time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])

    def test_time_all_starts_within_interval(self) -> None:
        test_cases: T.List[T.Tuple[float, int, int, float, bool]] = []

        test_start_hour = 6
        last_search_time_start = datetime.datetime(2023, 1, 1, test_start_hour, 0, 0, 0)
        last_search_time_start_uclock = last_search_time_start.timestamp()

        for interval in INTERVALS:
            now_uclock = last_search_time_start_uclock + SECONDS_PER_HOUR * interval
            start_hour = test_start_hour
            interval_hour = interval
            last_search_time_start_timestamp = last_search_time_start_uclock

            test_cases.append(
                (
                    now_uclock,
                    start_hour,
                    interval_hour,
                    last_search_time_start_timestamp,
                    True,
                )
            )

        for test_case in test_cases:
            result = is_time_to_search(
                now_uclock=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=self.time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])

    def test_time_all_starts_outside_interval(self) -> None:
        test_cases: T.List[T.Tuple[float, int, int, float, bool]] = []

        test_start_hour = 6
        last_search_time_start = datetime.datetime(2023, 1, 1, test_start_hour, 0, 0, 0)
        last_search_time_start_uclock = last_search_time_start.timestamp()

        self.assertEqual(last_search_time_start.day, 1)
        self.assertEqual(last_search_time_start.month, 1)
        self.assertEqual(last_search_time_start.year, 2023)
        self.assertEqual(last_search_time_start.hour, test_start_hour)
        self.assertEqual(last_search_time_start.minute, 0)
        self.assertEqual(last_search_time_start.second, 0)
        self.assertEqual(last_search_time_start.timestamp(), 1672581600.0)

        for interval in INTERVALS:
            now_uclock = (
                last_search_time_start_uclock
                + SECONDS_PER_HOUR * (interval - 1)
                - SECONDS_PER_MINUTE * 30
            )
            start_hour = test_start_hour
            interval_hour = interval

            test_cases.append(
                (
                    now_uclock,
                    start_hour,
                    interval_hour,
                    last_search_time_start_uclock,
                    False,
                )
            )

        for test_case in test_cases:
            result = is_time_to_search(
                now_uclock=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=self.time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])


if __name__ == "__main__":
    unittest.main()
