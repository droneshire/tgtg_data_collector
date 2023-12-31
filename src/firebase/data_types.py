import datetime
import typing as T

from constants import INTERVALS


class HealthMonitor(T.TypedDict):
    reset: bool
    heartbeat: datetime.datetime


class Email(T.TypedDict):
    email: str
    updatesEnabled: bool


class Notifications(T.TypedDict):
    email: Email


class TimeZone(T.TypedDict):
    abbrev: str
    altName: str
    label: str
    offset: int
    value: str


class Preferences(T.TypedDict):
    notifications: Notifications
    searchTimeZone: TimeZone
    deleteDataOnDownload: bool
    storeRawData: bool


class Region(T.TypedDict):
    latitude: float
    longitude: float
    radius: int


class Search(T.TypedDict):
    region: Region
    sendEmail: bool
    uploadOnly: bool
    eraseData: bool
    lastSearchTime: float
    lastDownloadTime: float
    numResults: int
    uuid: str


class Searches(T.TypedDict):
    items: T.Dict[str, Search]
    hoursBetweenCollection: int
    collectionTimeStart: int


class User(T.TypedDict):
    preferences: Preferences
    searches: Searches


NULL_USER = User(
    preferences=Preferences(
        notifications=Notifications(
            email=Email(email="", updatesEnabled=False),
        ),
        searchTimeZone=TimeZone(
            abbrev="PDT",
            altName="Pacific Daylight Time",
            label="(GMT-07:00) Pacific Time",
            offset=-7,
            value="America/Los_Angeles",
        ),
        deleteDataOnDownload=False,
        storeRawData=False,
    ),
    searches=Searches(
        items={},
        hoursBetweenCollection=min(INTERVALS),
        collectionTimeStart=6,
    ),
)
