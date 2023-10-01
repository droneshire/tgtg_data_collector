import copy
import datetime
import enum
import hashlib
import json
import os
import threading
import time
import typing as T

import deepdiff
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1.collection import CollectionReference
from google.cloud.firestore_v1.watch import DocumentChange

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
    EXP_TIME_MINUTES = 60 * 24 * 7

    def __init__(
        self,
        credentials_file: str,
        storage_bucket: str,
        send_email_callback: T.Optional[SendEmailCallbackType] = None,
        verbose: bool = False,
    ) -> None:
        if not firebase_admin._apps:  # pylint: disable=protected-access
            auth = credentials.Certificate(credentials_file)
            firebase_admin.initialize_app(auth, {"storageBucket": storage_bucket})
        self.database = firestore.client()
        self.bucket = storage.bucket()
        self.verbose = verbose

        self.user_ref: CollectionReference = self.database.collection("user")
        self.admin_ref: CollectionReference = self.database.collection("admin")

        self.users_watcher = self.user_ref.on_snapshot(self._collection_snapshot_handler)

        self.database_cache: T.Dict[str, firebase_data_types.User] = {}

        self.callback_done: threading.Event = threading.Event()
        self.database_cache_lock: threading.RLock = threading.RLock()

        self.last_health_ping: T.Optional[float] = None

        self._send_email_callback: T.Optional[SendEmailCallbackType] = send_email_callback

    def _delete_user(self, name: str) -> None:
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
            if search_item.get("sendEmail", False) and self._send_email_callback is not None:
                self._send_email_callback(search_hash, search_item)
        print("done")
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

    def delete_search_uploads(self, user: str, uuid: str) -> None:
        storage_path = self._get_base_blob_storage_path(user, uuid)
        for blob in self.bucket.list_blobs(prefix=storage_path):
            log.print_warn(f"Deleting upload {blob.name} for {user}")
            blob.delete()

    def delete_all_uploads(self, user: str) -> None:
        log.print_warn(f"Deleting all uploads for {user}")
        for blob in self.bucket.list_blobs(prefix=f"{user}/"):
            blob.delete()

    def _get_base_blob_storage_path(self, user: str, uuid: str) -> str:
        return f"{user}/{uuid}"

    def _get_blob_storage_path(self, user: str, file_path: str, num_results: int) -> str:
        file_name = os.path.basename(file_path)
        uuid, extension = os.path.splitext(file_name)
        blob_base_path = self._get_base_blob_storage_path(user, uuid)
        return f"{blob_base_path}/{num_results}{extension}"

    def get_upload_file_url(
        self, user: str, file_path: str, num_results: int, verbose: bool = False
    ) -> str:
        mimetype = "text/csv" if file_path.endswith(".csv") else "application/json"

        storage_path = self._get_blob_storage_path(user, file_path, num_results)
        blob = self.bucket.blob(storage_path)
        blob.content_type = mimetype
        blob.upload_from_filename(
            file_path,
            content_type=mimetype,
            predefined_acl="publicRead",
        )

        if verbose:
            log.print_bright(f"Uploading {file_path} to {storage_path} on firebase")

        download_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=self.EXP_TIME_MINUTES),
            method="GET",
        )
        log.print_ok_arrow(f"Download URL {download_url}")
        return str(download_url)

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
        self, user: str, search_name: str, last_search_time: float, new_results: int
    ) -> None:
        search_item = self._get_search_item(search_name)

        if search_item is None:
            log.print_warn(f"User {user} has no search named {search_name}")
            return

        previous_count = search_item.get("numResults", 0)
        new_count = previous_count + new_results

        self._update_search_fields(
            user, search_name, ["lastSearchTime", "numResults"], [last_search_time, new_count]
        )

    def reset_search_count(self, user: str, search_name: str) -> None:
        self._update_search_fields(user, search_name, ["numResults"], [0])

    def update_search_email(self, user: str, search_name: str) -> None:
        self._update_search_fields(
            user, search_name, ["sendEmail", "lastDownloadTime"], [False, time.time()]
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

    def get_searches(self, verbose: bool = True) -> T.Dict[str, too_good_to_go_data_types.Search]:
        searches = {}
        log.print_bold("Getting searches from database cache")
        with self.database_cache_lock:
            for user, info in self.database_cache.items():
                search_items = safe_get(dict(info), "searches.items".split("."), {})
                if not search_items:
                    continue

                time_zone = safe_get(dict(info), "preferences.searchTimeZone.value".split("."), "")
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
                        erase_data=item.get("eraseData", False),
                        num_results=item.get("numResults", 0),
                    )

                    search_hash = self.get_uuid(search, self.verbose)
                    searches[search_hash] = search

        return searches
