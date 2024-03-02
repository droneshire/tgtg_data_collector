import enum
import logging
import os
import shutil
import sys
import tarfile
import time
import typing as T

from util.file_util import make_sure_path_exists

_ALWAYS_PRINT = False


class Colors(enum.Enum):
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[31m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class Prefixes(enum.Enum):
    ARROW = chr(10236)


class MultiHandler(logging.Handler):
    """
    Create a special logger that logs to per-thread-name files
    I'm not confident the locking strategy here is correct, I think this is
    a global lock and it'd be OK to just have a per-thread or per-file lock.
    """

    def __init__(self, dirname: str, block_list_prefixes: T.Optional[T.List[str]] = None):
        super().__init__()
        self.files: T.Dict[str, T.TextIO] = {}
        self.dirname = dirname
        self.block_list_prefixes = block_list_prefixes if block_list_prefixes else []
        if not os.access(dirname, os.W_OK):
            raise OSError(f"Directory {dirname} not writeable")

    def flush(self) -> None:
        self.acquire()
        try:
            for file_descriptor in self.files.values():
                file_descriptor.flush()
        finally:
            self.release()

    def _get_or_open(self, key: str) -> T.Optional[T.TextIO]:
        "Get the file pointer for the given key, or else open the file"
        self.acquire()
        file_descriptor: T.Optional[T.TextIO] = None
        try:
            if key in self.files:
                return self.files[key]

            file_name = (
                f"{key}.log".replace("/", "_").replace(" ", "_").replace("(", "").replace(")", "")
            )
            file_name = file_name.lower()
            file_descriptor = open(  # pylint: disable=consider-using-with
                os.path.join(self.dirname, file_name),
                "a",
                encoding="utf-8",
            )
            self.files[key] = file_descriptor
            return file_descriptor
        finally:
            self.release()

        return file_descriptor

    def emit(self, record: logging.LogRecord) -> None:
        # No lock here; following code for StreamHandler and FileHandler
        try:
            name = record.threadName
            if name is None:
                return
            if any(n for n in self.block_list_prefixes if name.startswith(n)):
                return
            file_descriptor = self._get_or_open(name)
            if file_descriptor is None:
                raise ValueError(f"Could not open file for {name}")
            msg = self.format(record)
            file_descriptor.write(f"{msg}\n")
        except (KeyboardInterrupt, SystemExit):
            raise
        except:  # pylint: disable=bare-except
            self.handleError(record)


def clean_log_dir(log_dir: str) -> None:
    """Clean the log directory by removing all files and directories in the directory."""
    if not os.path.exists(log_dir):
        return
    for filename in os.listdir(log_dir):
        file_path = os.path.join(log_dir, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as exception_obj:  # pylint: disable=broad-except
            print(f"Failed to delete {file_path}. Reason: {exception_obj}")


def is_color_supported() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def get_logging_dir(name: str, create_if_not_exist: bool = True) -> str:
    util_dir = os.path.dirname(os.path.realpath(__file__))
    src_dir = os.path.dirname(util_dir)
    log_dir = os.path.join(os.path.dirname(src_dir), "logs", name)

    if create_if_not_exist:
        make_sure_path_exists(log_dir)
    return log_dir


def get_log_dir_name(log_dir: str) -> str:
    current_log_dir_name = time.strftime("%Y_%m_%d__%H_%M_%S", time.localtime(time.time()))
    updated_log_dir = os.path.join(log_dir, "logs", current_log_dir_name)
    make_sure_path_exists(path=updated_log_dir)
    return updated_log_dir


def setup(log_dir: str, log_level: str, main_thread_name: str) -> None:
    if not os.path.isdir(log_dir):
        os.mkdir(log_dir)

    new_log_dir = get_log_dir_name(log_dir)

    setup_log(log_level, new_log_dir, main_thread_name)

    logging.getLogger().addHandler(
        MultiHandler(
            new_log_dir,
            ["ThreadPool", "MainThread"],
        )
    )


def make_formatter_printer(
    color: str,
    log_level: int = logging.INFO,
    prefix: str = "",
    return_formatter: bool = False,
) -> T.Callable:
    logger = logging.getLogger(__name__)

    def formatter(message, *args, **kwargs):
        message = str(message)

        if args or kwargs:
            formatted_text = message.format(*args, **kwargs)
        else:
            formatted_text = message

        if prefix and sys.platform.lower() == "linux":
            formatted_text = prefix + "\t" + formatted_text

        if is_color_supported():
            if sys.stdout.encoding is not None:
                return (
                    str(color + formatted_text + Colors.ENDC.value)
                    .encode("utf-8")
                    .decode(sys.stdout.encoding, errors="ignore")
                )
            return str(color + formatted_text + Colors.ENDC.value)

        if sys.stdout.encoding is not None:
            return formatted_text.encode("utf-8").decode(sys.stdout.encoding, errors="ignore")

        return formatted_text

    def printer(message, *args, **kwargs):
        is_logger_in_use = logging.getLogger().hasHandlers()
        if _ALWAYS_PRINT:
            print(formatter(message, *args, **kwargs))
        elif not is_logger_in_use or logging.getLogger().isEnabledFor(log_level):
            print(formatter(message, *args, **kwargs))

        if is_logger_in_use:
            if log_level == logging.DEBUG:
                logger.debug(message)
            elif log_level == logging.WARNING:
                logger.warning(message)
            elif log_level == logging.ERROR:
                logger.error(message)
            elif log_level == logging.INFO:
                logger.info(message)
            elif log_level == logging.CRITICAL:
                logger.critical(message)

        sys.stdout.flush()

        # Flush the logger handlers
        for handler in logger.handlers:
            handler.flush()

    if return_formatter:
        return formatter

    return printer


def tar_logs(log_dir: str, tarname: str, remove_after: bool = False, max_tars: int = 5) -> None:
    """Tar the logs directory to a file called logs.tar.gz"""
    if not tarname.endswith(".tar.gz"):
        tarname += ".tar.gz"

    # if there are other tar names, increment the name by 1
    tar_index = 1
    while os.path.exists(os.path.join(log_dir, tarname)):
        tarname = tarname.replace(".tar.gz", "")
        tarname = tarname.split(".")[0]
        tarname = tarname + f".{tar_index}.tar.gz"
        tar_index += 1
        if tar_index > max_tars:
            break

    logs_dir = os.path.join(log_dir, "logs")
    make_sure_path_exists(logs_dir)
    tar_name = os.path.join(log_dir, tarname)
    with tarfile.open(tar_name, "w:gz") as tar:
        tar.add(logs_dir, arcname="logs")

    if remove_after:
        shutil.rmtree(logs_dir)


def setup_log(log_level: str, log_dir: str, id_string: str, always_print: bool = False) -> None:
    global _ALWAYS_PRINT  # pylint: disable=global-statement
    _ALWAYS_PRINT = always_print

    if log_level == "NONE":
        return

    log_file = os.path.join(log_dir, f"{id_string}.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.getLevelName(log_level),
        format="[%(levelname)s][%(asctime)s][%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filemode="w",
    )


print_ok_blue = make_formatter_printer(Colors.OKBLUE.value, log_level=logging.INFO)
print_ok_blue_arrow = make_formatter_printer(
    Colors.OKBLUE.value, prefix=Prefixes.ARROW.value, log_level=logging.INFO
)
print_ok = make_formatter_printer(Colors.OKGREEN.value, log_level=logging.CRITICAL)
print_ok_arrow = make_formatter_printer(
    Colors.OKGREEN.value, prefix=Prefixes.ARROW.value, log_level=logging.CRITICAL
)
print_bright = make_formatter_printer(Colors.OKCYAN.value, log_level=logging.WARNING)
print_warn = make_formatter_printer(Colors.WARNING.value, log_level=logging.WARNING)
print_fail = make_formatter_printer(Colors.FAIL.value, log_level=logging.CRITICAL)
print_fail_arrow = make_formatter_printer(
    Colors.FAIL.value, prefix=Prefixes.ARROW.value, log_level=logging.CRITICAL
)
print_bold = make_formatter_printer(Colors.BOLD.value, log_level=logging.CRITICAL)
print_normal = make_formatter_printer(Colors.ENDC.value, log_level=logging.DEBUG)
print_normal_arrow = make_formatter_printer(
    Colors.ENDC.value, prefix=Prefixes.ARROW.value, log_level=logging.DEBUG
)


format_ok_blue = make_formatter_printer(Colors.OKBLUE.value, return_formatter=True)
format_ok = make_formatter_printer(Colors.OKGREEN.value, return_formatter=True)
format_bright = make_formatter_printer(Colors.OKCYAN.value, return_formatter=True)
format_warn = make_formatter_printer(Colors.WARNING.value, return_formatter=True)
format_fail = make_formatter_printer(Colors.FAIL.value, return_formatter=True)
format_bold = make_formatter_printer(Colors.BOLD.value, return_formatter=True)
format_normal = make_formatter_printer(Colors.ENDC.value, return_formatter=True)
format_normal_arrow = make_formatter_printer(
    Colors.ENDC.value, prefix=Prefixes.ARROW.value, return_formatter=True
)
format_ok_arrow = make_formatter_printer(
    Colors.OKGREEN.value, prefix=Prefixes.ARROW.value, return_formatter=True
)
format_ok_blue_arrow = make_formatter_printer(
    Colors.OKBLUE.value, prefix=Prefixes.ARROW.value, return_formatter=True
)
format_fail_arrow = make_formatter_printer(
    Colors.FAIL.value, prefix=Prefixes.ARROW.value, return_formatter=True
)
