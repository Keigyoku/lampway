"""`python -m lampway_server` / `lampway-server`: serve on LAMPWAY_HOST:LAMPWAY_PORT."""

import logging
import os

import uvicorn

from .app import create_app
from .config import Settings


def main():
    logging.basicConfig(level=os.environ.get("LAMPWAY_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    app = create_app(settings)
    logging.getLogger("lampway").info(
        "serving on http://%s:%d (provider=%s, user=%s, password %s)", settings.host, settings.port,
        settings.provider, settings.user_email, "set" if settings.user_password else "NOT set",
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
