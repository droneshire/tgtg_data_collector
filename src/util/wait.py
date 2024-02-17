import time

from click_spinner import spinner


def wait(wait_time) -> None:
    with spinner():
        time.sleep(wait_time)
