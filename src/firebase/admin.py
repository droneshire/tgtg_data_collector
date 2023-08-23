import time
import typing as T

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1.collection import CollectionReference
from google.cloud.firestore_v1.watch import DocumentChange

from util import log


class FirebaseAdmin:
    TIME_BETWEEN_WATCHER_UPDATE = 60 * 45

    def __init__(self, credentials_file: str):
        self.credentials_file = credentials_file
        self._is_reset = False
        self.time_between_watcher_update: T.Optional[float] = None

        if not firebase_admin._apps:  # pylint: disable=protected-access
            auth = credentials.Certificate(credentials_file)
            firebase_admin.initialize_app(auth)

        self.database = firestore.client()
        self.admin_ref: CollectionReference = self.database.collection("admin")
        self.admin_watcher = self.admin_ref.on_snapshot(self._collection_snapshot_handler)

    def set_reset(self, reset: bool = False) -> None:
        self.admin_ref.document("health_monitor").set({"reset": reset}, merge=True)

    def get_reset(self) -> bool:
        doc = self.admin_ref.document("health_monitor").get()
        doc_dict = doc.to_dict()
        if not doc_dict:
            return False
        return doc_dict.get("reset", False)

    def refresh(self) -> None:
        now = time.time()
        if (
            self.time_between_watcher_update
            and now - self.time_between_watcher_update < self.TIME_BETWEEN_WATCHER_UPDATE
        ):
            return

        self.time_between_watcher_update = now

        log.print_ok("\nUpdating watcher...")
        if self.admin_watcher:
            self.admin_watcher.unsubscribe()

        self.admin_watcher = self.admin_ref.on_snapshot(self._collection_snapshot_handler)

    @property
    def is_reset(self) -> bool:
        return self._is_reset

    @is_reset.setter
    def is_reset(self, reset: bool) -> None:
        self._is_reset = reset

    def _collection_snapshot_handler(
        self,
        collection_snapshot: T.List[DocumentSnapshot],
        changed_docs: T.List[DocumentChange],
        read_time: T.Any,
    ) -> None:
        # pylint: disable=unused-argument
        if len(collection_snapshot) == 0:
            return
        collection_dict = collection_snapshot[0].to_dict()
        if not collection_dict:
            return
        reset = collection_dict.get("reset", False)
        log.print_bright(f"\nCollection snapshot: {reset}")
        self.is_reset = reset
