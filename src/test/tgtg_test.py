import datetime
import os
import tempfile
import typing as T
import unittest

import pytz

from backend import TgtgCollectorBackend
from firebase.user import FirebaseUser
from too_good_to_go.data_types import Search
from util import log


class TgtgTest(unittest.TestCase):
    test_email: str = "test@gmail.com"
    verbose: bool = False
    time_zone = pytz.timezone("America/Los_Angeles")

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

    def test_finding_interval(self) -> None:
        test_cases: T.List[
            T.Tuple[T.List[datetime.datetime], datetime.datetime, datetime.datetime, int, int]
        ] = []

        start_time = datetime.datetime(2023, 1, 1, 0, 0, 0, 0)
        start_time = self.time_zone.localize(start_time)

        for interval_hour in TgtgCollectorBackend.INTERVALS:
            time_intervals = [
                start_time + datetime.timedelta(hours=i * interval_hour)
                for i in range(max(24 // interval_hour, 2))
            ]

            for hour in range(interval_hour):
                now = start_time + datetime.timedelta(hours=hour)
                test_cases.append((time_intervals, now, start_time, interval_hour, hour))

            now = start_time + datetime.timedelta(hours=interval_hour)
            test_cases.append(
                (
                    time_intervals,
                    now,
                    start_time + datetime.timedelta(hours=interval_hour),
                    interval_hour,
                    interval_hour,
                )
            )

            for case in test_cases:
                start_of_matching_interval = TgtgCollectorBackend.get_start_of_last_interval(
                    case[0], case[1]
                )
                if self.verbose:
                    log.print_normal(
                        f"Start time: {case[2]}, interval: {case[3]}, "
                        f"offset: {case[4]} now: {case[1]},"
                        f" start of matching interval: {start_of_matching_interval}"
                    )
                self.assertEqual(start_of_matching_interval, case[2])

    def test_time_within_divisors_of_24(self) -> None:
        test_cases: T.List[T.Tuple[datetime.datetime, int, int, float, bool]] = []

        test_start_hour = 6
        last_search_time_start = datetime.datetime(
            2023, 1, 1, test_start_hour, 0, 0, 0, tzinfo=self.time_zone
        )
        intervals = range(25)

        for interval in intervals:
            test_cases.append(
                (
                    last_search_time_start + datetime.timedelta(hours=interval),
                    test_start_hour,
                    interval,
                    last_search_time_start.timestamp(),
                    interval in TgtgCollectorBackend.INTERVALS,
                )
            )
        for test_case in test_cases:
            result = TgtgCollectorBackend.is_time_to_search(
                now=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=self.time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])

    def test_time_all_starts_within_interval(self) -> None:
        test_cases: T.List[T.Tuple[datetime.datetime, int, int, float, bool]] = []

        test_start_hour = 6
        last_search_time_start = datetime.datetime(2023, 1, 1, test_start_hour, 0, 0, 0)
        last_search_time_start = self.time_zone.localize(last_search_time_start)

        for interval in TgtgCollectorBackend.INTERVALS:
            now = last_search_time_start + datetime.timedelta(hours=interval)
            start_hour = test_start_hour
            interval_hour = interval
            last_search_time_start_timestamp = last_search_time_start.timestamp()

            test_cases.append(
                (
                    now,
                    start_hour,
                    interval_hour,
                    last_search_time_start_timestamp,
                    True,
                )
            )

        for test_case in test_cases:
            result = TgtgCollectorBackend.is_time_to_search(
                now=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=self.time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])

    def test_time_all_starts_outside_interval(self) -> None:
        test_cases: T.List[T.Tuple[datetime.datetime, int, int, float, bool]] = []

        test_start_hour = 6
        last_search_time_start = datetime.datetime(2023, 1, 1, test_start_hour, 0, 0, 0)
        last_search_time_start = self.time_zone.localize(last_search_time_start)

        for interval in TgtgCollectorBackend.INTERVALS:
            now = last_search_time_start + datetime.timedelta(hours=interval - 1, minutes=30)
            start_hour = test_start_hour
            interval_hour = interval
            last_search_time_start_timestamp = last_search_time_start.timestamp()

            test_cases.append(
                (
                    now,
                    start_hour,
                    interval_hour,
                    last_search_time_start_timestamp,
                    False,
                )
            )

        for test_case in test_cases:
            result = TgtgCollectorBackend.is_time_to_search(
                now=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=self.time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])
