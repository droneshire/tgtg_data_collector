"""
TgtgClient implementation using cloudscraper for the request session.
"""
import datetime
import json
import sys
import time
import typing as T
from http import HTTPStatus

import cloudscraper
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from tgtg import (
    AUTH_POLLING_ENDPOINT,
    BASE_URL,
    DEFAULT_ACCESS_TOKEN_LIFETIME,
    SIGNUP_BY_EMAIL_ENDPOINT,
    TgtgAPIError,
    TgtgClient,
    TgtgLoginError,
    TgtgPollingError,
)

from util import log

MAX_POLLING_TRIES = 60
POLLING_WAIT_TIME = 60


class TgtgCloudscraperClient(TgtgClient):
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        url=BASE_URL,
        email=None,
        access_token=None,
        refresh_token=None,
        user_id=None,
        user_agent=None,
        language="en-UK",
        proxies=None,
        timeout=None,
        last_time_token_refreshed=None,
        access_token_lifetime=DEFAULT_ACCESS_TOKEN_LIFETIME,
        device_type="ANDROID",
        cookie=None,
        chrome_paths: T.Optional[T.Dict[str, str]] = None,
    ):
        super().__init__(
            url,
            email,
            access_token,
            refresh_token,
            user_id,
            user_agent,
            language,
            proxies,
            timeout,
            last_time_token_refreshed,
            access_token_lifetime,
            device_type,
            cookie,
        )

        self.captcha_timeout = 10.0

        if chrome_paths:
            self.web_driver = self._get_driver(chrome_paths=chrome_paths)
        else:
            self.web_driver = None
        self.session = cloudscraper.session()
        self.session.headers = super()._headers

    @staticmethod
    def _get_driver(chrome_paths: T.Dict[str, str]) -> uc.Chrome:
        log.print_bold("Creating Chrome Driver...")
        options = Options()
        options.add_argument("--no-first-run --no-service-autorun --password-store=basic")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=960,540")
        options.binary_location = chrome_paths["browser"]

        driver = uc.Chrome(
            options=options, executable_path=chrome_paths["driver"], delay=10, headless=False
        )

        driver.set_page_load_timeout(120)
        driver.implicitly_wait(120)

        log.print_ok_arrow("Successfully created chrome driver")
        return driver

    def reset_session(self, proxies: T.Dict[str, str]) -> None:
        self.proxies = proxies

    # this method is a copy of the same function within tgtg.py, except we overload the polling
    # and polling attempts so that we can have it wait longer for the email to arrive.
    # this is literally copy past from the original tgtg.py file
    def start_polling(self, polling_id):
        for _ in range(MAX_POLLING_TRIES):
            response = self.session.post(
                self._get_url(AUTH_POLLING_ENDPOINT),
                headers=self._headers,
                json={
                    "device_type": self.device_type,
                    "email": self.email,
                    "request_polling_id": polling_id,
                },
                proxies=self.proxies,
                timeout=self.timeout,
            )
            if response.status_code == HTTPStatus.ACCEPTED:  # pylint: disable=no-else-continue
                sys.stdout.write(
                    "Check your mailbox on PC to continue... "
                    "(Mailbox on mobile won't work, if you have installed tgtg app.)\n"
                )
                time.sleep(POLLING_WAIT_TIME)
                continue
            elif response.status_code == HTTPStatus.OK:  # pylint: disable=no-else-continue
                sys.stdout.write("Logged in!\n")
                login_response = response.json()
                self.access_token = login_response["access_token"]
                self.refresh_token = login_response["refresh_token"]
                self.last_time_token_refreshed = datetime.datetime.now()
                self.user_id = login_response["startup_data"]["user"]["user_id"]
                self.cookie = response.headers["Set-Cookie"]
                return
            else:  # pylint: disable=no-else-raise
                if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                    raise TgtgAPIError(response.status_code, "Too many requests. Try again later.")
                else:
                    raise TgtgLoginError(response.status_code, response.content)

        raise TgtgPollingError(
            f"Max retries ({MAX_POLLING_TRIES * POLLING_WAIT_TIME} seconds) reached. Try again."
        )

    # Same here, overloading this call so that we can use selenium to get the cookies
    def signup_by_email(
        self,
        *,
        email,
        name="",
        country_id="GB",
        newsletter_opt_in=False,
        push_notification_opt_in=True,
    ) -> T.Optional["TgtgClient"]:
        response = self.session.post(
            self._get_url(SIGNUP_BY_EMAIL_ENDPOINT),
            headers=self._headers,
            json={
                "country_id": country_id,
                "device_type": self.device_type,
                "email": email,
                "name": name,
                "newsletter_opt_in": newsletter_opt_in,
                "push_notification_opt_in": push_notification_opt_in,
            },
            proxies=self.proxies,
            timeout=self.timeout,
        )
        if response.status_code == HTTPStatus.OK:
            self.access_token = response.json()["login_response"]["access_token"]
            self.refresh_token = response.json()["login_response"]["refresh_token"]
            self.last_time_token_refreshed = datetime.datetime.now()
            self.user_id = response.json()["login_response"]["startup_data"]["user"]["user_id"]
            return self

        if response.status_code == HTTPStatus.FORBIDDEN:
            if self.web_driver is None:
                raise TgtgAPIError(response.status_code, response.content)

            timeout = self.captcha_timeout
            response_bytes = response.content.decode("utf-8")
            response_json = json.loads(response_bytes)
            auth_url = response_json["url"]
            self.web_driver.get(auth_url)
            time.sleep(timeout)

            cookies = self.web_driver.get_cookies()
            for cookie in cookies:
                print(cookie)
        else:
            raise TgtgAPIError(response.status_code, response.content)

        return None
