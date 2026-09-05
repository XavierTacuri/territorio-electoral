from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, validates
from app.db.base import Base
from app.db.spatial import SpatialGeometry


class TechnicalFields:
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class Province(TechnicalFields, Base):
    __tablename__ = "provinces"
    __table_args__ = (Index("ix_provinces_code", "code", unique=True), Index("ix_provinces_name", "name", unique=True))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(2), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    @property
    def dpa_code(self) -> str: return self.code
    @validates("code")
    def clean_code(self, _k: str, v: str) -> str: return v.strip()
    @validates("name")
    def clean_name(self, _k: str, v: str) -> str: return " ".join(v.split())


class Canton(TechnicalFields, Base):
    __tablename__ = "cantons"
    __table_args__ = (UniqueConstraint("province_id", "code", name="uq_cantons_province_code"), UniqueConstraint("province_id", "name", name="uq_cantons_province_name"), Index("ix_cantons_dpa_code", "dpa_code", unique=True), Index("ix_cantons_province_id", "province_id"), Index("ix_cantons_geometry_gist", "geometry", postgresql_using="gist"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    province_id: Mapped[int] = mapped_column(ForeignKey("provinces.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(2), nullable=False)
    dpa_code: Mapped[str] = mapped_column(String(4), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    geometry: Mapped[str | None] = mapped_column(SpatialGeometry("MULTIPOLYGON"), nullable=True)


class Parish(TechnicalFields, Base):
    __tablename__ = "parishes"
    __table_args__ = (UniqueConstraint("canton_id", "code", name="uq_parishes_canton_code"), CheckConstraint("parish_type IN ('URBAN','RURAL')", name="parish_type"), Index("ix_parishes_dpa_code", "dpa_code", unique=True), Index("ix_parishes_canton_id", "canton_id"), Index("ix_parishes_geometry_gist", "geometry", postgresql_using="gist"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canton_id: Mapped[int] = mapped_column(ForeignKey("cantons.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(2), nullable=False)
    dpa_code: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parish_type: Mapped[str] = mapped_column(String(10), nullable=False)
    geometry: Mapped[str | None] = mapped_column(SpatialGeometry("MULTIPOLYGON"), nullable=True)


class Community(TechnicalFields, Base):
    __tablename__ = "communities"
    __table_args__ = (UniqueConstraint("parish_id", "name", name="uq_communities_parish_name"), CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"), CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"), Index("ix_communities_parish_id", "parish_id"), Index("ix_communities_location_gist", "location", postgresql_using="gist"), Index("uq_communities_parish_lower_name", "parish_id", text("lower(name)"), unique=True))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    parish_id: Mapped[int] = mapped_column(ForeignKey("parishes.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location: Mapped[str | None] = mapped_column(SpatialGeometry("POINT"), nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class Sector(TechnicalFields, Base):
    __tablename__ = "sectors"
    __table_args__ = (UniqueConstraint("community_id", "name", name="uq_sectors_community_name"), CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"), CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"), Index("ix_sectors_community_id", "community_id"), Index("ix_sectors_location_gist", "location", postgresql_using="gist"), Index("uq_sectors_community_lower_name", "community_id", text("lower(name)"), unique=True))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    community_id: Mapped[UUID] = mapped_column(ForeignKey("communities.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location: Mapped[str | None] = mapped_column(SpatialGeometry("POINT"), nullable=True)
