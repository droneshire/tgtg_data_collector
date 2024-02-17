"""
Google Places API wrapper

https://developers.google.com/maps/documentation/places/web-service/overview
https://developers.google.com/maps/documentation/places/web-service/text-search
"""

import copy
import json
import os
import typing as T

import requests

from demographics.util import get_viewport
from util import log


class GooglePlacesAPI:
    HEADERS = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "",
        "X-Goog-FieldMask": "",
    }
    DEFAULT_FIELDS = "places.formattedAddress,places.displayName"
    MIN_VIEWPOINT_WIDTH_METERS = 100.0
    MAX_VIEWPOINT_WIDTH_METERS = 50000.0
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
        try:
            response = requests.post(url, headers=headers, json=json_data, timeout=10.0).json()
            if not isinstance(response, dict):
                log.print_fail(f"Could not search for {query}")
                log.print_warn(response)
                return {}

            return response
        except Exception as exception:  # pylint: disable=broad-except
            log.print_fail(f"Could not search for {query}")
            log.print_warn(exception)
            return {}

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
