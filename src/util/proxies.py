"""
Get proxies from various sources.
"""
import os

import dotenv
from fp.fp import FreeProxy


class Proxies:
    def get(self):
        raise NotImplementedError


class ScrapeDogProxy(Proxies):
    def __init__(self):
        dotenv.load_dotenv()
        api_key = os.getenv("SCRAPER_DOG_PROXY_API_KEY")
        assert api_key is not None, "Missing SCRAPER_DOG_PROXY_API_KEY in .env"
        self.proxy_url = {"http:", f"http://scrapingdog:{api_key}@proxy.scrapingdog.com:8081"}

    def get(self):
        return self.proxy_url


class FreeProxyProxy(Proxies):
    def get(self):
        return {"http": FreeProxy(elite=True, rand=True).get()}
