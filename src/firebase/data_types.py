import datetime
import typing as T


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


class Region(T.TypedDict):
    lattitude: float
    longitude: float
    radius: int


class Search(T.TypedDict):
    name: str
    region: Region


class Searches(T.TypedDict):
    searches: T.List[Search]
    sendData: bool


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
    ),
    searches=Searches(
        searches=[],
        sendData=False,
    ),
)
