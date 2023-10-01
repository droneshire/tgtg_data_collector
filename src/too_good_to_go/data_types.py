from typing import List, TypedDict


class Region(TypedDict):
    latitude: float
    longitude: float
    radius: int


class Search(TypedDict):
    user: str
    search_name: str
    region: Region
    hour_start: int
    hour_interval: int
    time_zone: str
    last_search_time: float
    last_download_time: float
    email_data: bool
    erase_data: bool
    num_results: int


class Price(TypedDict):
    code: str
    minor_units: int
    decimals: int


class Badge(TypedDict):
    badge_type: str
    rating_group: str
    percentage: int
    user_count: int
    month_count: int


class Picture(TypedDict):
    picture_id: str
    current_url: str


class Country(TypedDict):
    iso_code: str
    name: str


class Address(TypedDict):
    country: Country
    address_line: str
    city: str
    postal_code: str


class Location(TypedDict):
    longitude: float
    latitude: float


class StoreLocation(TypedDict):
    address: Address
    location: Location


class Item(TypedDict):
    item_id: str
    price: Price
    sales_taxes: List[str]
    tax_amount: Price
    price_excluding_taxes: Price
    price_including_taxes: Price
    value_excluding_taxes: Price
    value_including_taxes: Price
    taxation_policy: str
    show_sales_taxes: bool
    value: Price
    cover_picture: Picture
    logo_picture: Picture
    name: str
    description: str
    can_user_supply_packaging: bool
    packaging_option: str
    collection_info: str
    diet_categories: List[str]
    item_category: str
    badges: List[Badge]
    favorite_count: int
    buffet: bool


class Store(TypedDict):
    store_id: str
    store_name: str
    branch: str
    description: str
    tax_identifier: str
    website: str
    store_location: StoreLocation
    logo_picture: Picture
    store_time_zone: str
    hidden: bool
    favorite_count: int
    we_care: bool


class Result(TypedDict):
    item: Item
    store: Store
    display_name: str
    pickup_location: StoreLocation
    items_available: int
    distance: float
    favorite: bool
    in_sales_window: bool
    new_item: bool


class GetItemResponse(TypedDict):
    results: List[Result]
