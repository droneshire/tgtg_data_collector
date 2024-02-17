import math
import typing as T

import plotly.express as px


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


def get_viewport(
    center_lat: float, center_lon: float, radius_meters: float
) -> T.Dict[str, T.Dict[str, float]]:
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
    center_lat: float, center_lon: float, radius_meters: float, grid_side_meters: float
) -> T.List[T.Tuple[float, float]]:
    """
    Given a center (lat, lon), radius in meters, and grid square area in meters,
    calculate a grid of coordinates.
    """

    grid_lat_adjustment, grid_lon_adjustment = meters_to_degress(grid_side_meters, center_lat)

    lat_adjustment, lon_adjustment = meters_to_degress(radius_meters, center_lat)

    lon_steps = int(lon_adjustment / grid_lon_adjustment) * 2
    lat_steps = int(lat_adjustment / grid_lat_adjustment) * 2

    lat_step_size = grid_lat_adjustment
    lon_step_size = grid_lon_adjustment

    grid = []

    print(f"lat_steps: {lat_steps}, lon_steps: {lon_steps}")
    # Subtract 1 from lat_steps and lon_steps to avoid going over the radius
    # since we are adding half the step size to the center
    for i in range(lat_steps - 1):
        for j in range(lon_steps - 1):
            lat = center_lat - lat_adjustment + (lat_step_size / 2) + i * lat_step_size
            lon = center_lon - lon_adjustment + (lon_step_size / 2) + j * lon_step_size
            grid.append((lat, lon))

    return grid
