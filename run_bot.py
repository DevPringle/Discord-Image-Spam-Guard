from __future__ import annotations

import logging

from app.db import DB
from app.discord_bot import create_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    DB.initialize()
    runtime_config = DB.get_effective_runtime_config()
    token = runtime_config["discord_bot_token"]
    if not token:
        raise SystemExit("Bot token is missing. Run the setup wizard or fill in .env first.")
    bot = create_bot()
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
