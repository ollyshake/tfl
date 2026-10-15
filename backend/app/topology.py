import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import CollectionRun, Line, LineStation, Station


logger = logging.getLogger(__name__)
LINE_ID = "victoria"
DIRECTIONS = ("inbound", "outbound")


@dataclass
class ParsedTopology:
    line_name: str
    stations: dict[str, dict[str, Any]]
    line_stations: list[dict[str, Any]]


def required_text(value: dict[str, Any], field: str) -> str:
    text_value = value.get(field)
    if not isinstance(text_value, str) or not text_value.strip():
        raise ValueError(f"Missing or invalid {field}")
    return text_value.strip()


def coordinate(value: Any, field: str, limit: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Missing or invalid {field}")
    number = float(value)
    if not math.isfinite(number) or not -limit <= number <= limit:
        raise ValueError(f"Invalid {field} range")
    return number


def parse_topology(payload: Any, direction: str) -> ParsedTopology:
    """Validate the entire response before changing any existing route rows."""
    if not isinstance(payload, dict):
        raise ValueError("Expected a route sequence object")
    if payload.get("lineId") != LINE_ID:
        raise ValueError("Response is not for the Victoria line")
    if required_text(payload, "direction").lower() != direction:
        raise ValueError("Response direction does not match the request")
    line_name = required_text(payload, "lineName")

    sequences = payload.get("stopPointSequences")
    if not isinstance(sequences, list) or not sequences:
        raise ValueError("Expected non-empty stopPointSequences")

    # Top-level station entries can supply metadata omitted from sequence stops.
    station_metadata = payload.get("stations", [])
    if not isinstance(station_metadata, list):
        raise ValueError("Expected a stations list")
    known_stations = {}
    for station in station_metadata:
        if not isinstance(station, dict):
            raise ValueError("Expected a station object")
        known_stations[required_text(station, "id")] = station

    stations = {}
    line_stations = []
    for sequence_number, sequence in enumerate(sequences, start=1):
        if not isinstance(sequence, dict):
            raise ValueError("Expected a stop sequence object")
        stops = sequence.get("stopPoint")
        if not isinstance(stops, list) or not stops:
            raise ValueError("Expected a non-empty stopPoint list")

        for stop_order, stop in enumerate(stops, start=1):
            if not isinstance(stop, dict):
                raise ValueError("Expected a stop object")
            station_id = required_text(stop, "id")
            station = {**known_stations.get(station_id, {}), **stop}
            stations[station_id] = {
                "id": station_id,
                "name": required_text(station, "name"),
                "latitude": coordinate(station.get("lat"), "latitude", 90),
                "longitude": coordinate(station.get("lon"), "longitude", 180),
            }
            line_stations.append(
                {
                    "line_id": LINE_ID,
                    "station_id": station_id,
                    "direction": direction,
                    "route_sequence": sequence_number,
                    "stop_order": stop_order,
                }
            )

    return ParsedTopology(line_name, stations, line_stations)


def collect_topology(client: httpx.Client) -> bool:
    """Fetch both directions, then atomically replace the current topology."""
    key = os.getenv("TFL_APP_KEY")
    params = {"app_key": key} if key else {}
    collections = []
    parsed_directions = []

    for direction in DIRECTIONS:
        endpoint = f"/Line/{LINE_ID}/Route/Sequence/{direction}"
        payload = None
        http_status = None
        error = None

        try:
            response = client.get(endpoint, params=params)
            http_status = response.status_code
            response.raise_for_status()
            payload = response.json()
            parsed_directions.append(parse_topology(payload, direction))
        except (httpx.HTTPError, ValueError) as exc:
            # HTTP exception messages can contain the URL and its API key.
            if isinstance(exc, httpx.HTTPStatusError):
                error = f"HTTP {http_status}"
            elif isinstance(exc, ValueError):
                error = f"Invalid topology: {exc}"
            else:
                error = type(exc).__name__
            logger.error("Topology %s: %s", direction, error)

        collections.append(
            CollectionRun(
                endpoint=endpoint,
                target=LINE_ID,
                collected_at=datetime.now(timezone.utc),
                outcome="error" if error else "success",
                http_status=http_status,
                error=error,
                raw_response=payload if isinstance(payload, (dict, list)) else None,
            )
        )

    complete = len(parsed_directions) == len(DIRECTIONS)
    with SessionLocal.begin() as session:
        session.add_all(collections)

        if complete:
            line_insert = insert(Line).values(
                id=LINE_ID, name=parsed_directions[0].line_name
            )
            session.execute(
                line_insert.on_conflict_do_update(
                    index_elements=[Line.id],
                    set_={"name": line_insert.excluded.name},
                )
            )

            # A station appears in both directions, but has one metadata row.
            stations = {}
            route_rows = []
            for parsed in parsed_directions:
                stations.update(parsed.stations)
                route_rows.extend(parsed.line_stations)

            station_insert = insert(Station).values(list(stations.values()))
            session.execute(
                station_insert.on_conflict_do_update(
                    index_elements=[Station.id],
                    set_={
                        "name": station_insert.excluded.name,
                        "latitude": station_insert.excluded.latitude,
                        "longitude": station_insert.excluded.longitude,
                    },
                )
            )

            # Replace only this line's current ordering, leaving history intact.
            session.execute(delete(LineStation).where(LineStation.line_id == LINE_ID))
            session.execute(insert(LineStation), route_rows)

    if complete:
        logger.info(
            "Victoria topology: success (%s stations, %s ordered stops)",
            len(stations),
            len(route_rows),
        )
    else:
        logger.warning("Topology import skipped; existing route ordering preserved")
    return complete


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        with httpx.Client(
            base_url=os.getenv("TFL_BASE_URL", "https://api.tfl.gov.uk"),
            timeout=10.0,
        ) as client:
            success = collect_topology(client)
    except SQLAlchemyError as exc:
        logger.error("Topology database write failed (%s)", type(exc).__name__)
        success = False

    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
