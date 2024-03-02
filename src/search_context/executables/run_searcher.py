"""
Executable that runs the searcher on a grid search.
"""

import argparse
import os
import typing as T
from datetime import datetime

import dotenv
import pytz

from constants import PROJECT_NAME
from search_context.google_places import GooglePlacesAPI
from search_context.searcher import MAX_SEARCH_CALLS, Searcher
from search_context.util import (
    METERS_PER_MILE,
    SearchGrid,
    get_city_center_coordinates,
    get_search_grid_details,
)
from util import file_util, log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the searcher on a grid search")

    firebase_credentials_file = os.environ["FIREBASE_CREDENTIALS_FILE"]
    firebase_storage_path = os.environ["FIREBASE_STORAGE_PATH"]
    census_api_key = os.environ["CENSUS_API_KEY"]
    google_places_api_key = os.environ["GOOGLE_MAPS_PLACES_API_KEY"]
    test_email = os.environ["TEST_EMAIL_ADDRESS"]

    parser.add_argument(
        "--census_api_key", type=str, default=census_api_key, help="US Census API key"
    )
    parser.add_argument(
        "--google-api_key", type=str, default=google_places_api_key, help="Google Places API key"
    )
    datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = log.get_logging_dir(PROJECT_NAME)
    results_dir = os.path.join(log_dir, "search_context_results")
    file_util.make_sure_path_exists(results_dir)
    default_results_csv = os.path.join(results_dir, f"search_results_{datetime_str}.csv")
    parser.add_argument(
        "--results_csv",
        type=str,
        default=default_results_csv,
        help="CSV file to write results to",
    )
    parser.add_argument(
        "--email", type=str, default=test_email, help="Email address to send notifications to"
    )
    parser.add_argument(
        "--credentials_file",
        type=str,
        default=firebase_credentials_file,
        help="Firebase credentials file",
    )
    parser.add_argument(
        "--storage_bucket",
        type=str,
        default=firebase_storage_path,
        help="Firebase storage bucket",
    )
    parser.add_argument(
        "--max_search_calls",
        type=int,
        default=MAX_SEARCH_CALLS,
        help="Maximum number of search calls",
    )
    parser.add_argument(
        "--clamp_at_max",
        action="store_true",
        default=True,
        help="Clamp the number of search calls at the maximum",
    )
    parser.add_argument(
        "--radius_miles", type=float, default=20.0, help="Radius in miles to search"
    )
    parser.add_argument("--city", type=str, required=True, help="City to search in")
    parser.add_argument("--max_cost", type=float, default=10.0, help="Maximum cost")
    parser.add_argument("--cost_per_search", type=float, default=0.04, help="Cost per search")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--dry_run", action="store_true", help="Dry run")
    return parser.parse_args()


def get_search_grid(
    city: str, radius_miles: float, max_cost: float, cost_per_search: float, google_api_key: str
) -> T.List[SearchGrid]:
    radius_meters = radius_miles * METERS_PER_MILE

    city_center_coordinates = get_city_center_coordinates(city)
    assert city_center_coordinates, f"Location not found for {city}"

    center_lat, center_lon = city_center_coordinates

    # Get the maximum width of the viewport for our search to have good resolution
    # since places api limits the search results to 20 max regardless of the radius
    google_places = GooglePlacesAPI(google_api_key, verbose=True)
    log.print_bright("Finding maximum viewpoint width...")
    max_grid_resolution_width_meters = google_places.find_maximum_viewpoint_width(
        center_lat, center_lon, "All restaurants"
    )

    log.print_ok_blue(f"Maximum viewpoint width: {max_grid_resolution_width_meters} meters")

    # pylint: disable=duplicate-code
    grid, city_center_coordinates, num_grid_squares, total_cost, new_radius_meters = (
        get_search_grid_details(
            city,
            max_grid_resolution_width_meters,
            radius_meters,
            max_cost,
            cost_per_search,
            verbose=False,
        )
    )
    # pylint: enable=duplicate-code

    log.print_ok_blue(f"Final radius: {new_radius_meters / METERS_PER_MILE:.2f} miles")
    log.print_ok_blue(f"Number of grid squares: {num_grid_squares}")
    log.print_ok_blue(f"Grid size: {len(grid)}")
    log.print_ok_blue(f"Total cost: ${total_cost:.2f}")
    log.print_ok_blue(f"City center: {city_center_coordinates}")
    log.print_ok_blue(f"Grid resolution: {max_grid_resolution_width_meters} meters")

    return grid if grid else []


def main() -> None:
    dotenv.load_dotenv()

    args = parse_args()

    searcher = Searcher(
        google_api_key=args.google_api_key,
        us_census_api_key=args.census_api_key,
        results_csv=args.results_csv,
        email=args.email,
        credentials_file=args.credentials_file,
        storage_bucket=args.storage_bucket,
        max_search_calls=args.max_search_calls,
        clamp_at_max=args.clamp_at_max,
        verbose=args.verbose,
    )

    grid = get_search_grid(
        args.city, args.radius_miles, args.max_cost, args.cost_per_search, args.google_api_key
    )

    searcher.run_search(
        search_name=f"{args.city} Search",
        search_grid=grid,
        time_zone=pytz.timezone("America/Los_Angeles"),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
