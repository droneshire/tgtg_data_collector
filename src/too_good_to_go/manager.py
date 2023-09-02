import json
import os
import typing as T

from tgtg import TgtgClient

from util import file_util, log


class TgtgManager:
    def __init__(self, email: str, credentials_file: str, allow_create: bool = False) -> None:
        self.credentials_file = credentials_file
        self.email = email

        self.client = TgtgClient(email=self.email)

        self.credentials = self.load_credentials()

        if not self.credentials and allow_create:
            self.credentials = self.create_account()

    def save_credentials(self, credentials: T.Dict[str, T.Any]) -> T.Dict[str, T.Any]:
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

        if email:
            return all_credentials.get(email, {})
        else:
            return all_credentials

    def create_account(self) -> T.Dict[str, T.Any]:
        try:
            TgtgClient().signup_by_email(email=self.email)
        except TypeError:
            log.print_fail(f"Failed to create account for {self.email}!")
            return {}

        credentials = dict(self.client.get_credentials())

        log.print_ok(f"Account Credentials for {self.email}:")
        log.print_bright(f"{json.dumps(credentials, indent=4)}")

        self.save_credentials(credentials)

        return credentials

    def load_credentials(self) -> T.Dict[str, T.Any]:
        credentials = {}

        if not os.path.exists(self.credentials_file):
            log.print_warn(f"Credentials file {self.credentials_file} does not exist!")

            credentials = self.client.get_credentials()

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
