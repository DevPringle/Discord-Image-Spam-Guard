# Discord Image Spam Guard

Discord Image Spam Guard is a self-hosted Discord bot with a local dashboard for catching repeated spam images.

You run it on your own PC or server.
You upload the spam images you want blocked.
The bot watches new image attachments and reacts when one matches.

## What it does

- watches new image attachments in channels the bot can see
- compares them against your saved reference images
- supports exact file matches with SHA-256
- supports near matches with pHash, dHash, and wHash
- can delete the message on match
- can log the hit to a mod-log channel
- can timeout, kick, ban, or do nothing after a match
- lets you change settings from a local dashboard
- lets you drag and drop or batch upload reference images
- lets you edit image names and notes after upload
- includes bot power and restart controls in the dashboard
- stores runtime settings locally so the app and bot can start back up cleanly later

## What it does not do

- it does not scan old messages from before the bot was added
- it is not a hosted public invite bot
- it does not require Docker or a cloud setup

## Before you start

You need:
- Python 3.11 or newer
- a Discord application with a bot token
- the bot invited to your server
- Message Content Intent enabled in the Discord developer portal
- Server Members Intent enabled in the Discord developer portal

Recommended bot permissions:
- View Channels
- Read Message History
- Send Messages
- Embed Links
- Manage Messages
- Moderate Members
- Kick Members
- Ban Members

## Fast setup on Windows

If you want the easiest route:

1. Extract the project folder anywhere you want.
2. Double-click `setup_windows.bat`.
3. Wait for setup to finish. This may take a few minutes.
4. Double-click `start_windows.bat`.
5. Your browser will open the dashboard.
6. Finish the first-run setup page.
7. Once setup is saved, the bot can be started from the dashboard or by running `start_windows.bat` again.

What the scripts do:
- `setup_windows.bat` creates `.venv`, installs packages, and creates `.env` if needed
- `start_windows.bat` starts the dashboard and opens it in your browser
- `rebuild_windows.bat` rebuilds `.venv` if your environment gets weird

## First run

The first time the dashboard opens, you will be asked for:
- your Discord bot token
- your Discord server ID
- a dashboard password
- an optional mod log channel ID
- a starting preset

When you save setup:
- the values are stored locally for the app to use later
- the same runtime values are also written to your local `.env`

## Dashboard

By default, the dashboard runs at:

`http://localhost:5000`

Login:
- username: `admin`
- password: the dashboard password you chose during setup

The dashboard can also be opened from another device on your local network if you use your machine's LAN IP and your firewall allows it.

## Basic use

1. Start the dashboard.
2. Log in.
3. Open **Reference Images**.
4. Drag in or select one or more spam images.
5. Go to **Settings** and choose your match behavior.
6. Start the bot from the dashboard if it is not already running.
7. Test with one of the saved images.

## Manual start

If you want to run things by hand, use the virtual environment that setup created.

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python run_web.py
python run_bot.py
```

If you run `py run_bot.py` outside the virtual environment, it may fail because the required packages are installed into `.venv`, not your system Python.

## Runtime settings

The setup page and settings page can update:
- bot token
- server ID
- dashboard password
- mod log channel ID

Those values are stored locally and also written into `.env` so future launches are consistent.

## Project layout

```text
discord_image_spam_guard/
├── .env.example
├── .gitignore
├── README.md
├── LICENSE
├── rebuild_windows.bat
├── requirements.txt
├── run_bot.py
├── run_web.py
├── setup_windows.bat
├── start_windows.bat
│
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── discord_bot.py
│   ├── image_matching.py
│   ├── policy.py
│   ├── web.py
│   │
│   ├── services/
│   ├── static/
│   └── templates/
│
├── data/
│   └── reference_images/
│
├── logs/
```

## Troubleshooting

### Bot says privileged intents are required
Turn on Message Content Intent and Server Members Intent in the Discord developer portal.

### Bot says the token is invalid
Double-check the token in setup or settings and save it again.

### Bot does nothing when a spam image is posted
Check these:
- the image is an actual attachment, not just a link
- you uploaded reference images
- the bot has permission in that channel
- your threshold is not too loose or too strict

### Timeout, kick, or ban fails
The bot role is probably below the user it tried to act on.

### The dashboard looks empty
That is normal on a fresh install. Upload reference images first.

## Links

GitHub:
https://github.com/DevPringle/Discord-Image-Spam-Guard

Support:
https://buymeacoffee.com/devpringle
