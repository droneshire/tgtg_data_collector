import unittest

from demographics import util


class DemographicsTest(unittest.TestCase):

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
        city = "New York"
        lat, lon = util.get_city_center_coordinates(city)
        self.assertAlmostEqual(lat, 40.7128, places=2)
        self.assertAlmostEqual(lon, -74.0060, places=2)

        city = "New York City"
        lat, lon = util.get_city_center_coordinates(city)
        self.assertAlmostEqual(lat, 40.7128, places=2)
        self.assertAlmostEqual(lon, -74.0060, places=2)

        city = "Los Angeles"
        lat, lon = util.get_city_center_coordinates(city)
        self.assertAlmostEqual(lat, 34.0522, places=2)
        self.assertAlmostEqual(lon, -118.2437, places=2)

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
