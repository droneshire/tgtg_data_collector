import math
import typing as T

from geopy.geocoders import Nominatim
from global_land_mask import globe

from util import log

METERS_PER_MILE = 1609.34
METERS_PER_KILOMETER = 1000.0

DEFAULT_PROMPTS = [
    "All restaurants",  # This first one in the list is the default used for optimization purposes
    "All bakeries",
    "All grocery stores",
    "All coffee shops",
]


class Coordinates(T.TypedDict):
    latitude: float
    longitude: float


class Viewport(T.TypedDict):
    low: Coordinates
    high: Coordinates


class SearchGrid(T.TypedDict):
    center: Coordinates
    viewport: Viewport
    width_meters: float


def extract_city(address: str) -> T.Optional[str]:
    """
    Given an address, extract the city from it.
    The address is expected to be a comma-separated string.
    Example:
        1340, Saint Nicholas Avenue, Washington Heights, Manhattan Community Board 12,
        Manhattan, City of New York, New York County, New York, 10033, United States
    """
    parts = address.split(",")
    city = None
    zip_code_index: T.Optional[int] = None

    print(address)
    for i, part in enumerate(parts):
        part = part.strip()
        if "City of " in part:
            city = part[len("City of ") :].strip()
            break
        if part.isnumeric() and len(part) == 5 and i > 1:
            zip_code_index = i

    if not city and zip_code_index:
        # If none of the recognizable keywords are found,
        # assume city is 3 parts before the zip code
        city = parts[zip_code_index - 3].strip() if zip_code_index - 3 >= 0 else None

        if city is None:
            return None

        if "County" in city:
            return None

        if any(char.isdigit() for char in city):
            return None

    return city


def get_city_center_coordinates(city_name: str) -> T.Optional[T.Tuple[float, float]]:
    # Initialize the Nominatim geocoder
    geolocator = Nominatim(user_agent="tgtg")

    # Use the geocoder to geocode the city name
    location = geolocator.geocode(city_name)

    if not location:
        return None

    return (location.latitude, location.longitude)


def meters_to_degrees_latitude(meters: float) -> float:
    """Convert miles to degrees latitude."""
    return meters / 111139.0


def meters_to_degrees_longitude(meters: float, latitude: float) -> float:
    """Convert miles to degrees longitude at a given latitude."""
    # Earth's radius in meters
    earth_radius = 6378137.0
    radians_latitude = math.radians(latitude)
    # Calculate the radius of a circle at the given latitude
    meters_per_degree = math.cos(radians_latitude) * math.pi * earth_radius / 180.0
    return meters / meters_per_degree


def meters_to_degress(meters: float, center_lat: float) -> T.Tuple[float, float]:
    """
    Given a distance in meters and a center latitude, calculate the number of degrees
    in latitude and longitude that correspond to the radius.
    """
    lat_adjustment = meters_to_degrees_latitude(meters)
    lon_adjustment = meters_to_degrees_longitude(meters, center_lat)
    return lat_adjustment, lon_adjustment


def get_viewport(center_lat: float, center_lon: float, radius_meters: float) -> Viewport:
    """
    Given a center (lat, lon) and radius in meters, calculate a viewport.
    Where the low is the bottom left corner and the high is the top right corner.
    """
    lat_adjustment, lon_adjustment = meters_to_degress(radius_meters, center_lat)

    low_lat = max(-90, center_lat - lat_adjustment)
    high_lat = min(90, center_lat + lat_adjustment)
    low_lon = center_lon - lon_adjustment
    high_lon = center_lon + lon_adjustment

    # Handle longitude wraparound
    if low_lon < -180:
        low_lon += 360
    if high_lon > 180:
        high_lon -= 360

    return {
        "low": {"latitude": low_lat, "longitude": low_lon},
        "high": {"latitude": high_lat, "longitude": high_lon},
    }


