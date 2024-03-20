import json
import os
import typing as T

import censusgeocode
import requests
from census import Census

from constants import DEFAULT_CENSUS_FIELDS_JSON_FILE
from util import dict_util, log

ListorStr = T.Union[str, T.List[str]]


class USCensusAPI:
    def __init__(
        self,
        api_key: str,
        cache_json_file: str = DEFAULT_CENSUS_FIELDS_JSON_FILE,
        warm_cache: bool = True,
        verbose: bool = False,
    ):
        self.census = Census(api_key)
        self.api_key = api_key
        self.verbose = verbose
        self.cache_json_file = cache_json_file
        self.census_fields_cache: T.Dict[str, T.Dict[str, T.Any]] = {}

        if warm_cache:
            self.warm_cache()

    def warm_cache(self):
        if not self.cache_json_file or not os.path.exists(self.cache_json_file):
            log.print_warn("No cache file specified")
            try:
                self.census_fields_cache = self.census.acs5.fields()
            except requests.exceptions.JSONDecodeError as exception:
                log.print_warn(f"Could not load census fields: {exception}")
                return

            with open(self.cache_json_file, "w", encoding="utf-8") as outfile:
                json.dump(self.census_fields_cache, outfile, indent=4)

            return

        with open(self.cache_json_file, "r", encoding="utf-8") as infile:
            try:
                self.census_fields_cache = json.load(infile)
            except json.JSONDecodeError:
                log.print_warn(f"Could not load cache file: {self.cache_json_file}")
                self.census_fields_cache = {}

    def is_usable_address(self, address: str) -> bool:
        try:
            result = censusgeocode.onelineaddress(address)
            state = self._item("STATE", result)
            county = self._item("COUNTY", result)
            tract = self._item("TRACT", result)
            block_group = self._item("BLKGRP", result)
            return bool(state and county and tract and block_group)
        except Exception:  # pylint: disable=broad-except
            return False

    def get_census_data_from_lat_long(
        self,
        fields: ListorStr,
        lat: float,
        long: float,
    ) -> T.Optional[T.Dict[str, T.Any]]:
        try:
            result = censusgeocode.coordinates(x=lat, y=long)
        except Exception:  # pylint: disable=broad-except
            log.print_warn(f"Could not find lat/long: {lat}, {long}")
            return None

        if result is None:
            log.print_warn(f"Could not find lat/long: {lat}, {long}")
            return None

        log.print_bright(f"Found lat/long: {lat}, {long}")
        return self._get_census_data(f"{lat}, {long}", result, fields)

    def get_census_data_from_address(
        self, fields: ListorStr, address: str
    ) -> T.Optional[T.Dict[str, T.Any]]:
        try:
            result = censusgeocode.onelineaddress(address)
        except Exception:  # pylint: disable=broad-except
            log.print_warn(f"Could not find address: {address}")
            return None

        if result is None:
            log.print_warn(f"Could not find address: {address}")
            return None

        log.print_bright(f"Found address: {address}")
        return self._get_census_data(address, result, fields)

    def _get_census_data(
        self, search_location: str, geocode_results: T.Dict[str, T.Any], fields: ListorStr
    ) -> T.Dict[str, T.Any]:
        state = self._item("STATE", geocode_results)
        county = self._item("COUNTY", geocode_results)
        tract = self._item("TRACT", geocode_results)
        block_group = self._item("BLKGRP", geocode_results)

        if not state or not county or not tract or not block_group:
            log.print_warn(f"Could not find geo info about for {search_location}")
            return {}

        if self.verbose:
            log.print_normal(f"State: {state}")
            log.print_normal(f"County: {county}")
            log.print_normal(f"Tract: {tract}")
            log.print_normal(f"Block Group: {block_group}")

        if not isinstance(fields, list):
            fields = [fields]

        try:
            result = self.census.acs5.state_county_blockgroup(
                fields, state, county, tract=tract, blockgroup=block_group
            )
        except Exception as exception:  # pylint: disable=broad-except
            log.print_warn(f"Could not find census data for {search_location}")
            log.print_warn(exception)
            return {}

        if not result:
            log.print_warn(f"Could not find census data for {search_location}")
            return {}

        data = {}
        for field in fields:
            if field not in result[0]:
                log.print_warn(f"Could not find {field} in census data for {search_location}")
                continue

            data[field] = result[0][field]

            if self.verbose:
                log.print_bold(f"Found {self.get_description_for_field(field)}: {data[field]}")

        return data

    def get_description_for_field(self, field: str):
        if field not in self.census_fields_cache:
            return field

        return_string = self.census_fields_cache[field].get("concept", "")
        return_string += ": "
        return_string += self.census_fields_cache[field].get("label", "").replace("!!", " ")
        return return_string

    @staticmethod
    def _item(val, data):
        return dict_util.find_in_nested_dict(data, val)
