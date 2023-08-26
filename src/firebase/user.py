import copy
import enum
import json
import threading
import time
import typing as T

import deepdiff
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1.collection import CollectionReference
from google.cloud.firestore_v1.watch import DocumentChange

from firebase import data_types as firebase_data_types
from too_good_to_go import data_types as too_good_to_go_data_types
from util import log
from util.dict_util import check_dict_keys_recursive, patch_missing_keys_recursive, safe_get


class Changes(enum.Enum):
    ADDED = 1
    MODIFIED = 2
    REMOVED = 3


class FirebaseUser:
    HEALTH_PING_TIME = 60 * 30

    def __init__(self, credentials_file: str, verbose: bool = False) -> None:
        if not firebase_admin._apps:  # pylint: disable=protected-access
            auth = credentials.Certificate(credentials_file)
            firebase_admin.initialize_app(auth)
        self.database = firestore.client()
        self.verbose = verbose

        self.user_ref: CollectionReference = self.database.collection("user")
        self.admin_ref: CollectionReference = self.database.collection("admin")

        self.users_watcher = self.user_ref.on_snapshot(self._collection_snapshot_handler)

        self.database_cache: T.Dict[str, firebase_data_types.User] = {}

        self.callback_done: threading.Event = threading.Event()
        self.database_cache_lock: threading.Lock = threading.Lock()

        self.last_health_ping: T.Optional[float] = None

    def _delete_user(self, name: str) -> None:
        with self.database_cache_lock:
            if name in self.database_cache:
                del self.database_cache[name]
        log.print_warn(f"Deleting user {name} from cache")

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
            safe_get(
                dict(self.database_cache[doc_id]),
                "preferences.notifications.email.email".split("."),
                "",
            )
            phone_number = safe_get(
                dict(self.database_cache[doc_id]),
                "preferences.notifications.sms.phoneNumber".split("."),
                "",
            )
            if phone_number and not phone_number.startswith("+1"):
                phone_number = "+1" + phone_number

            if change.type.name == Changes.ADDED.name:
                log.print_ok_blue(f"Added document: {doc_id}")
            elif change.type.name == Changes.MODIFIED.name:
                log.print_ok_blue(f"Modified document: {doc_id}")
            elif change.type.name == Changes.REMOVED.name:
                log.print_ok_blue(f"Removed document: {doc_id}")
                self._delete_user(doc_id)

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

        diff = deepdiff.DeepDiff(
            old_db_user,
            db_user,
            ignore_order=True,
        )
        if not diff:
            return

        log.print_normal(
            f"Updated client {user} in database:\n{diff.to_json(indent=4, sort_keys=True)}"
        )

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

    def _get_users(self) -> T.Dict[str, firebase_data_types.User]:
        with self.database_cache_lock:
            return copy.deepcopy(self.database_cache)

    def get_searches(self) -> T.List[too_good_to_go_data_types.Search]:
        searches = []
        with self.database_cache_lock:
            for user, info in self.database_cache.items():
                search_items = info.get("searches", {}).get("items", [])
                if not search_items:
                    continue

                for item in search_items:
                    region = item.get("region", {})
                    if not region:
                        continue
                    log.print_ok_blue_arrow(f"Adding search for {user}: {json.dumps(region)}")
                    search_region = too_good_to_go_data_types.Region(
                        lattitude=region.get("lattitude", 0.0),
                        longitude=region.get("longitude", 0.0),
                        radius=region.get("radius", 0),
                    )
                    searches.append(
                        too_good_to_go_data_types.Search(user=user, region=search_region)
                    )

        return searches
