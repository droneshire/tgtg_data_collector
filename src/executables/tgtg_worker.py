import argparse
import os
import re

import dotenv

from account_creator import AccountCreator
from config import PROJECT_NAME
from email_parser import EmailParser
from parse_args import parse_args
from util import log, wait


def is_valid_email(email: str) -> bool:
    regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
    return re.fullmatch(regex, email) is not None


def get_login_code_from_parser(email: str, creds_env: str, delete_after_find: bool = False) -> str:
    creds = os.environ.get(creds_env)

    code_from_address = os.environ.get("AVION_REWARDS_EMAIL_ADDRESS")
    code_subject = os.environ.get("AVION_REWARDS_EMAIL_SUBJECT")
    code_regex = os.environ.get("AVION_REWARDS_EMAIL_REGEX")

    if not creds:
        log.print_fail(
            "Missing Google Oath Credentials.\n"
            "Either use the --manual-input flag or set the "
            "GOOGLE_OATH_CREDENTIALS_FILE_MAIN and "
            "GOOGLE_OATH_CREDENTIALS_FILE_BACKUP environment variables."
        )
        raise ValueError("Missing Google Oath Credentials.")

    if not code_from_address or not code_subject or not code_regex:
        log.print_fail(
            "Missing environment variables.\n"
            "Set AVION_REWARDS_EMAIL_ADDRESS, AVION_REWARDS_EMAIL_SUBJECT, and "
            "AVION_REWARDS_EMAIL_BODY."
        )
        raise ValueError("Missing environment variables.")

    email_parser = EmailParser(email=email, credentials_path=creds)

    login_code = email_parser.wait_for_login_code(
        from_address=code_from_address,
        subject=code_subject,
        search_regex=code_regex,
        timeout=120.0,
        delete_after_find=delete_after_find,
    )

    return login_code


def run_loop(args: argparse.Namespace) -> None:
    creator = AccountCreator(args.email, args.backup_email, args.password)

    creator.init()

    emails = [e.strip() for e in os.environ.get("ACCOUNT_EMAILS", "").split(",")]

    if not emails:
        log.print_fail("Missing ACCOUNT_EMAILS environment variable.")
        raise ValueError("Missing ACCOUNT_EMAILS environment variable.")

    log.print_warn("Checking emails to create accounts for...")
    emails_to_use = []

    for email in emails:
        if is_valid_email(email):
            log.print_ok_blue_arrow(f"{email} \U00002705")
            emails_to_use.append(email)
        else:
            log.print_fail_arrow(f"{email} \U0000274C")

    for email in emails_to_use:
        creator.start_new_account(email)

        wait.wait(10)

        if args.manual_input:
            login_code = input("Enter email login code: ")
        else:
            login_code = get_login_code_from_parser(
                args.email,
                "GOOGLE_OATH_CREDENTIALS_FILE_MAIN",
                delete_after_find=not args.save_after_read,
            )

        creator.input_login_code(login_code)

        if args.manual_input:
            backup_login_code = input("Enter backup email login code: ")
        else:
            backup_login_code = get_login_code_from_parser(
                args.backup_email,
                "GOOGLE_OATH_CREDENTIALS_FILE_BACKUP",
                delete_after_find=not args.save_after_read,
            )

        creator.input_backup_login_code(backup_login_code)

    wait.wait(5)

    if args.close_on_exit:
        creator.close()


def main() -> None:
    dotenv.load_dotenv(".env")
    args = parse_args()

    log.setup_log(args.log_level, args.log_dir, PROJECT_NAME)
    log.print_ok_blue("Creating new Avion Account...")

    run_loop(args)


if __name__ == "__main__":
    main()
