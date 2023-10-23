import datetime
import json
import os
import random
import time
import typing as T

import tgtg.exceptions as tgtg_exceptions

from too_good_to_go import data_types
from too_good_to_go.tgtg_cloudscraper_client import TgtgCloudscraperClient as TgtgClient
from util import csv_logger, file_util, log, proxies
from util.dict_util import safe_get

PROXY = proxies.FreeProxyProxy


class TgtgManager:
    MAX_PAGES_PER_REGION = 20
    MAX_ITEMS_PER_PAGE = 400

    def __init__(
        self,
        email: str,
        credentials_file: str,
        allow_create: bool = False,
        use_proxies: bool = True,
    ) -> None:
        self.credentials_file = credentials_file
        self.email = email
        self.allow_create = allow_create

        self.client: T.Optional[TgtgClient] = None
        self.credentials: T.Dict[str, T.Any] = {}

        self.proxies: T.Any = PROXY() if use_proxies else None

        assert self.MAX_ITEMS_PER_PAGE <= 400, "MAX_ITEMS_PER_PAGE must be <= 400"

    def init(self) -> None:
        self.credentials = self.load_credentials()

        if not self.credentials and self.allow_create:
            self.credentials = self.create_account()

        params = self.credentials
        if self.proxies is not None:
            params.update({"proxies": self.proxies.get()})
        self.client = TgtgClient(**params)

        assert self.client is not None, "Client not initialized!"

        self._refresh_token()

        log.print_ok_blue_arrow(f"Logged in as {self.email}")

    def run(self) -> None:
        self._refresh_token()

    def save_credentials(self, credentials: T.Dict[str, T.Any]) -> None:
        file_util.make_sure_path_exists(os.path.dirname(self.credentials_file))

        if os.path.exists(self.credentials_file):
            self.read_credentials()
        else:
            all_credentials = {}

        all_credentials[self.email] = credentials

        with open(self.credentials_file, "w", encoding="utf-8") as outfile:
            json.dump(all_credentials, outfile, indent=4)

    def read_credentials(self, email: T.Optional[str] = None) -> T.Dict[str, T.Any]:
        if not os.path.exists(self.credentials_file):
            log.print_warn(f"Credentials file {self.credentials_file} does not exist!")
            return {}

        with open(self.credentials_file, "r", encoding="utf-8") as infile:
            data = json.load(infile)
            all_credentials = dict(data) if data else {}

        return all_credentials.get(email, {}) if email else all_credentials

    def create_account(self) -> T.Dict[str, T.Any]:
        try:
            TgtgClient().signup_by_email(email=self.email)
        except TypeError:
            log.print_fail(f"Failed to create account for {self.email}!")
            return {}
        except tgtg_exceptions.TgtgAPIError as exception:
            log.print_fail(f"Failed to create account for {self.email}!")
            log.print_fail(f"{exception}")
            return {}

        credentials = dict(TgtgClient(email=self.email).get_credentials())

        log.print_ok(f"Account Credentials for {self.email}:")
        log.print_bright(f"{json.dumps(credentials, indent=4)}")

        self.save_credentials(credentials)

        return credentials

    def load_credentials(self) -> T.Dict[str, T.Any]:
        credentials = {}

        if not os.path.exists(self.credentials_file):
            log.print_warn(f"Credentials file {self.credentials_file} does not exist!")

            credentials = TgtgClient(email=self.email).get_credentials()

            if credentials:
                self.save_credentials(credentials)
            else:
                log.print_warn(f"Failed to get credentials for {self.email}!")
                return {}
        else:
            credentials = self.read_credentials(self.email)

        log.print_ok(f"Account Credentials for {self.email}:")
        log.print_bright(f"{json.dumps(credentials, indent=4)}")

        return credentials

    def search_region(self, region: data_types.Region) -> data_types.GetItemResponse:
        if self.client is None:
            log.print_fail("Client not initialized!")
            return data_types.GetItemResponse({"results": []})

        # attempt to read and concatenate all pages
        data = data_types.GetItemResponse({"results": []})

        log.print_bold("Searching region...")

        for page in range(1, self.MAX_PAGES_PER_REGION + 1):
            log.print_normal(f"Searching page {page} out of max {self.MAX_PAGES_PER_REGION}")
            new_data = None
            try:
                new_data = self.client.get_items(
                    favorites_only=False,
                    latitude=region["latitude"],
                    longitude=region["longitude"],
                    radius=region["radius"],
                    page_size=self.MAX_ITEMS_PER_PAGE,
                    page=page,
                )
            except tgtg_exceptions.TgtgAPIError as exception:
                log.print_fail(f"Failed to get items for page {page}!")
                log.print_fail(f"{exception}")
                if self.proxies is not None:
                    self.client.reset_session(self.proxies.get())

            if not new_data or not isinstance(new_data, list):
                break

            data["results"].extend(new_data)
            time.sleep(random.uniform(5, 20))

        return T.cast(data_types.GetItemResponse, data)

    def write_data_to_json(
        self, get_item_response: data_types.GetItemResponse, json_file: str, time_zone: T.Any
    ) -> None:
        file_util.make_sure_path_exists(json_file)

        date_now = datetime.datetime.now()
        date_localized = time_zone.localize(date_now)
        date_formated = date_localized.strftime("%Y-%m-%d %H:%M:%S")
        new_data = {date_formated: get_item_response}
        new_data_json = json.dumps(new_data, indent=4)

        # in order to not need to read the whole file, we can just append to the end. this assumes
        # that the file is a valid json file and that the first and last characters are '{' and '}'
        if os.path.isfile(json_file):
            with open(json_file, "a+", encoding="utf-8") as outfile:
                outfile.seek(0, os.SEEK_END)
                pos = outfile.tell() - 1

                if pos > 0:
                    # Find the position of the last closing brace '}'
                    while pos >= 0 and outfile.read(1) != "}":
                        pos -= 1

                    if pos >= 0:
                        outfile.seek(pos)  # Go to the last '}'
                        outfile.truncate()  # Truncate from there

                        # Move to the end of the last content line (before a newline)
                        while pos >= 0 and outfile.read(1) != "\n":
                            pos -= 1

                        if pos >= 0:
                            outfile.seek(pos + 1)
                            outfile.write(",")

                outfile.write("\n")
        else:
            with open(json_file, "w", encoding="utf-8") as outfile:
                outfile.write("{\n")

        with open(json_file, "a", encoding="utf-8") as outfile:
            outfile.write(new_data_json[1:-1])
            outfile.write("}")

    @staticmethod
    def convert_to_price(data: T.Dict[str, T.Any], field: str) -> str:
        if not data:
            return ""

        value_including_taxes_dict = safe_get(data, field.split("."), {})

        if not value_including_taxes_dict:
            return ""

        code = str(value_including_taxes_dict.get("code", ""))
        minor_units = int(value_including_taxes_dict["minor_units"])
        decimals = int(value_including_taxes_dict["decimals"])

        price = float(minor_units) / (10**decimals)
        price_string = f"{price:.2f} {code}"
        return price_string

    def _refresh_token(self) -> None:
        # call the client login method to refresh the token if needed.
        # the login function will automatically refresh the token based on internal
        # refresh token logic
        if self.client is None:
            return

        self.client.login()

    def _get_flatten_data(self, timestamp: str, data: T.Dict) -> T.Dict:
        flattened = {}

        flattened["timestamp"] = timestamp
        flattened["store_id"] = safe_get(data, "store.store_id".split("."), "")
        flattened["store_name"] = safe_get(data, "store.store_name".split("."), "")
        flattened["pickup_location:location:longitude"] = safe_get(
            data, "pickup_location.location.longitude".split("."), ""
        )
        flattened["pickup_location:location:latitude"] = safe_get(
            data, "pickup_location.location.latitude".split("."), ""
        )
        flattened["pickup_interval:start"] = safe_get(data, "pickup_interval.start".split("."), "")
        flattened["pickup_interval:end"] = safe_get(data, "pickup_interval.end".split("."), "")
        flattened["items_available"] = safe_get(data, "items_available".split("."), "")
        flattened["sold_out_at"] = safe_get(data, "sold_out_at".split("."), "")
        flattened["item_type"] = safe_get(data, "item_type".split("."), "")
        flattened["item_category"] = safe_get(data, "item.item_category".split("."), "")

        flattened["price_including_taxes"] = self.convert_to_price(
            data, "item.price_including_taxes"
        )
        flattened["value_including_taxes"] = self.convert_to_price(
            data, "item.value_including_taxes"
        )

        flattened["average_overall_rating:average_overall_rating"] = safe_get(
            data, "item.average_overall_rating.average_overall_rating".split("."), ""
        )
        flattened["average_overall_rating:rating_count"] = safe_get(
            data, "item.average_overall_rating.rating_count".split("."), ""
        )
        flattened["average_overall_rating:month_count"] = safe_get(
            data, "item.average_overall_rating.month_count".split("."), ""
        )
        flattened["favorite_count"] = safe_get(data, "item.favorite_count".split("."), "")

        return flattened

    def write_data_to_csv(
        self, get_item_response: data_types.GetItemResponse, csv_file: str, time_zone: T.Any
    ) -> None:
        file_util.make_sure_path_exists(csv_file)

        date_now = datetime.datetime.now()
        date_localized = time_zone.localize(date_now)
        local_offset = date_localized.utcoffset()
        local_time = date_localized - local_offset

        date_formated = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")

        header = list(self._get_flatten_data(date_formated, {}).keys())

        csv = csv_logger.CsvLogger(csv_file=csv_file, header=header)

        for item in get_item_response["results"]:
            csv.write(self._get_flatten_data(date_formated, dict(item)))
