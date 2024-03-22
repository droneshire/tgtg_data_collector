import copy
import enum
import hashlib
import json
import threading
import time
import typing as T

import deepdiff
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1.collection import CollectionReference
from google.cloud.firestore_v1.watch import DocumentChange, Watch

from firebase import data_types as firebase_data_types
from too_good_to_go import data_types as too_good_to_go_data_types
from util import log
from util.dict_util import check_dict_keys_recursive, patch_missing_keys_recursive, safe_get

SendEmailCallbackType = T.Callable[[str, too_good_to_go_data_types.Search], None]


class Changes(enum.Enum):
    ADDED = 1
    MODIFIED = 2
    REMOVED = 3


class FirebaseUser:
    HEALTH_PING_TIME = 60 * 30

    def __init__(
        self,
        credentials_file: str,
        send_email_callback: T.Optional[SendEmailCallbackType] = None,
        verbose: bool = False,
        auto_init: bool = True,
    ) -> None:
        if not firebase_admin._apps:  # pylint: disable=protected-access
            auth = credentials.Certificate(credentials_file)
            firebase_admin.initialize_app(auth)
        self.credentials_file = credentials_file
        self.database = firestore.client()
        self.verbose = verbose

        self.user_ref: CollectionReference = self.database.collection("user")
        self.admin_ref: CollectionReference = self.database.collection("admin")

        self.users_watcher: T.Optional[Watch] = None

        self.database_cache: T.Dict[str, firebase_data_types.User] = {}

        self.callback_done: threading.Event = threading.Event()
        self.database_cache_lock: threading.RLock = threading.RLock()

        self.last_health_ping: T.Optional[float] = None

        self._send_email_callback: T.Optional[SendEmailCallbackType] = send_email_callback

        if auto_init:
            self.init()

    def init(self) -> None:
        self.users_watcher = self.user_ref.on_snapshot(self._collection_snapshot_handler)

    def _delete_user(self, name: str) -> None:
        """
        Delete a user from the cache. This should be called when a user is removed
        from the database. This just removes the cache. The cache gets updated
        periodically to firestore.
        """
        with self.database_cache_lock:
            if name in self.database_cache:
                del self.database_cache[name]
        log.print_warn(f"Deleting user {name} from cache")

    def _maybe_upload_db_cache_to_firestore(
        self,
        user: str,
        old_db_user: firebase_data_types.User,
        db_user: firebase_data_types.User,
    ) -> None:
        """
        Upload the database cache to firestore if there are differences between the
        old and new user. This should be called periodically to ensure that the
        firestore database is up to date with the cache.
        App -> Firstore
        """
        diff = deepdiff.DeepDiff(
            old_db_user,
            db_user,
            ignore_order=True,
        )
        if not diff:
            return

        log.print_normal(
            f"Updated user {user} in database:\n{diff.to_json(indent=4, sort_keys=True)}"
        )

        user_dict_firestore = json.loads(json.dumps(db_user))

        self.user_ref.document(user).set(user_dict_firestore)

    def _collection_snapshot_handler(
        self,
        collection_snapshot: T.List[DocumentSnapshot],
        changed_docs: T.List[DocumentChange],
        read_time: T.Any,
    ) -> None:
        """
        Handle a collection snapshot from the firestore database. This is a callback
        and is asynchronous. We need to be careful to not block the main thread.
        We just update the cache here and then signal the main thread that we are done
        for further processing.

        Firestore -> App
        """
        # pylint: disable=unused-argument
        log.print_warn(f"Received collection snapshot for {len(collection_snapshot)} documents")

        users = self.database_cache.keys()
        with self.database_cache_lock:
            self.database_cache = {}
            for doc in collection_snapshot:
                doc_dict = doc.to_dict()
                if not doc_dict:
                    continue
                self.database_cache[doc.id] = doc_dict  # type: ignore
                log.print_normal(f"{json.dumps(doc_dict, indent=4, sort_keys=True)}")

        for user in users:
            if user not in self.database_cache:
                self._delete_user(user)

        for change in changed_docs:
            doc_id = change.document.id
            email = safe_get(
                dict(self.database_cache[doc_id]),
                "preferences.notifications.email.email".split("."),
                "",
            )

            if change.type.name == Changes.ADDED.name:
                log.print_ok_blue(f"Added document: {doc_id} for {email}")
            elif change.type.name == Changes.MODIFIED.name:
                log.print_ok_blue(f"Modified document: {doc_id} for {email}")
            elif change.type.name == Changes.REMOVED.name:
                log.print_ok_blue(f"Removed document: {doc_id} for {email}")
                self._delete_user(doc_id)

        for search_hash, search_item in self.get_searches(verbose=False).items():
            # We could kick off the search context jobs here as well, but since they
            # are not time sensitive due to how long they take, we can just wait for
            # the next iteration of the main loop to do it.
            if search_item.get("email_data", False) and self._send_email_callback is not None:
                self._send_email_callback(search_hash, search_item)

        self.callback_done.set()

    def _handle_firebase_update(self, user: str, db_user: firebase_data_types.User) -> None:
        log.print_normal(f"Checking to see if we need to update {user} databases...")
        old_db_user = copy.deepcopy(db_user)

        if not db_user:
            db_user = copy.deepcopy(firebase_data_types.NULL_USER)
            log.print_normal(
                f"Initializing new user {user} in database:\n"
                f"{json.dumps(db_user, indent=4, sort_keys=True)}"
            )
        missing_keys = check_dict_keys_recursive(dict(firebase_data_types.NULL_USER), dict(db_user))
        if missing_keys:
            log.print_warn(f"Missing keys in user {user}:\n{missing_keys}")
            patch_missing_keys_recursive(dict(firebase_data_types.NULL_USER), dict(db_user))

        self._maybe_upload_db_cache_to_firestore(user, old_db_user, db_user)

    @property
    def send_email_callback(self) -> SendEmailCallbackType:
        assert self._send_email_callback is not None, "Send email callback is None"
        return self._send_email_callback

    @send_email_callback.setter
    def send_email_callback(self, callback: SendEmailCallbackType) -> None:
        self._send_email_callback = callback

    def get_users(self) -> T.Dict[str, firebase_data_types.User]:
        with self.database_cache_lock:
            return copy.deepcopy(self.database_cache)

    def update_watchers(self) -> None:
        log.print_normal("Updating watcher...")
        if self.users_watcher:
            self.users_watcher.unsubscribe()

        self.users_watcher = self.user_ref.on_snapshot(self._collection_snapshot_handler)

    def update_from_firebase(self) -> None:
        """
        Synchronous update from firebase database. We do this periodically to ensure
        that we are not missing any updates from the database. This is a fallback
        mechanism in case the watcher fails, which it seems to periodically do.
        """
        log.print_warn("Updating from firebase database instead of cache")
        users = self.database_cache.keys()
        with self.database_cache_lock:
            self.database_cache = {}
            for doc in self.user_ref.list_documents():
                self.database_cache[doc.id] = doc.get().to_dict()

        for user in users:
            if user not in self.database_cache:
                self._delete_user(user)

        self.callback_done.set()

    def check_and_maybe_handle_firebase_db_updates(self) -> None:
        """
        Syncronous check for updates from the firebase database. This calls a
        centralized callback to handle syncronous and asynchronous updates from the
        database.
        """
        if self.callback_done.is_set():
            self.callback_done.clear()
            log.print_bright("Handling firebase database updates")
            for user, info in self.database_cache.items():
                self._handle_firebase_update(user, info)

    def health_ping(self) -> None:
        if self.last_health_ping and time.time() - self.last_health_ping < self.HEALTH_PING_TIME:
            return

        self.last_health_ping = time.time()

        log.print_ok_arrow("Health ping")
        # pylint: disable=no-member
        self.admin_ref.document("health_monitor").set(
            {"heartbeat": firestore.SERVER_TIMESTAMP}, merge=True
        )

    def check_and_maybe_update_to_firebase(
        self, user: str, db_user: firebase_data_types.User
    ) -> None:
        if user not in self.database_cache:
            return

        old_db_user = copy.deepcopy(self.database_cache[user])

        self._maybe_upload_db_cache_to_firestore(user, old_db_user, db_user)

    @staticmethod
    def get_uuid(search: too_good_to_go_data_types.Search, verbose: bool = False) -> str:
        if not search:
            if verbose:
                log.print_warn(f"Search {search} is None")
            return ""

        if not search.get("user"):
            if verbose:
                log.print_warn(f"Search {search} has no user")
            return ""

        if not search.get("region"):
            if verbose:
                log.print_warn(f"Search {search} has no region")
            return ""

        if (
            not search["region"].get("latitude")
            or not search["region"].get("longitude")
            or not search["region"].get("radius")
        ):
            if verbose:
                log.print_warn(f"Search {search} has invalid region")
            return ""

        search_hash = "_".join(
            [
                search["user"],
                str(search["region"]["latitude"]),
                str(search["region"]["longitude"]),
                str(search["region"]["radius"]),
                str(search["hour_start"]),
                str(search["hour_interval"]),
                str(search["time_zone"]),
            ]
        )
        md5 = hashlib.md5()
        md5.update(search_hash.encode())
        search_uuid_hex = md5.hexdigest()

        if verbose:
            log.print_normal(f"Search {json.dumps(search, indent=4)} has uuid {search_uuid_hex}")

        return search_uuid_hex

    def update_search_stats(
        self, user: str, search_name: str, last_search_time: float, new_results: int, uuid: str
    ) -> None:
        search_item = self._get_search_item(search_name)

        if search_item is None:
            log.print_warn(f"User {user} has no search named {search_name}")
            return

        previous_count = search_item.get("numResults", 0)
        new_count = previous_count + new_results

        self._update_search_fields(
            user,
            search_name,
            ["lastSearchTime", "numResults", "uuid"],
            [last_search_time, new_count, uuid],
        )

    def update_after_data_erase(self, user: str, search_name: str) -> None:
        self._update_search_fields(user, search_name, ["numResults", "eraseData"], [0, False])

    def update_search_email(self, user: str, search_name: str) -> None:
        self._update_search_fields(
            user,
            search_name,
            ["sendEmail", "lastDownloadTime", "uploadOnly"],
            [False, time.time(), False],
        )

    def _get_search_item(self, search_name: str) -> T.Optional[firebase_data_types.Search]:
        with self.database_cache_lock:
            for _, info in self.database_cache.items():
                search_items = safe_get(dict(info), "searches.items".split("."), {})
                if not search_items:
                    continue

                if search_name in search_items:
                    return T.cast(firebase_data_types.Search, search_items[search_name])

        return None

    def _update_search_fields(
        self, user: str, search_name: str, fields: T.List[str], values: T.List[T.Any]
    ) -> None:
        assert len(fields) == len(values), "Fields and values must be the same length"

        with self.database_cache_lock:
            if user not in self.database_cache:
                log.print_warn(f"User {user} not in database cache")
                return

            old_db_user = copy.deepcopy(self.database_cache[user])
            db_user = copy.deepcopy(self.database_cache[user])

        search_item = self._get_search_item(search_name)

        if search_item is None:
            log.print_warn(f"User {user} has no search named {search_name}")
            return

        for field, value in zip(fields, values):
            if field not in list(T.get_type_hints(firebase_data_types.Search).keys()):
                log.print_warn(f"Field {field} is not a valid search field")
                return

            search_item[field] = value  # type: ignore

        db_user["searches"]["items"][search_name] = search_item

        self._maybe_upload_db_cache_to_firestore(user, old_db_user, db_user)

    def clear_search_context(self, user: str, city: str) -> None:
        with self.database_cache_lock:
            if user not in self.database_cache:
                log.print_warn(f"User {user} not in database cache")
                return
            census_details = safe_get(
                dict(self.database_cache[user]), "searchContext.censusDetails".split("."), {}
            )
            old_db_user = copy.deepcopy(self.database_cache[user])
            db_user = copy.deepcopy(self.database_cache[user])

            log.print_bright(f"Clearing search context for {user} in {city}")

            db_user["searchContext"] = firebase_data_types.NULL_USER["searchContext"]
            # preserve the census details
            db_user["searchContext"]["censusDetails"] = census_details

            self._maybe_upload_db_cache_to_firestore(user, old_db_user, db_user)

    def get_search_contexts(self) -> T.List[too_good_to_go_data_types.SearchContext]:
        search_contexts = []
        with self.database_cache_lock:
            for user, info in self.database_cache.items():
                context = safe_get(dict(info), "searchContext".split("."))
                if context is None or not context:
                    continue

                try:
                    search_context = too_good_to_go_data_types.SearchContext(
                        user=user,
                        city=context["city"],
                        city_center=(
                            context["cityCenter"]["latitude"],
                            context["cityCenter"]["longitude"],
                        ),
                        radius_miles=context["radiusMiles"],
                        num_squares=context["numberOfSquares"],
                        grid_width_meters=context["gridWidthMeters"],
                        trigger_search=context["triggerSearch"],
                        send_email=context["autoUpload"],
                        max_cost_per_city=context["maxCostPerCity"],
                        cost_per_square=context["costPerSquare"],
                        census_year=context["censusDetails"]["year"],
                        census_source_path=context["censusDetails"]["sourcePath"],
                        census_codes=list(context["censusDetails"]["fields"].keys()),
                        time_zone=safe_get(
                            dict(info), "preferences.searchTimeZone.value".split("."), ""
                        ),
                        start_index=context["gridStartIndex"],
                    )
                    search_contexts.append(search_context)
                except KeyError as exception:
                    log.print_warn(f"Could not find key {exception} in search context for {user}")

        return search_contexts

    def get_searches(self, verbose: bool = True) -> T.Dict[str, too_good_to_go_data_types.Search]:
        searches = {}
        if verbose:
            log.print_bold("Getting searches from database cache")
        with self.database_cache_lock:
            for user, info in self.database_cache.items():
                search_items = safe_get(dict(info), "searches.items".split("."), {})
                if not search_items:
                    continue

                time_zone = safe_get(dict(info), "preferences.searchTimeZone.value".split("."), "")
                delete_data_on_download = safe_get(
                    dict(info), "preferences.deleteDataOnDownload".split("."), False
                )
                hour_start = safe_get(dict(info), "searches.collectionTimeStart".split("."), 0)
                hour_interval = safe_get(
                    dict(info), "searches.hoursBetweenCollection".split("."), 0
                )

                if hour_interval == 0 or time_zone == "":
                    log.print_warn(f"Skipping {user} because hour_interval is 0")
                    continue

                for item_name, item in search_items.items():
                    region = item.get("region", {})
                    if not region:
                        continue
                    if verbose:
                        log.print_ok_blue_arrow(
                            f"Adding search: {item_name}, for {user}: {json.dumps(region)}"
                        )
                    search_region = too_good_to_go_data_types.Region(
                        latitude=region.get("latitude", 0.0),
                        longitude=region.get("longitude", 0.0),
                        radius=region.get("radius", 0),
                    )

                    search = too_good_to_go_data_types.Search(
                        user=user,
                        search_name=item_name,
                        region=search_region,
                        hour_start=hour_start,
                        hour_interval=hour_interval,
                        time_zone=time_zone,
                        last_search_time=item.get("lastSearchTime", 0),
                        last_download_time=item.get("lastDownloadTime", 0),
                        email_data=item.get("sendEmail", False),
                        upload_only=item.get("uploadOnly", False),
                        erase_data=item.get("eraseData", False),
                        num_results=item.get("numResults", 0),
                        delete_data_on_download=delete_data_on_download,
                        store_raw_data=safe_get(
                            dict(info), "preferences.storeRawData".split("."), False
                        ),
                    )

                    search_hash = self.get_uuid(search, self.verbose)
                    searches[search_hash] = search

        return searches
