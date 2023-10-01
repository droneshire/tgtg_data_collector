"""
TgtgClient implementation using cloudscraper for the request session.
"""

import cloudscraper
from tgtg import BASE_URL, DEFAULT_ACCESS_TOKEN_LIFETIME, TgtgClient


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

        self.session = cloudscraper.session(debug=True)
        self.session.headers = super()._headers
