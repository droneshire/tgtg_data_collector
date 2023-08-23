import typing as T


class Region(T.TypedDict):
    lattitude: float
    longitude: float
    radius: int


class Search(T.TypedDict):
    user: str
    region: Region
