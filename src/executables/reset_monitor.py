"""
Script that monitors the firestore database
under the "admin.health_monitor.reset" field path
for a boolean value of True. If the value is True,
then the script will reset the server by killing
any outstanding bot processes and restarting them.
"""
import argparse
import os
import subprocess
import sys

import dotenv

from constants import PROJECT_NAME
from firebase.admin import FirebaseAdmin
from util import log, wait

TIME_BETWEEN_CHECKS = 5


def try_to_kill_process() -> None:
    pidfile = os.environ.get("BOT_PIDFILE", "monitor_inventory.pid")
    try:
        with open(pidfile, "r", encoding="utf-8") as infile:
            pid = int(infile.read())
            log.print_fail_arrow(f"Killing process with pid {pid}...")
            os.kill(pid, 9)
    except:  # pylint: disable=bare-except
        log.print_normal("No process to kill.")


def is_process_killed() -> bool:
    pidfile = os.environ.get("BOT_PIDFILE", "monitor_inventory.pid")
    try:
        with open(pidfile, "r", encoding="utf-8") as infile:
            pid = int(infile.read())
            if not os.path.exists(f"/proc/{pid}"):
                log.print_fail(f"Process with pid {pid} is killed.")
                return True
            return False
    except:  # pylint: disable=bare-except
        log.print_fail("No process running.")
        return True


def reset_server() -> None:
    """Reset the server by killing all bot processes and restarting them."""
    log.print_fail("Resetting server...")
    try_to_kill_process()
    bot_start_command = os.environ.get("BOT_START_COMMAND", "")

    if not bot_start_command:
        log.print_fail_arrow("BOT_START_COMMAND not set in .env file.")
        sys.exit(1)

    # kinda sketchy, as we can execute arb code here from the `.env` file...
    subprocess.call(bot_start_command, shell=True)
    log.print_ok_arrow("Server reset complete.")


def main() -> None:
    dotenv.load_dotenv(".env")

    parser = argparse.ArgumentParser(description=__doc__)

    log_dir = log.get_logging_dir(PROJECT_NAME)
    parser.add_argument("--log-dir", default=log_dir)

    pidfile = os.environ.get("RESET_PIDFILE", "reset_server.pid")

    with open(pidfile, "w", encoding="utf-8") as outfile:
        outfile.write(str(os.getpid()))

    credentials_file = os.environ.get("FIREBASE_CREDENTIALS_FILE", "")
    firebase_server: FirebaseAdmin = FirebaseAdmin(credentials_file=credentials_file)

    try:
        while True:
            if firebase_server.is_reset:
                log.print_bright("Reset signal detected.")
                log.clean_log_dir(os.path.join(log_dir, "logs"))
                reset_server()
                firebase_server.set_reset(reset=False)
                log.print_ok_arrow("Bot reset complete.")
            elif is_process_killed():
                reset_server()
                log.print_ok_arrow("Bot reset complete.")
            firebase_server.refresh()
            wait.wait(TIME_BETWEEN_CHECKS)
    except KeyboardInterrupt:
        log.print_fail_arrow("Keyboard interrupt detected.")
    finally:
        os.remove(path=pidfile)


if __name__ == "__main__":
    main()
