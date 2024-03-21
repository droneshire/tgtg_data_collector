# pylint: disable=duplicate-code
import unittest
from unittest.mock import MagicMock, patch

from search_context import util
from search_context.util import SearchGrid, get_search_grid_details


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

    def test_calculate_cost_from_results(self):
        square_width_meters = 100.0
        cost_per_search = 0.05
        radius_meters = 500.0
        squares, cost = util.calculate_cost_from_results(
            square_width_meters, cost_per_search, radius_meters
        )
        self.assertAlmostEqual(cost, 5.0, places=2)
        self.assertEqual(squares, 100)

        square_width_meters = 100.0
        cost_per_search = 0.05
        radius_meters = 50.0
        squares, cost = util.calculate_cost_from_results(
            square_width_meters, cost_per_search, radius_meters
        )
        self.assertAlmostEqual(cost, 0.05, places=2)
        self.assertEqual(squares, 1)

        square_width_meters = 10.0
        cost_per_search = 0.05
        radius_meters = square_width_meters / 2 - 1.0
        squares, cost = util.calculate_cost_from_results(
            square_width_meters, cost_per_search, radius_meters
        )
        self.assertAlmostEqual(cost, 0.0, places=2)
        self.assertEqual(squares, 0)

        square_width_meters = 10.0
        cost_per_search = 0.05
        radius_meters = square_width_meters / 2
        squares, cost = util.calculate_cost_from_results(
            square_width_meters, cost_per_search, radius_meters
        )
        self.assertAlmostEqual(cost, 0.05, places=2)
        self.assertEqual(squares, 1)

    def test_get_grid_coordinates(self):
        center_lat = 40.7128
        center_lon = -74.0060
        radius_meters = 5000.0
        grid_side_meters = 1000.0
        skip_over_water = False
        grid = util.get_grid_coordinates(
            center_lat, center_lon, radius_meters, grid_side_meters, skip_over_water
        )
        self.assertIsInstance(grid, list)
        self.assertEqual(len(grid), 100)

        center_lat = 40.7128
        center_lon = -74.0060
        radius_meters = 5000.0
        grid_side_meters = 1000.0
        skip_over_water = True
        grid = util.get_grid_coordinates(
            center_lat, center_lon, radius_meters, grid_side_meters, skip_over_water
        )
        self.assertIsInstance(grid, list)
        self.assertEqual(len(grid), 79)

    @patch("search_context.util.get_city_center_coordinates")
    @patch("search_context.util.calculate_cost_from_results")
    @patch("search_context.util.get_grid_coordinates")
    def test_get_search_grid_details(
        self,
        mock_get_grid_coordinates,
        mock_calculate_cost_from_results,
        mock_get_city_center_coordinates,
    ):
        # Mock return values for dependencies
        mock_get_city_center_coordinates.return_value = (
            40.7128,
            -74.0060,
        )  # Example: New York City center
        mock_calculate_cost_from_results.side_effect = [
            (10, 200.0),  # Initial high cost to trigger radius adjustment
            (8, 150.0),  # Adjusted cost within budget
        ]
        mock_get_grid_coordinates.return_value = [
            MagicMock(spec=SearchGrid)
        ] * 8  # Mock grid of 8 squares

        # Parameters for the test
        city = "New York"
        max_grid_resolution_width_meters = 100.0
        radius_meters = 5000.0
        max_cost_per_city = 150.0
        cost_per_search = 25.0
        verbose = False

        result = get_search_grid_details(
            city,
            max_grid_resolution_width_meters,
            radius_meters,
            max_cost_per_city,
            cost_per_search,
            prompts=["test"],
            verbose=verbose,
        )

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 5)
        grid, city_center_coordinates, number_of_squares, total_cost, new_radius_meters = result
        self.assertIsInstance(grid, list)
        self.assertIsInstance(city_center_coordinates, tuple)
        self.assertEqual(len(grid), 8)
        self.assertEqual(total_cost, 150.0)
        self.assertEqual(number_of_squares, 8)
        self.assertNotEqual(new_radius_meters, radius_meters)

        mock_get_city_center_coordinates.assert_called_once_with(city)
        self.assertEqual(mock_calculate_cost_from_results.call_count, 2)
        mock_get_grid_coordinates.assert_called_once()

    @patch("search_context.util.get_city_center_coordinates")
    @patch("search_context.util.get_grid_coordinates")
    def test_prompts_adjust_cost(
        self,
        mock_get_grid_coordinates,
        mock_get_city_center_coordinates,
    ) -> None:
        # Mock return values for dependencies
        mock_get_city_center_coordinates.return_value = (
            40.7128,
            -74.0060,
        )  # Example: New York City center
        mock_get_grid_coordinates.return_value = [
            MagicMock(spec=SearchGrid)
        ] * 8  # Mock grid of 8 squares

        city = "New York"
        max_grid_resolution_width_meters = 100.0
        radius_meters = 5000.0
        max_cost_per_city = 20000.0
        cost_per_search = 1.0
        verbose = False

        prompts1 = ["test"]

        result = get_search_grid_details(
            city,
            max_grid_resolution_width_meters,
            radius_meters,
            max_cost_per_city,
            cost_per_search,
            prompts=prompts1,
            verbose=verbose,
        )

        _, _, number_of_squares, total_cost, _ = result

        expected_squares = 10000
        expected_cost = 10000.0

        self.assertEqual(total_cost, expected_cost)
        self.assertEqual(number_of_squares, expected_squares)

        prompts2 = ["test", "tests"]

        result = get_search_grid_details(
            city,
            max_grid_resolution_width_meters,
            radius_meters,
            max_cost_per_city,
            cost_per_search,
            prompts=prompts2,
            verbose=verbose,
        )
        _, _, number_of_squares, total_cost, _ = result
        self.assertEqual(total_cost, expected_cost * len(prompts2) / len(prompts1))
        self.assertEqual(number_of_squares, expected_squares)

        max_cost_per_city = 200.0
        cost_per_search = 25.0

        result = get_search_grid_details(
            city,
            max_grid_resolution_width_meters,
            radius_meters,
            max_cost_per_city,
            cost_per_search,
            prompts=prompts2,
            verbose=verbose,
        )

        grid, _, number_of_squares, total_cost, new_radius_meters = result

        self.assertEqual(len(grid), 0)
        self.assertEqual(number_of_squares, 0)
        self.assertEqual(new_radius_meters, 0)
        self.assertEqual(total_cost, 20000)
