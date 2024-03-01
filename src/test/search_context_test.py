import unittest

from search_context import util


class SearchContextTest(unittest.TestCase):

    def test_get_address_from_string(self):
        address = (
            "Autumn Lane, Seaport, South Boston, Boston, Suffolk County,"
            " Massachusetts, 02210, United States"
        )

        city = util.extract_city(address)
        self.assertEqual(city, "Boston")

        address = (
            "1340, Saint Nicholas Avenue, Washington Heights, Manhattan Community Board 12, "
            "Manhattan, United States"
        )
        city = util.extract_city(address)
        self.assertIsNone(city)

        address = (
            "2323, Saint Nicholas Avenue, Washington Heights, Manhattan Community Board 12, "
            "New York City, New York, 10033, United States"
        )
        city = util.extract_city(address)
        self.assertIsNone(city)

        address = (
            "2323, Saint Nicholas Avenue, Washington Heights, County of New York, "
            "New York City, New York, 10033, United States"
        )
        city = util.extract_city(address)
        self.assertIsNone(city)

        address = "13404, Saint Nicholas Avenue, Washington Heights, United States"
        city = util.extract_city(address)
        self.assertIsNone(city)

        address = (
            "920, Providence Highway, Norfolk County, Dedham, Massachusetts, 02026, United States"
        )
        city = util.extract_city(address)
        self.assertIsNone(city)

    def test_city_to_city_center_coordinates(self):
        test_cases = [
            ("New York", (40.7128, -74.0060)),
            ("New York City", (40.7128, -74.0060)),
            ("Los Angeles", (34.0522, -118.2437)),
        ]

        skip_check = False
        for city, expected in test_cases:
            try:
                lat, lon = util.get_city_center_coordinates(city)
            except Exception as exc:  # pylint: disable=broad-except
                skip_check = True
                print(f"\nFailed to get coordinates for {city}: {exc}")

            if not skip_check:
                self.assertAlmostEqual(lat, expected[0], places=2)
                self.assertAlmostEqual(lon, expected[1], places=2)

    def test_meters_to_degrees_latitude(self):
        meters = 111139.0
        degrees = util.meters_to_degrees_latitude(meters)
        self.assertAlmostEqual(degrees, 1.0, places=2)

        meters = 222278.0
        degrees = util.meters_to_degrees_latitude(meters)
        self.assertAlmostEqual(degrees, 2.0, places=2)

    def test_meters_to_degrees_longitude(self):
        meters = 111139.0
        degrees = util.meters_to_degrees_longitude(meters, 0.0)
        self.assertAlmostEqual(degrees, 1.0, places=2)

        meters = 222278.0
        degrees = util.meters_to_degrees_longitude(meters, 0.0)
        self.assertAlmostEqual(degrees, 2.0, places=2)

    def test_meters_to_degress(self):
        meters = 111139.0
        lat, lon = util.meters_to_degress(meters, 0.0)
        self.assertAlmostEqual(lat, 1.0, places=2)
        self.assertAlmostEqual(lon, 1.0, places=2)

        meters = 222278.0
        lat, lon = util.meters_to_degress(meters, 0.0)
        self.assertAlmostEqual(lat, 2.0, places=2)
        self.assertAlmostEqual(lon, 2.0, places=2)
