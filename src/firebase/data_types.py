import datetime
import typing as T


class HealthMonitor(T.TypedDict):
    reset: bool
    heartbeat: datetime.datetime


class Email(T.TypedDict):
    email: str
    updatesEnabled: bool


class Sms(T.TypedDict):
    phoneNumber: str
    updatesEnabled: bool


class Notifications(T.TypedDict):
    email: Email
    sms: Sms


class Preferences(T.TypedDict):
    notifications: Notifications


class Region(T.TypedDict):
    lattitude: float
    longitude: float
    radius: int


class User(T.TypedDict):
    preferences: Preferences
    regions: T.List[Region]


NULL_USER = User(
    preferences=Preferences(
        notifications=Notifications(
            email=Email(email="", updatesEnabled=False),
            sms=Sms(
                phoneNumber="",
                updatesEnabled=False,
            ),
        )
    ),
    regions=[
        Region(
            lattitude=0.0,
            longitude=0.0,
            radius=0,
        )
    ],
)
