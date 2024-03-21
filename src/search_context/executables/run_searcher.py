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
    DEFAULT_PROMPTS,
    METERS_PER_MILE,
    SearchGrid,
    get_city_center_coordinates,
    get_search_grid_details,
)
from util import email, file_util, fmt_util, log


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
    default_results_csv = os.path.join(results_dir, f"search_context_{datetime_str}.csv")
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
    parser.add_argument(
        "--census_fields",
        type=str,
        default="B01001_001E,B19013_001E",
        help="Census fields to search for",
    )
    parser.add_argument("--census_year", type=int, default=2022, help="Census year to log")
    parser.add_argument("--city", type=str, required=True, help="City to search in")
    parser.add_argument("--max_cost", type=float, default=1.0, help="Maximum cost")
    parser.add_argument("--cost_per_search", type=float, default=0.04, help="Cost per search")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--dry_run", action="store_true", help="Dry run")
    parser.add_argument("--and_upload", action="store_true", help="Upload results to Firebase")
    return parser.parse_args()


def get_search_grid(
    city: str,
    radius_miles: float,
    max_cost: float,
    cost_per_search: float,
    google_api_key: str,
    verbose: bool = False,
) -> T.List[SearchGrid]:
    radius_meters = radius_miles * METERS_PER_MILE

    city_center_coordinates = get_city_center_coordinates(city)
    assert city_center_coordinates, f"Location not found for {city}"

    center_lat, center_lon = city_center_coordinates

    # Get the maximum width of the viewport for our search to have good resolution
    # since places api limits the search results to 20 max regardless of the radius
    google_places = GooglePlacesAPI(google_api_key, verbose=verbose)
    log.print_bright("Finding maximum viewpoint width...")
    max_grid_resolution_width_meters = google_places.find_maximum_viewpoint_width(
        center_lat, center_lon, DEFAULT_PROMPTS[0]
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

    data = [
        {"Parameter": "City", "Value": city},
        {"Parameter": "City center", "Value": str(city_center_coordinates)},
        {"Parameter": "Final radius", "Value": f"{new_radius_meters / METERS_PER_MILE:.2f} miles"},
        {"Parameter": "Grid resolution", "Value": f"{max_grid_resolution_width_meters} meters"},
        {"Parameter": "Grid size max", "Value": str(num_grid_squares)},
        {"Parameter": "Grid size actual", "Value": str(len(grid))},
        {"Parameter": "Total cost", "Value": f"${total_cost:.2f}"},
    ]

    fmt_util.print_simple_rich_table(
        "Search Grid Parameters",
        data,
    )

    return grid if grid else []


def main() -> None:
    dotenv.load_dotenv()

    args = parse_args()

    sender_email = email.Email(
        {
            "address": os.environ["SENDER_EMAIL_ADDRESS"],
            "password": os.environ["SENDER_EMAIL_PASSWORD"],
            "quiet": args.dry_run,
        }
    )

    searcher = Searcher(
        google_api_key=args.google_api_key,
        us_census_api_key=args.census_api_key,
        results_csv=args.results_csv,
        email_obj=sender_email,
        credentials_file=args.credentials_file,
        storage_bucket=args.storage_bucket,
        max_search_calls=args.max_search_calls,
        auto_init=False,
        clamp_at_max=args.clamp_at_max,
        verbose=args.verbose,
    )

    grid = get_search_grid(
        args.city, args.radius_miles, args.max_cost, args.cost_per_search, args.google_api_key
    )

    searcher.run_search(
        user=args.email,
        search_name=f"{args.city} Search",
        search_grid=grid,
        census_year=args.census_year,
        time_zone=pytz.timezone("America/Los_Angeles"),
        census_fields=args.census_fields.split(","),
        and_upload=args.and_upload,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
