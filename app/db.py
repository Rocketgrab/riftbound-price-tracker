from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import ROOT, settings


class Base(DeclarativeBase):
    pass


class RawListing(Base):
    __tablename__ = "raw_listings"
    __table_args__ = (
        UniqueConstraint("marketplace", "external_id", name="uq_listing_ext"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    price_native: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    price_usd: Mapped[float] = mapped_column(Float, index=True)
    listing_type: Mapped[str] = mapped_column(String(16), index=True)
    sku: Mapped[str] = mapped_column(String(32), index=True)
    language: Mapped[str] = mapped_column(String(8), index=True)
    url: Mapped[str] = mapped_column(Text)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    observed_on: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(16), default="live")
    kept: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DailyAggregate(Base):
    __tablename__ = "daily_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "date",
            "marketplace",
            "sku",
            "language",
            name="uq_daily_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    marketplace: Mapped[str] = mapped_column(String(32), index=True)
    sku: Mapped[str] = mapped_column(String(32), index=True)
    language: Mapped[str] = mapped_column(String(8), index=True)
    high_usd: Mapped[float] = mapped_column(Float)
    low_usd: Mapped[float] = mapped_column(Float)
    median_usd: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)
    sold_volume: Mapped[int] = mapped_column(Integer, default=0)


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("date", "currency", name="uq_fx_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(8))
    usd_per_unit: Mapped[float] = mapped_column(Float)


class CollectRun(Base):
    __tablename__ = "collect_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    marketplace: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16))
    items_kept: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


def make_engine():
    (ROOT / "data").mkdir(exist_ok=True)
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(daily_aggregates)"))}
        if "sold_volume" not in cols:
            conn.execute(text("ALTER TABLE daily_aggregates ADD COLUMN sold_volume INTEGER DEFAULT 0"))
