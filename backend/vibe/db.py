"""Database schema (SQLite by default, any SQLAlchemy URL works)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import (Float, ForeignKey, Integer, LargeBinary, String, Text, DateTime,
                        UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    instagram_handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    other_pages_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    @property
    def other_pages(self) -> list[str]:
        return json.loads(self.other_pages_json or "[]")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "instagram_handle": self.instagram_handle,
                "other_pages": self.other_pages, "created_at": self.created_at.isoformat()}


# label of a post:
#   team      = posted on the team's own page (approved)
#   rejected  = a real draft the seniors sent back
#   other     = a post from another page ("not our vibe")
#   augmented = a deliberately broken copy of a team post (near-miss)
# decision (optional) = what the seniors decided about this exact design: "accepted" | "rejected".
#   Only designs with a decision train the approval model; project groups versions of one brief.
LABELS = ("team", "rejected", "other", "augmented")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("team_id", "source_page", "external_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    label: Mapped[str] = mapped_column(String(16), index=True)
    source_page: Mapped[str] = mapped_column(String(120), default="")
    external_id: Mapped[str] = mapped_column(String(200))
    image_path: Mapped[str] = mapped_column(String(500))
    caption: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)   # accepted | rejected
    project: Mapped[str | None] = mapped_column(String(120), nullable=True)   # brief this design was for
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    features: Mapped["Feature | None"] = relationship(back_populates="post", uselist=False,
                                                     cascade="all, delete-orphan")

    def to_dict(self, with_features: bool = False) -> dict:
        d = {"id": self.id, "team_id": self.team_id, "label": self.label,
             "source_page": self.source_page, "image_url": media_url(self.image_path),
             "caption": self.caption, "posted_at": self.posted_at.isoformat() if self.posted_at else None,
             "likes": self.likes, "comments": self.comments,
             "decision": self.decision, "project": self.project}
        if with_features and self.features is not None:
            d["features"] = self.features.to_dict()
        return d


class Feature(Base):
    __tablename__ = "features"
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    clip: Mapped[bytes] = mapped_column(LargeBinary)
    palette_json: Mapped[str] = mapped_column(Text)
    brightness: Mapped[float] = mapped_column(Float)
    saturation: Mapped[float] = mapped_column(Float)
    warmth: Mapped[float] = mapped_column(Float)
    text_amount: Mapped[float] = mapped_column(Float)
    busyness: Mapped[float] = mapped_column(Float)
    whitespace: Mapped[float] = mapped_column(Float)
    contrast: Mapped[float] = mapped_column(Float)
    illustration: Mapped[float] = mapped_column(Float)
    hist: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)   # 64-bin Lab colour histogram
    aesthetic: Mapped[float | None] = mapped_column(Float, nullable=True)    # LAION appeal score
    typo_json: Mapped[str | None] = mapped_column(Text, nullable=True)       # finish.typography() summary
    post: Mapped[Post] = relationship(back_populates="features")

    @property
    def vector(self) -> np.ndarray:
        return np.frombuffer(self.clip, dtype=np.float32)

    def style(self) -> dict:
        from .features import STYLE_KEYS
        return {k: getattr(self, k) for k in STYLE_KEYS}

    def to_dict(self) -> dict:
        return {**self.style(), "palette": json.loads(self.palette_json)}


class Check(Base):
    __tablename__ = "checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    user: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    inspo_json: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(40))
    result_json: Mapped[str] = mapped_column(Text)
    model_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str | None] = mapped_column(String(10), nullable=True)         # plan | final
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)      # plan check a final belongs to
    project: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    outcome: Mapped["Outcome | None"] = relationship(uselist=False, cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        r = json.loads(self.result_json)
        r.update({"id": self.id, "team_id": self.team_id, "user": self.user,
                  "description": self.description,
                  "inspo_urls": [media_url(p) for p in json.loads(self.inspo_json)],
                  "created_at": self.created_at.isoformat(),
                  "model_version": self.model_version,
                  "kind": self.kind or "plan", "parent_id": self.parent_id, "project": self.project,
                  "outcome": self.outcome.result if self.outcome else None})
        return r


class Outcome(Base):
    __tablename__ = "outcomes"
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), primary_key=True)
    result: Mapped[str] = mapped_column(String(20))  # approved | rejected | posted
    final_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ModelVersion(Base):
    __tablename__ = "models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    metrics_json: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(500))

    def to_dict(self) -> dict:
        return {"id": self.id, "team_id": self.team_id, "trained_at": self.trained_at.isoformat(),
                "metrics": json.loads(self.metrics_json)}


class Plugin(Base):
    __tablename__ = "plugins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500))
    slot: Mapped[str] = mapped_column(String(40), default="result")  # result | profile
    author_team: Mapped[str] = mapped_column(String(120), default="")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    def to_dict(self) -> dict:
        return {"id": self.id, "team_id": self.team_id, "name": self.name,
                "description": self.description, "url": self.url, "slot": self.slot,
                "author_team": self.author_team, "enabled": bool(self.enabled),
                "created_at": self.created_at.isoformat()}


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "team_id": self.team_id, "kind": self.kind, "status": self.status,
                "progress": round(self.progress, 3), "message": self.message,
                "created_at": self.created_at.isoformat(),
                "finished_at": self.finished_at.isoformat() if self.finished_at else None}


def media_url(path: str | None) -> str | None:
    """Image paths are stored relative to DATA_DIR and served under /media."""
    if not path:
        return None
    return "/media/" + path.replace("\\", "/")


engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False}
                       if config.DB_URL.startswith("sqlite") else {})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
    if config.DB_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Columns added after the first release: (table, column, SQL type). init_db adds any that are missing,
# so an existing database keeps working; pipeline.backfill_features fills them in.
_ADDED_COLUMNS = [("features", "hist", "BLOB"), ("features", "aesthetic", "FLOAT"),
                  ("features", "typo_json", "TEXT"), ("posts", "decision", "VARCHAR(16)"),
                  ("posts", "project", "VARCHAR(120)"), ("checks", "kind", "VARCHAR(10)"),
                  ("checks", "parent_id", "INTEGER"), ("checks", "project", "VARCHAR(120)")]


def init_db() -> None:
    Base.metadata.create_all(engine)
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, col, sqltype in _ADDED_COLUMNS:
            if col not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sqltype}"))
