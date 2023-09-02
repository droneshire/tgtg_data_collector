import datetime
import os
import tempfile
import typing as T
import unittest

import pytz

from backend import TgtgCollectorBackend


class TgtgTest(unittest.TestCase):
    test_dir: str = os.path.join(os.path.dirname(__file__), "test_data")
    test_email: str = "test@gmail.com"
    verbose: bool = True

    def setUp(self) -> None:
        # pylint: disable=consider-using-with
        self.temp_credentials_file = tempfile.NamedTemporaryFile(delete=False)

        with open(
            os.path.join(self.test_dir, "credentials.json"), "w", encoding="utf-8"
        ) as outfile:
            outfile.write("{}")

    def tearDown(self) -> None:
        if self.temp_credentials_file and os.path.isfile(self.temp_credentials_file.name):
            os.remove(self.temp_credentials_file.name)

    def test_is_within_interval(self) -> None:
        time_zone = pytz.timezone("America/Los_Angeles")
        test_cases: T.List[T.Tuple[datetime.datetime, int, int, float, bool]] = []

        intervals = [1, 2, 3, 4, 6, 8, 12, 24]
        # last search times is a float time that would be seconds from epoch (time.time())
        last_search_time_start = datetime.datetime(2020, 1, 1, 0, 0, 0).timestamp()
        last_search_times = [last_search_time_start + i * 60 * 60 for i in range(0, 24 * 2)]

        for hour in range(0, 24):
            for interval_hour in intervals:
                for start_hour in range(0, 24):
                    for last_search_time in last_search_times:
                        test_cases.append(
                            (
                                datetime.datetime(2020, 1, 2, hour, 0, 0, tzinfo=time_zone),
                                start_hour,
                                interval_hour,
                                last_search_time,
                                hour - last_search_time >= interval_hour,
                            )
                        )

        for test_case in test_cases:
            result = TgtgCollectorBackend.is_within_interval(
                now=test_case[0],
                start_hour=test_case[1],
                interval_hour=test_case[2],
                last_search_time=test_case[3],
                time_zone=time_zone,
                verbose=self.verbose,
            )
            self.assertEqual(result, test_case[4])
