from __future__ import annotations

from app.db import DB
from app.web import create_app


def main() -> None:
    DB.initialize()
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
