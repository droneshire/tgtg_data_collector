import datetime
import json
import os
import time
import typing as T

import tgtg.exceptions as tgtg_exceptions
from tgtg import TgtgClient

from too_good_to_go import data_types
from util import file_util, log


class TgtgManager:
    MAX_PAGES_PER_REGION = 10
    MAX_ITEMS_PER_PAGE = 50

    def __init__(self, email: str, credentials_file: str, allow_create: bool = False) -> None:
        self.credentials_file = credentials_file
        self.email = email
        self.allow_create = allow_create

        self.client = None
        self.credentials: T.Dict[str, T.Any] = {}

    def init(self) -> None:
        self.credentials = self.load_credentials()

        if not self.credentials and self.allow_create:
            self.credentials = self.create_account()

        self.client = TgtgClient(**self.credentials)

        log.print_ok_blue_arrow(f"Logged in as {self.email}")

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

        for page in range(1, self.MAX_PAGES_PER_REGION + 1):
            new_data = self.client.get_items(
                favorites_only=False,
                latitude=region["latitude"],
                longitude=region["longitude"],
                radius=region["radius"],
                page_size=self.MAX_ITEMS_PER_PAGE,
                page=page,
            )
            if not new_data["results"]:
                break

            data["results"] += new_data["results"]
            time.sleep(0.5)

        return T.cast(data_types.GetItemResponse, data)

    def write_data_to_json(
        self, get_item_response: data_types.GetItemResponse, json_file: str
    ) -> None:
        file_util.make_sure_path_exists(json_file)

        if os.path.isfile(json_file):
            with open(json_file, "r", encoding="utf-8") as infile:
                data = json.load(infile)
        else:
            data = {}

        date_formated = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        data[date_formated] = get_item_response

        with open(json_file, "w", encoding="utf-8") as outfile:
            json.dump(data, outfile, indent=4)
