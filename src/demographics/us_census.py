import json
import typing as T

import censusgeocode
from census import Census

from constants import DEFAULT_CENSUS_FIELDS_JSON_FILE
from util import dict_util, log


class USCensusAPI:
    def __init__(
        self,
        api_key: str,
        cache_json_file: str = DEFAULT_CENSUS_FIELDS_JSON_FILE,
        warm_cache: bool = True,
    ):
        self.census = Census(api_key)
        self.cache_json_file = cache_json_file
        self.census_fields_cache: T.Dict[str, T.Dict[str, T.Any]] = {}

        if warm_cache:
            self.warm_cache()

    def warm_cache(self):
        if not self.cache_json_file:
            log.print_warn("No cache file specified")
            self.census_fields_cache = self.census.acs5.fields()

            with open(self.cache_json_file, "w", encoding="utf-8") as outfile:
                json.dump(self.census_fields_cache, outfile, indent=4)

            return

        with open(self.cache_json_file, "r", encoding="utf-8") as infile:
            try:
                self.census_fields_cache = json.load(infile)
            except json.JSONDecodeError:
                log.print_warn(f"Could not load cache file: {self.cache_json_file}")
                self.census_fields_cache = {}

    def get_census_data(self, field: str, address: str):
        try:
            result = censusgeocode.onelineaddress(address)
        except Exception:  # pylint: disable=broad-except
            log.print_warn(f"Could not find address: {address}")
            return None

        if result is None:
            log.print_warn(f"Could not find address: {address}")
            return None

        log.print_bright(f"Found address: {address}")

        state = self._item("STATE", result)
        county = self._item("COUNTY", result)
        tract = self._item("TRACT", result)
        block_group = self._item("BLKGRP", result)

        if not state or not county or not tract or not block_group:
            log.print_warn(f"Could not find geo info about {field} for address: {address}")
            return None

        log.print_normal(f"State: {state}")
        log.print_normal(f"County: {county}")
        log.print_normal(f"Tract: {tract}")
        log.print_normal(f"Block Group: {block_group}")

        try:
            result = self.census.acs5.state_county_blockgroup(
                field, state, county, tract=tract, blockgroup=block_group
            )
        except Exception as exception:  # pylint: disable=broad-except
            log.print_warn(f"Could not find census data for address: {address}")
            log.print_warn(exception)
            return None

        if not result:
            log.print_warn(f"Could not find census data for address: {address}")
            return None

        data = result[0][field]

        log.print_bold(f"Found {self.get_description_for_field(field)}: {data}")

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
