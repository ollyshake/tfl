import argparse
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import CollectionRun

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def collect_status(client: httpx.Client) -> bool:
    endpoint = "/Line/victoria/Status"
    key = os.getenv("TFL_APP_KEY")
    params = {"app_key": key} if key else {}

    payload = None
    http_status = None
    error = None

    try:
        response = client.get(endpoint, params=params)
        http_status = response.status_code
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("Expected a list of line statuses")

    except (httpx.HTTPError, ValueError) as exc:
        payload = None
        # Avoid logging the request URL, which may contain the API key.
        error = (
            f"HTTP {http_status}"
            if isinstance(exc, httpx.HTTPStatusError)
            else type(exc).__name__
        )

    outcome = "error" if error else "success"

    with SessionLocal.begin() as session:
        session.add(
            CollectionRun(
                endpoint=endpoint,
                target="victoria",
                collected_at=datetime.now(timezone.utc),
                outcome=outcome,
                http_status=http_status,
                error=error,
                raw_response=payload,
            )
        )
        # The session context commits on success and rolls back on error.

    logger.info("Victoria status: %s%s", outcome, f" ({error})" if error else "")
    return error is None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    with httpx.Client(
        base_url=os.getenv("TFL_BASE_URL", "https://api.tfl.gov.uk"),
        timeout=10.0,
    ) as client:
        while True:
            started = time.monotonic()

            try:
                success = collect_status(client)
            except SQLAlchemyError as exc:
                logger.error("Database write failed (%s)", type(exc).__name__)
                success = False

            if not args.loop:
                raise SystemExit(0 if success else 1)

            time.sleep(max(0, 60 - (time.monotonic() - started)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