def get_grid_coordinates(
    center_lat: float,
    center_lon: float,
    radius_meters: float,
    grid_side_meters: float,
    skip_over_water: bool,
    verbose: bool = False,
) -> T.List[SearchGrid]:
    """
    Given a center (lat, lon), radius in meters, and grid side area in meters,
    calculate a grid of coordinates.
    """

    grid_lat_adjustment, grid_lon_adjustment = meters_to_degress(grid_side_meters, center_lat)

    lat_adjustment, lon_adjustment = meters_to_degress(radius_meters, center_lat)

    lon_steps = int(lon_adjustment / grid_lon_adjustment) * 2
    lat_steps = int(lat_adjustment / grid_lat_adjustment) * 2

    lat_step_size = grid_lat_adjustment
    lon_step_size = grid_lon_adjustment

    grid = []

    for i in range(lat_steps):
        for j in range(lon_steps):
            lat = center_lat - lat_adjustment + (lat_step_size / 2) + i * lat_step_size
            lon = center_lon - lon_adjustment + (lon_step_size / 2) + j * lon_step_size

            viewport: Viewport = get_viewport(lat, lon, grid_side_meters)
            search_grid = SearchGrid(
                center={"latitude": lat, "longitude": lon},
                viewport=viewport,
                width_meters=grid_side_meters,
            )

            if not skip_over_water:
                grid.append(search_grid)
            elif globe.is_land(lat, lon):
                grid.append(search_grid)
            elif verbose:
                log.print_warn(f"Skipping water grid at {lat}, {lon}")

    return grid


def calculate_cost_from_results(
    search_block_width: float,
    cost_per_square: float,
    radius_meters: float,
    verbose: bool = False,
) -> T.Tuple[int, float]:
    search_block_area = (
        search_block_width * search_block_width
    )  # Area of one square in square meters

    area_width = radius_meters * 2

    total_area_meters = area_width * area_width

    # Calculate how many search_block_width meter squares fit into the area
    number_of_squares = int(total_area_meters / search_block_area)

    total_cost = number_of_squares * cost_per_square

    if verbose:
        print(f"Total searches: {number_of_squares:.0f}")
        print(f"Total cost: ${total_cost:.2f}")
        print(f"Searched area: {search_block_area:.2f} m^2")
        print(f"Total area: {total_area_meters:.2f} m^2")

    return int(number_of_squares), total_cost


def get_search_grid_details(
    city: str,
    max_grid_resolution_width_meters: float,
    radius_meters: float,
    max_cost_per_city: float,
    cost_per_search: float,
    prompts: T.Optional[T.List[str]] = None,
    verbose: bool = False,
) -> T.Tuple[T.List[SearchGrid], T.Tuple[float, float], int, float, float]:
    city_center_coordinates = get_city_center_coordinates(city)
    assert city_center_coordinates, f"Location not found for {city}"

    if verbose:
        log.print_bright(f"City center: {city_center_coordinates}")

    center_lat, center_lon = city_center_coordinates

    number_of_squares = 0
    total_cost = max_cost_per_city * 10.0
    grid = []

    # Now optimize for cost by reducing the radius until it is within budget
    log.print_normal(f"Optimizing {city} for cost...")
    new_radius_meters = radius_meters
    step_size_meters = METERS_PER_KILOMETER

    if not prompts:
        prompts = DEFAULT_PROMPTS

    cost_per_search = cost_per_search * len(prompts)
    while True:
        number_of_squares, total_cost = calculate_cost_from_results(
            max_grid_resolution_width_meters, cost_per_search, new_radius_meters, verbose=verbose
        )
        if 0 < total_cost <= max_cost_per_city:
            break

        if total_cost <= 0:
            step_size_meters /= 2
            new_radius_meters += step_size_meters
            continue

        if new_radius_meters <= step_size_meters:
            log.print_fail("Radius is too small for the cost")
            return ([], city_center_coordinates, 0, total_cost, 0)

        new_radius_meters -= step_size_meters

    grid = get_grid_coordinates(
        center_lat=center_lat,
        center_lon=center_lon,
        radius_meters=new_radius_meters,
        grid_side_meters=max_grid_resolution_width_meters,
        skip_over_water=True,
        verbose=verbose,
    )

    return (grid, city_center_coordinates, number_of_squares, total_cost, new_radius_meters)
