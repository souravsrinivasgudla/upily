from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    Boolean, Float, ForeignKey, JSON, func
)
from sqlalchemy.orm import relationship
from db.database import Base, is_sqlite


class Article(Base):
    __tablename__ = "articles"

    id              = Column(Integer, primary_key=True, index=True)
    title           = Column(String(500), nullable=False)
    url             = Column(String(2000), unique=True, nullable=False)
    source          = Column(String(200))
    category        = Column(String(100))
    published_at    = Column(DateTime(timezone=True))
    fetched_at      = Column(DateTime(timezone=True), server_default=func.now())

    raw_content     = Column(Text)
    summary         = Column(Text)
    deep_explanation= Column(Text)
    why_it_matters  = Column(Text)
    background_info = Column(Text)

    importance_score= Column(Float, default=0.5)
    is_trending     = Column(Boolean, default=False)
    tags            = Column(JSON, default=list)

    # 1536-dim vector for OpenAI text-embedding-3-small
    # SQLite fallback: store as JSON or String
    embedding       = Column(JSON) if not is_sqlite else Column(Text)

    qa_pairs = relationship("QAPair", back_populates="article", cascade="all, delete")

    def to_dict(self):
        return {
            "id":               self.id,
            "title":            self.title,
            "url":              self.url,
            "source":           self.source,
            "category":         self.category,
            "published_at":     self.published_at.isoformat() if self.published_at else None,
            "raw_content":      self.raw_content,
            "summary":          self.summary,
            "deep_explanation": self.deep_explanation,
            "why_it_matters":   self.why_it_matters,
            "background_info":  self.background_info,
            "importance_score": self.importance_score,
            "is_trending":      self.is_trending,
            "tags":             self.tags or [],
        }


class QAPair(Base):
    __tablename__ = "qa_pairs"

    id         = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=True)
    question   = Column(Text, nullable=False)
    answer     = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    embedding  = Column(JSON) if not is_sqlite else Column(Text)

    article = relationship("Article", back_populates="qa_pairs")


class TrendReport(Base):
    __tablename__ = "trend_reports"

    id          = Column(Integer, primary_key=True, index=True)
    date        = Column(DateTime(timezone=True), server_default=func.now())
    trends      = Column(JSON)
    categories  = Column(JSON)
    top_articles= Column(JSON)


class DailyDigest(Base):
    __tablename__ = "daily_digests"

    id                  = Column(Integer, primary_key=True, index=True)
    date                = Column(DateTime(timezone=True), server_default=func.now())
    article_count       = Column(Integer)
    categories_covered  = Column(JSON)
    status              = Column(String(50), default="pending")
    error               = Column(Text)
