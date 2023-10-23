"""
TgtgClient implementation using cloudscraper for the request session.
"""
import typing as T

import cloudscraper
from tgtg import BASE_URL, DEFAULT_ACCESS_TOKEN_LIFETIME, TgtgClient

from util import log


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

        self.session = cloudscraper.session()
        self.session.headers = super()._headers

    def reset_session(self, proxies: T.Dict[str, str]) -> T.Dict[str, str]:
        if self.proxies == proxies:
            return self.proxies
        log.print_bright(f"Resetting session with new proxy: {proxies}")
        self.proxies = proxies
