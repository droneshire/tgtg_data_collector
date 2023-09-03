# Too Good To Go Data Collector

[![Python application](https://github.com/droneshire/property_guru_upwork/actions/workflows/python-app.yml/badge.svg)](https://github.com/droneshire/property_guru_upwork/actions/workflows/python-app.yml)

Python backend to collect and analyze periodic data collected from Too Good To Go restaurant food waste site.

## Important Links

- [`tgtg-python`](https://github.com/ahivert/tgtg-python)
- [Too Good To Go](https://www.toogoodtogo.com/en-us)
- [Firebase Console](https://console.firebase.google.com/u/0/project/too-good-to-go-data-collect.web.app)
- [Hosted Website Frontend for Managing Settings](https://too-good-to-go-data-collect.web.app/login)

## Environment

An environment file (`.env`) should be located in the root directory and should contain the following items:

```
TGTG_DEFAULT_API_CREDENTIALS_FILE = "tgtg_credentials.json"
TGTG_DEFAULT_API_EMAIL=<REDACTED>

SENDER_EMAIL_ADDRESS=<REDACTED>
SENDER_EMAIL_PASSWORD=<REDACTED>

FIREBASE_CREDENTIALS_FILE="firebase_service_account.json"

BOT_PIDFILE="tgtg_worker.pid"
RESET_PIDFILE="reset_tgtg_worker.pid"
BOT_START_COMMAND='tmux send-keys -t tgtg-worker-bot:0.0 "tgtg_bot_dir; git pull; make run_worker" C-m'

```

The `SENDER_` address and passwords should be email token that is set up for a specific email address.

Instructions to do this in your google account:

1. Set up 2-step verification.
2. Go to your Google account, then Security, and then App passwords
3. Click Select app, then Other (custom name).
4. Give a name and click Generate.
5. Follow the instructions to enter the app password.
6. Click Done.
