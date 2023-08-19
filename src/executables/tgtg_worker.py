import argparse
import os
import re

import dotenv

from constants import PROJECT_NAME
from parse_args import parse_args
from util import log, wait


def run_loop(args: argparse.Namespace) -> None:
    wait.wait(5)


def main() -> None:
    dotenv.load_dotenv(".env")
    args = parse_args()

    log.setup_log(args.log_level, args.log_dir, PROJECT_NAME)
    log.print_ok_blue("Starting TGTG data collection client...")

    run_loop(args)


if __name__ == "__main__":
    main()
