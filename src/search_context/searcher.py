import typing as T
from datetime import datetime

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from validate_email_address import validate_email

from firebase.storage import FirebaseStorage
from firebase.user import FirebaseUser
from search_context.google_places import ADVANCED_FIELDS, DEFAULT_PROMPT, GooglePlacesAPI
from search_context.us_census import USCensusAPI
from search_context.util import SearchGrid
from util import csv_logger, email, file_util, log, short_url
from util.dict_util import safe_get
from util.fmt_util import get_pretty_seconds

MAX_SEARCH_CALLS = 20000


class Searcher:
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        google_api_key: str,
        us_census_api_key: str,
        results_csv: str,
        email_obj: email.Email,
        credentials_file: str,
        storage_bucket: str,
        max_search_calls: int = MAX_SEARCH_CALLS,
        auto_init: bool = True,
        clamp_at_max: bool = False,
        verbose: bool = False,
    ) -> None:
        self.google_places = GooglePlacesAPI(google_api_key, verbose=verbose)
        self.us_census = USCensusAPI(us_census_api_key)
        path_name = results_csv.split(".csv")[0]
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.places_csv = f"{path_name}_places_{date_str}.csv"
        self.census_csv = f"{path_name}_census_{date_str}.csv"
        self.email = email_obj
        self.max_search_calls = max_search_calls
        self.clamp_at_max = clamp_at_max
        self.verbose = verbose

        self.firestore_storage = FirebaseStorage(credentials_file, storage_bucket, verbose=verbose)
        self.firestore_user: FirebaseUser = FirebaseUser(
            credentials_file=credentials_file,
            send_email_callback=None,
            verbose=verbose,
            auto_init=auto_init,
        )
        self.common_data = {
            "timestamp": "",
            "search_name": "",
            "search_latitude": 0.0,
            "search_longitude": 0.0,
            "square_width_meters": 0.0,
            "search_num": 0,
            "grid_size": 0,
        }
        self.places_logger: T.Optional[csv_logger.CsvLogger] = None
        self.census_logger: T.Optional[csv_logger.CsvLogger] = None

    def _get_opening_hours(self, data: T.Dict[str, T.Any]) -> str:
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        formatted_hours = []

        regular_opening_hours = safe_get(data, ["regularOpeningHours"], {})

        for period in regular_opening_hours.get("periods", []):
            open_time = period["open"]
            close_time = period["close"]

            # Format the opening and closing times as strings
            open_str = f'{open_time["hour"]:02d}:{open_time["minute"]:02d}'
            close_str = f'{close_time["hour"]:02d}:{close_time["minute"]:02d}'

            # Map the day number to the day name and create the final string for this period
            day_str = f'{day_names[open_time["day"]]}: {open_str}-{close_str}'

            # Append the formatted string to the list
            formatted_hours.append(day_str)

        if not formatted_hours:
            return "No regular hours"

        # Join the list into a comma-separated string
        comma_separated_hours = ", ".join(formatted_hours)

        return comma_separated_hours

    def _get_flatten_places_data(
        self,
        data: T.Dict[str, T.Any],
    ) -> T.Dict[str, T.Any]:
        opening_hours = self._get_opening_hours(data)
        flattened_data = {
            "nationalPhoneNumber": safe_get(data, ["nationalPhoneNumber"], ""),
            "formattedAddress": safe_get(data, ["formattedAddress"], ""),
            "latitude": safe_get(data, ["location", "latitude"]),
            "longitude": safe_get(data, ["location", "longitude"]),
            "rating": safe_get(data, ["rating"]),
            "googleMapsUri": safe_get(data, ["googleMapsUri"], ""),
            "websiteUri": safe_get(data, ["websiteUri"], ""),
            "regularOpeningHours": opening_hours,
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

        common_copy = self.common_data.copy()
        common_copy.update(flattened_data)

        return common_copy

    def _get_places_results(
        self, prompt: str, fields: T.List[str], grid: SearchGrid
    ) -> T.List[T.Dict[str, T.Any]]:
        data = {"locationRestriction": {"rectangle": grid["viewport"]}}

        try:
            results = self.google_places.text_search(prompt, fields, data)
        except Exception as exception:  # pylint: disable=broad-except
            log.print_fail(
                f"Could not google places search for "
                f"{grid['center']['latitude']}, {grid['center']['longitude']}"
            )
            log.print_warn(exception)
            return []

        if "places" not in results:
            log.print_warn("No results found")
            return []

        return list(results["places"])

    def _get_census_results(self, fields: T.List[str], block_address: str) -> T.Dict[str, T.Any]:
        results: T.Dict[str, T.Any] = {}
        try:
            raw_results = self.us_census.get_census_data_from_address(fields, block_address)
            if raw_results:
                results = dict(raw_results)
        except Exception as exception:  # pylint: disable=broad-except
            log.print_fail(f"Could not census search for {block_address} with fields {fields}")
            log.print_warn(exception)
        return results

    def _update_common_data(
        self, search_name: str, search_size: int, grid: SearchGrid, time_zone: T.Any
    ) -> None:
        date_now = datetime.now()
        date_localized = time_zone.localize(date_now)
        local_offset = date_localized.utcoffset()
        local_time = date_localized - local_offset
        date_formated = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")

        self.common_data["timestamp"] = date_formated
        self.common_data["search_name"] = search_name
        self.common_data["search_latitude"] = grid["center"]["latitude"]
        self.common_data["search_longitude"] = grid["center"]["longitude"]
        self.common_data["square_width_meters"] = grid["width_meters"]
        self.common_data["grid_size"] = search_size
        self.common_data["search_num"] = self.common_data.get("search_num", 0) + 1  # type: ignore

    def _search_a_grid(
        self,
        prompt: str,
        places_fields: T.List[str],
        census_fields: T.List[str],
        census_year: int,
        grid: SearchGrid,
        dry_run: bool,
    ) -> T.Tuple[int, int]:
        if dry_run or self.census_logger is None or self.places_logger is None:
            return 0, 0

        places = self._get_places_results(prompt, places_fields, grid)
        address = None

        for place in places:
            if address is None:
                address = place.get("formattedAddress", None)
                if address and not self.us_census.is_usable_address(address):
                    address = None
            self.places_logger.write(self._get_flatten_places_data(place))

        log.print_bright(f"Found {len(places)} places, using {address} for census search")

        if not places or not census_fields or not address:
            return 0, 0

        census_results = self._get_census_results(census_fields, address)
        if census_results:
            common_copy = self.common_data.copy()
            common_copy["census_year"] = census_year
            census_results.update(common_copy)
            self.census_logger.write(census_results)

        return len(places), len(census_results.keys())

    def _setup_csv_loggers(self, census_fields: T.Optional[T.List[str]], dry_run: bool) -> None:
        if dry_run:
            return
        places_header = list(self._get_flatten_places_data({}).keys())
        census_header = (
            list(self.common_data.keys()) + ["census_year"] + census_fields if census_fields else []
        )
        self.places_logger = csv_logger.CsvLogger(csv_file=self.places_csv, header=places_header)
        self.census_logger = csv_logger.CsvLogger(csv_file=self.census_csv, header=census_header)

    def run_search(
        self,
        user: str,
        search_name: str,
        search_grid: T.List[SearchGrid],
        time_zone: T.Any,
        census_year: int,
        prompt: str = DEFAULT_PROMPT,
        places_fields: T.Optional[T.List[str]] = None,
        census_fields: T.Optional[T.List[str]] = None,
        and_upload: bool = True,
        dry_run: bool = False,
    ) -> None:
        log.print_bright(f"Starting {search_name} search...")

        self.firestore_user.update_from_firebase()

        if places_fields is None:
            places_fields = ADVANCED_FIELDS

        if census_fields is None:
            census_fields = []

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

        self._setup_csv_loggers(census_fields, dry_run)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=100),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[progress.completed]{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Grid Search", total=len(search_grid))

            places_found = 0
            census_found = 0

            for grid in search_grid:
                self._update_common_data(search_name, len(search_grid), grid, time_zone)

                places, census = self._search_a_grid(
                    prompt, places_fields, census_fields, census_year, grid, dry_run
                )
                places_found += places
                census_found += census
                progress.update(task, advance=1)

        self._maybe_upload_results(
            user,
            search_name,
            places_found,
            census_found,
            census_fields,
            len(search_grid),
            dry_run,
            and_upload,
        )

    def _maybe_upload_results(
        self,
        user: str,
        search_name: str,
        places_found: int,
        census_found: int,
        census_codes: T.List[str],
        num_grids: int,
        dry_run: bool,
        and_upload: bool,
    ) -> None:
        if dry_run:
            return

        self.firestore_user.clear_search_context(user, search_name)

        zip_name = self.census_csv.replace("census", "data").replace(".csv", ".tar.gz")

        # these are likely very large files, so we tar + compress them
        file_util.create_zip_archive([self.places_csv, self.census_csv], zip_name)

        if not and_upload:
            return

        url = self.firestore_storage.upload_file_and_get_url(
            user, zip_name, places_found + census_found
        )
        url = short_url.shorten_url(url)

        log.print_bright(f"Uploaded {zip_name} to {url}")

        if not validate_email(user):
            log.print_warn("Invalid email address")
            return

        expire_time_seconds = int(self.firestore_storage.EXP_TIME_MINUTES * 60.0)
        expire_time_pretty = get_pretty_seconds(expire_time_seconds, use_days=True)

        message = (
            f"Hello!\n\n"
            f"{search_name} results:\n"
            f"- {places_found} Google Places results\n"
            f"- {census_found} census results\n\n"
            f"Number of grids searched: {num_grids}\n\n"
            f"Census codes used:\n"
            f"- {', '.join(census_codes)}\n\n"
            "Untar/decompress the file to get the CSVs. There is one with the "
            "Google Places search results in it and another with the census data in it.\n\n"
            f"Download link (which expires in {expire_time_pretty}):\n"
            f"- {url}\n\n"
            f"Thanks,\n"
            f"Too Good To Go Research Team\n"
        )
        did_send_email = email.send_email(
            [self.email],
            [user],
            "Too Good To Go Places/Demographics Results",
            content=message,
            verbose=self.verbose,
        )

        if did_send_email:
            log.print_bright(f"Sent email to {user}")
        else:
            log.print_fail(f"Could not send email to {user}")
