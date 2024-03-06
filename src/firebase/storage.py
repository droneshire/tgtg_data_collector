"""
Firebase Storage class to handle file uploads and deletions
"""

import datetime
import os
import time

import firebase_admin
from firebase_admin import credentials, storage

from util import log


class FirebaseStorage:
    EXP_TIME_MINUTES = 60 * 24 * 7

    def __init__(self, credentials_file: str, storage_bucket: str, verbose: bool = False) -> None:
        if not firebase_admin._apps:  # pylint: disable=protected-access
            auth = credentials.Certificate(credentials_file)
            firebase_admin.initialize_app(auth, {"storageBucket": storage_bucket})
        self.bucket = storage.bucket()
        self.storage_bucket = storage_bucket
        self.verbose = verbose

    def _get_blob_storage_path(self, user: str, file_path: str, num_results: int) -> str:
        file_name = os.path.basename(file_path)
        file_name_stripped, extension = os.path.splitext(file_name)
        blob_base_path = self._get_base_blob_storage_path(user, file_name_stripped)
        date_string = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"{blob_base_path}/{num_results}__{date_string}{extension}"

    def _get_base_blob_storage_path(self, user: str, identifier: str) -> str:
        return f"{user}/{identifier}"

    def delete_search_uploads(self, user: str, identifier: str) -> None:
        storage_path = self._get_base_blob_storage_path(user, identifier)
        for blob in self.bucket.list_blobs(prefix=storage_path):
            blob.reload()
            time_created = blob.time_created

            if time_created and time.time() - time_created.timestamp() < self.EXP_TIME_MINUTES * 60:
                continue

            log.print_warn(f"Deleting upload {blob.name} for {user}")
            blob.delete()

    def delete_all_uploads(self, user: str) -> None:
        log.print_warn(f"Deleting all uploads for {user}")
        for blob in self.bucket.list_blobs(prefix=f"{user}/"):
            blob.delete()

    def upload_file_and_get_url(
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
        log.print_ok_arrow(f"Download URL\n\n{download_url}")
        return str(download_url)
