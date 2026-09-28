from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Index, Integer, String, Text

from db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime | None) -> str | None:
    """SQLite returns naive datetimes; they are stored as UTC, so label them as such."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class Article(Base):
    __tablename__ = "articles"

    id               = Column(Integer, primary_key=True, index=True)
    title            = Column(String(500), nullable=False)
    url              = Column(String(2000), unique=True, nullable=False)
    source           = Column(String(200))
    category         = Column(String(100), index=True)
    published_at     = Column(DateTime(timezone=True))   # None when the source gave no date
    fetched_at       = Column(DateTime(timezone=True), default=_utcnow, index=True)

    raw_content      = Column(Text)   # plain-text excerpt from the source (HTML stripped)
    summary          = Column(Text)
    deep_explanation = Column(Text)   # NULL until AI analysis succeeds
    why_it_matters   = Column(Text)
    background_info  = Column(Text)

    importance_score = Column(Float, default=0.5)
    is_trending      = Column(Boolean, default=False)
    tags             = Column(JSON, default=list)
    # Articles about the same event (across outlets) share a cluster_id — see services/clustering.py
    cluster_id       = Column(Integer, index=True)
    # Local news (category 'local'): the location the story was fetched for — see services/local_news.py
    loc_country      = Column(String(2))
    loc_state        = Column(String(100))
    loc_district     = Column(String(100))

    __table_args__ = (Index("ix_articles_location", "loc_country", "loc_state", "loc_district"),)

    @property
    def is_analyzed(self) -> bool:
        return bool(self.deep_explanation)

    def to_dict(self, include_content: bool = True) -> dict:
        data = {
            "id":               self.id,
            "title":            self.title,
            "url":              self.url,
            "source":           self.source,
            "category":         self.category,
            "published_at":     _iso_utc(self.published_at),
            "fetched_at":       _iso_utc(self.fetched_at),
            "summary":          self.summary,
            "importance_score": self.importance_score,
            "is_trending":      bool(self.is_trending),
            "tags":             self.tags or [],
            "is_analyzed":      self.is_analyzed,
            "cluster_id":       self.cluster_id,
        }
        if self.category == "local":
            data["location"] = {"state": self.loc_state, "district": self.loc_district}
        if include_content:
            data.update({
                "raw_content":      self.raw_content,
                "deep_explanation": self.deep_explanation,
                "why_it_matters":   self.why_it_matters,
                "background_info":  self.background_info,
            })
        return data
