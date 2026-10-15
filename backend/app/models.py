from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    outcome: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB(none_as_null=True)
    )

    __table_args__ = (
        CheckConstraint("outcome IN ('success', 'error')"),
        Index("collection_runs_target_time_idx", target, collected_at.desc()),
    )


class Line(Base):
    __tablename__ = "lines"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90"),
        CheckConstraint("longitude BETWEEN -180 AND 180"),
    )


class LineStation(Base):
    __tablename__ = "line_stations"

    line_id: Mapped[str] = mapped_column(
        Text, ForeignKey("lines.id"), primary_key=True
    )
    direction: Mapped[str] = mapped_column(Text, primary_key=True)
    route_sequence: Mapped[int] = mapped_column(primary_key=True)
    stop_order: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(Text, ForeignKey("stations.id"))

    __table_args__ = (
        CheckConstraint("direction IN ('inbound', 'outbound')"),
        CheckConstraint("route_sequence >= 1"),
        CheckConstraint("stop_order >= 1"),
        Index("line_stations_station_id_idx", "station_id"),
    )
