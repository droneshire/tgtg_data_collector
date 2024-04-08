"""
Google Places API wrapper

https://developers.google.com/maps/documentation/places/web-service/overview
https://developers.google.com/maps/documentation/places/web-service/text-search
https://developers.google.com/maps/documentation/places/web-service/search
"""

import copy
import json
import os
import typing as T

import requests

from search_context.util import Coordinates, get_viewport
from util import log

ADVANCED_FIELDS = [
    "places.formattedAddress",
    "places.displayName",
    "places.nationalPhoneNumber",
    "places.location",
    "places.rating",
    "places.googleMapsUri",
    "places.websiteUri",
    "places.regularOpeningHours",
    "places.businessStatus",
    "places.priceLevel",
    "places.userRatingCount",
    "places.takeout",
    "places.delivery",
    "places.dineIn",
    "places.servesBreakfast",
    "places.primaryTypeDisplayName",
    "places.primaryType",
    "places.editorialSummary",
    "places.outdoorSeating",
    "places.servesCoffee",
    "places.paymentOptions",
    "places.accessibilityOptions",
]

TYPES = [
    "bakery",
    "sandwich_shop",
    "coffee_shop",
    "cafe",
    "fast_food_restaurant",
    "store",
    "restaurant",
    "food",
    "point_of_interest",
    "establishment",
]


def call_api(
    url: str,
    headers: T.Optional[T.Dict[str, T.Any]] = None,
    params: T.Optional[T.Dict[str, T.Any]] = None,
    json_data: T.Optional[T.Dict[str, T.Any]] = None,
    timeout: float = 10.0,
) -> T.Dict[T.Any, T.Any]:
    headers = headers or {}
    json_data = json_data or {}
    params = params or {}

    try:
        response = requests.post(
            url, headers=headers, params=params, json=json_data, timeout=timeout
        ).json()
        if not isinstance(response, dict):
            print(f"Failed results from {url}")
            print(response)
            return {}

        return response
    except Exception as exception:  # pylint: disable=broad-except
        print(f"Failed results for {url}")
        print(exception)
        raise exception


class GoogleMapsAPI:
    def __init__(self, api_key: str, verbose: bool = False) -> None:
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api"
        self.verbose = verbose

    def find_place_from_location(self, place: str, location: Coordinates) -> T.Dict[T.Any, T.Any]:
        location_string = f"{location['latitude']},{location['longitude']}"
        params = {
            "input": place,
            "inputtype": "textquery",
            "fields": "name,place_id",
            "locationbias": f"point:{location_string}",
            "key": self.api_key,
        }

        url = os.path.join(self.base_url, "place", "findplacefromtext", "json")

        if self.verbose:
            print(f"Searching for {place} at {location_string}")

        return call_api(url, params=params)

    def nearby_search(
        self,
        location: Coordinates,
        radius_meters: int,
        location_type: T.List[str],
        keyword: str,
    ) -> T.Dict[T.Any, T.Any]:
        location_string = f"{location['latitude']},{location['longitude']}"
        assert location_type in TYPES, f"Invalid location type {location_type}"

        params = {
            "location": location_string,
            "radius": radius_meters,
            "type": location_type,
            "keyword": keyword,
            "key": self.api_key,
        }

        url = os.path.join(self.base_url, "place", "nearbysearch", "json")

        if self.verbose:
            print(f"Searching for {keyword} at {location_string}")

        return call_api(url, params=params)

    def details_from_place_id(
        self, place_id: str, fields: T.Optional[T.List[str]] = None
    ) -> T.Dict[T.Any, T.Any]:
        fields = fields or [field.replace("places.", "") for field in ADVANCED_FIELDS]

        params = {
            "place_id": place_id,
            "fields": ",".join(fields),
            "key": self.api_key,
        }

        url = os.path.join(self.base_url, "place", "details", "json")

        if self.verbose:
            print(f"Getting details for {place_id}")

        return call_api(url, params=params)


