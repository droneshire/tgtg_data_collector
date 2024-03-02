import typing as T
from datetime import datetime

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from firebase.storage import FirebaseStorage
from firebase.user import FirebaseUser
from search_context.google_places import ADVANCED_FIELDS, DEFAULT_PROMPT, GooglePlacesAPI
from search_context.us_census import USCensusAPI
from search_context.util import SearchGrid
from util import csv_logger, log
from util.dict_util import safe_get

MAX_SEARCH_CALLS = 20000


class Searcher:
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        google_api_key: str,
        us_census_api_key: str,
        results_csv: str,
        email: str,
        credentials_file: str,
        storage_bucket: str,
        max_search_calls: int = MAX_SEARCH_CALLS,
        clamp_at_max: bool = False,
        verbose: bool = False,
    ) -> None:
        self.google_places = GooglePlacesAPI(google_api_key, verbose=verbose)
        self.us_census = USCensusAPI(us_census_api_key)
        self.results_csv = results_csv
        self.email = email
        self.max_search_calls = max_search_calls
        self.clamp_at_max = clamp_at_max
        self.verbose = verbose

        self.firestore_storage = FirebaseStorage(credentials_file, storage_bucket, verbose=verbose)
        self.firestore_user: FirebaseUser = FirebaseUser(
            credentials_file=credentials_file,
            send_email_callback=None,
            verbose=verbose,
            auto_init=False,
        )

        self.header = list(self._get_flatten_data("", "", {}).keys())

    def _get_flatten_data(self, search_name: str, timestamp: str, data: T.Dict) -> T.Dict:
        flattened_data = {
            "timestamp": timestamp,
            "search_name": search_name,
            "nationalPhoneNumber": safe_get(data, ["nationalPhoneNumber"], ""),
            "formattedAddress": safe_get(data, ["formattedAddress"], ""),
            "latitude": safe_get(data, ["location", "latitude"]),
            "longitude": safe_get(data, ["location", "longitude"]),
            "rating": safe_get(data, ["rating"]),
            "googleMapsUri": safe_get(data, ["googleMapsUri"], ""),
            "websiteUri": safe_get(data, ["websiteUri"], ""),
            "openNow": safe_get(data, ["regularOpeningHours", "openNow"]),
            "businessStatus": safe_get(data, ["businessStatus"], ""),
            "userRatingCount": safe_get(data, ["userRatingCount"]),
            "displayName": safe_get(data, ["displayName", "text"], ""),
            "primaryTypeDisplayName": safe_get(data, ["primaryTypeDisplayName", "text"], ""),
            "takeout": safe_get(data, ["takeout"]),
            "delivery": safe_get(data, ["delivery"]),
            "dineIn": safe_get(data, ["dineIn"]),
            "servesBreakfast": safe_get(data, ["servesBreakfast"]),
            "primaryType": safe_get(data, ["primaryType"]),
            "editorialSummary": safe_get(data, ["editorialSummary", "text"], ""),
            "acceptsCreditCards": safe_get(data, ["paymentOptions", "acceptsCreditCards"]),
            "acceptsCashOnly": safe_get(data, ["paymentOptions", "acceptsCashOnly"]),
            "wheelchairAccessibleParking": safe_get(
                data, ["accessibilityOptions", "wheelchairAccessibleParking"]
            ),
            "wheelchairAccessibleEntrance": safe_get(
                data, ["accessibilityOptions", "wheelchairAccessibleEntrance"]
            ),
            "wheelchairAccessibleRestroom": safe_get(
                data, ["accessibilityOptions", "wheelchairAccessibleRestroom"]
            ),
            "wheelchairAccessibleSeating": safe_get(
                data, ["accessibilityOptions", "wheelchairAccessibleSeating"]
            ),
        }

        for i in range(7):  # Assuming 7 days a week
            periods = safe_get(data, ["regularOpeningHours", "periods"], [])

            if i >= len(periods):
                continue

            flattened_data[f"open_day_{i}"] = safe_get(periods[i], ["open", "day"])
            flattened_data[f"open_hour_{i}"] = safe_get(periods[i], ["open", "hour"])
            flattened_data[f"open_minute_{i}"] = safe_get(periods[i], ["open", "minute"])
            flattened_data[f"close_day_{i}"] = safe_get(periods[i], ["close", "day"])
            flattened_data[f"close_hour_{i}"] = safe_get(periods[i], ["close", "hour"])
            flattened_data[f"close_minute_{i}"] = safe_get(periods[i], ["close", "minute"])

        for i, desc in enumerate(
            safe_get(data, ["regularOpeningHours", "weekdayDescriptions"], [])
        ):
            flattened_data[f"weekday_desc_{i}"] = desc

        return flattened_data

    def run_search(
        self,
        search_name: str,
        search_grid: T.List[SearchGrid],
        time_zone: T.Any,
        prompt: str = DEFAULT_PROMPT,
        fields: T.Optional[T.List[str]] = None,
        dry_run: bool = False,
    ) -> None:
        log.print_bright(f"Starting {search_name} search...")

        if fields is None:
            fields = ADVANCED_FIELDS

        log.print_normal("Checking grid size...")

        if len(search_grid) == 0:
            log.print_warn("No search grid provided")
            return

        if len(search_grid) > MAX_SEARCH_CALLS:
            log.print_fail_arrow(
                f"Search grid larger than maximum allowed: {len(search_grid)}/{MAX_SEARCH_CALLS}"
            )

            if not self.clamp_at_max:
                return

            log.print_warn(f"Clamping search grid at maximum of {MAX_SEARCH_CALLS}")
            search_grid = search_grid[:MAX_SEARCH_CALLS]

        csv = csv_logger.CsvLogger(csv_file=self.results_csv, header=self.header)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=100),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[progress.completed]{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Grid Search", total=len(search_grid))

            for grid in search_grid:
                data = {"locationRestriction": {"rectangle": grid["viewport"]}}

                date_now = datetime.now()
                date_localized = time_zone.localize(date_now)
                local_offset = date_localized.utcoffset()
                local_time = date_localized - local_offset

                date_formated = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")

                if dry_run:
                    progress.update(task, advance=1)
                    continue

                try:
                    results = self.google_places.text_search(prompt, fields, data)
                except Exception as exception:  # pylint: disable=broad-except
                    log.print_fail(
                        f"Could not search for "
                        f"{grid['center']['latitude']}, {grid['center']['longitude']}"
                    )
                    log.print_warn(exception)
                    progress.update(task, advance=1)
                    continue

                if "places" not in results:
                    log.print_warn("No results found")
                else:
                    for place in results["places"]:
                        csv.write(self._get_flatten_data(search_name, date_formated, dict(place)))

                progress.update(task, advance=1)
