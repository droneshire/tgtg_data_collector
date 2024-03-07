import os
import tarfile
import typing as T
import zipfile


def make_sure_path_exists(path: str, ignore_extension: bool = False) -> None:
    path = os.path.dirname(path) if not ignore_extension and len(path.split(".")) > 1 else path

    root = "/"
    dirs = path.split("/")[1:]
    for directory in dirs:
        section = os.path.join(root, directory)
        root = section
        if not os.path.isdir(section) and not os.path.isfile(section):
            os.mkdir(section)


def create_tar_archive(files: T.List[str], tar_name: str, use_base_name: bool = False):
    """
    Creates a tar archive from a list of files.

    :param files: A list of file paths to include in the archive.
    :param tar_name: The name of the tar archive to create.
    """
    with (
        tarfile.open(tar_name, "w:gz") if tar_name.endswith(".gz") else tarfile.open(tar_name, "w")
    ) as tar:
        for file in files:
            # Add file to tar archive, arcname is the name which will be stored in the archive
            # arcname=file will store the files with the same directory structure as on disk
            # to store files in the root, pass arcname=os.path.basename(file)
            tar.add(file, arcname=os.path.basename(file) if use_base_name else file)


def create_zip_archive(files: T.List[str], zip_name: str):
    """
    Creates a zip archive from a list of files.

    :param files: A list of file paths to include in the archive.
    :param zip_name: The name of the zip archive to create.
    """

    with zipfile.ZipFile(zip_name, "w") as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))
