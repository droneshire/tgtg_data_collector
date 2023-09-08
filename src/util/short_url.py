import pyshorteners


def shorten_url(long_url: str) -> str:
    shortener = pyshorteners.Shortener()
    url = shortener.tinyurl.short(long_url)
    return str(url) if url else long_url