class GooglePlacesAPI:
    HEADERS = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "",
        "X-Goog-FieldMask": "",
    }
    DEFAULT_FIELDS = "places.formattedAddress,places.displayName"
    MIN_VIEWPOINT_WIDTH_METERS = 100.0
    MAX_VIEWPOINT_WIDTH_METERS = 700.0
    VIEWPOINT_WIDTH_STEP_METERS = 50.0

    def __init__(self, api_key: str, verbose: bool = False) -> None:
        self.api_key = api_key
        self.HEADERS["X-Goog-Api-Key"] = api_key
        self.base_url = "https://places.googleapis.com/v1"
        self.verbose = verbose

    def text_search(
        self,
        query: str,
        fields: T.Optional[T.List[str]] = None,
        data: T.Optional[T.Dict[str, T.Any]] = None,
    ) -> T.Dict[T.Any, T.Any]:
        json_data = {
            "textQuery": query,
        }

        if data:
            json_data.update(data)

        if self.verbose:
            log.print_normal(f"Searching for {query}")
            log.print_normal(f"Data: {json.dumps(json_data, indent=2)}")

        headers = copy.deepcopy(self.HEADERS)

        headers["X-Goog-FieldMask"] = ",".join(fields) if fields else self.DEFAULT_FIELDS

        url = os.path.join(self.base_url, "places:searchText")

        return call_api(url, headers, json_data)

    def find_nearby_places_from_place_id(
        self, place_id: str, fields: T.Optional[T.List[str]] = None
    ) -> T.Dict[T.Any, T.Any]:
        if fields is None:
            fields = ADVANCED_FIELDS

        headers = copy.deepcopy(self.HEADERS)

        headers["X-Goog-FieldMask"] = ",".join(fields) if fields else self.DEFAULT_FIELDS

        url = os.path.join(self.base_url, "places/{place_id}")

        if self.verbose:
            log.print_normal(f"Searching for nearby places from {place_id}")

        return call_api(url, headers=headers)

    def search_location_radius(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float,
        query: str,
        fields: T.Optional[T.List[str]] = None,
        included_type: T.Optional[str] = None,
    ) -> T.Dict[T.Any, T.Any]:
        radius_meters = min(radius_miles * 1609.34, 50000.0)

        if self.verbose:
            log.print_normal(
                f"Searching for {query} within {radius_miles} miles of {latitude}, {longitude}"
            )
        json_data: T.Dict[str, T.Any] = {
            "locationBias": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            },
        }

        if included_type is not None:
            json_data["includedType"] = included_type

        if self.verbose:
            log.print_normal(f"Data: {json.dumps(json_data, indent=2)}")
        return self.text_search(query=query, fields=fields, data=json_data)

    def find_maximum_viewpoint_width(
        self, latitude: float, longitude: float, query: str, fields: T.Optional[T.List[str]] = None
    ) -> float:
        viewpoint_width_meters = self.MIN_VIEWPOINT_WIDTH_METERS

        while viewpoint_width_meters < self.MAX_VIEWPOINT_WIDTH_METERS:
            if self.verbose:
                log.print_normal(
                    f"Searching for {query} with viewpoint width {viewpoint_width_meters} meters"
                )
            rect_viewpoint = get_viewport(latitude, longitude, viewpoint_width_meters)
            data = {"locationRestriction": {"rectangle": rect_viewpoint}}
            results = self.text_search(query, fields, data)
            if results and results.get("places") and len(results["places"]) >= 20:
                if self.verbose:
                    log.print_ok(
                        f"Found {len(results['places'])} results "
                        f"with viewpoint width {viewpoint_width_meters} meters"
                    )
                return viewpoint_width_meters - self.VIEWPOINT_WIDTH_STEP_METERS
            viewpoint_width_meters += self.VIEWPOINT_WIDTH_STEP_METERS

        return viewpoint_width_meters
