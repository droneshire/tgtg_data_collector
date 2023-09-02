import json
import os
import typing as T

from tgtg import TgtgClient

from util import file_util, log


class TgtgManager:
    def __init__(self, email: str, credentials_file: str, allow_create: bool = False) -> None:
        self.credentials_file = credentials_file
        self.credentials = self.load_credentials()

        if not self.credentials and allow_create:
            self.credentials = self.create_account()

        self.email = email

    def create_account(self) -> T.Dict[str, T.Any]:
        try:
            TgtgClient().signup_by_email(email=self.email)
        except TypeError:
            log.print_fail(f"Failed to create account for {self.email}!")
            return {}

        client = TgtgClient(email=self.email)
        credentials = dict(client.get_credentials())

        log.print_ok(f"Account Credentials for {self.email}:")
        log.print_bright(f"{json.dumps(credentials, indent=4)}")

        file_util.make_sure_path_exists(os.path.dirname(self.credentials_file))

        if os.path.exists(self.credentials_file):
            with open(self.credentials_file, "r", encoding="utf-8") as infile:
                data = json.load(infile)
                all_credentials = dict(data) if data else {}
        else:
            all_credentials = {}

        all_credentials[self.email] = credentials

        with open(self.credentials_file, "w", encoding="utf-8") as outfile:
            json.dump(all_credentials, outfile, indent=4)

        return credentials

    def load_credentials(self) -> T.Dict[str, T.Any]:
        if not os.path.exists(self.credentials_file):
            log.print_fail(f"Credentials file {self.credentials_file} does not exist!")
            return {}

        with open(self.credentials_file, "r", encoding="utf-8") as infile:
            data = json.load(infile)
            all_credentials = dict(data) if data else {}

        return all_credentials.get(self.email, {})
