from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,Index,JSON,String,Text,Uuid,func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.db.base import Base
JSON_VALUE=JSON().with_variant(JSONB,"postgresql")
class TerritoryAIConversation(Base):
    __tablename__="territory_ai_conversations";__table_args__=(Index("ix_territory_ai_conversations_campaign_user","campaign_id","user_id"),)
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4);campaign_id:Mapped[UUID]=mapped_column(ForeignKey("campaigns.id",ondelete="RESTRICT"),nullable=False);user_id:Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="RESTRICT"),nullable=False);title:Mapped[str]=mapped_column(String(180),nullable=False);last_intent:Mapped[str|None]=mapped_column(String(50));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False);updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False);messages:Mapped[list["TerritoryAIMessage"]]=relationship(back_populates="conversation",cascade="all, delete-orphan",order_by="TerritoryAIMessage.created_at")
class TerritoryAIMessage(Base):
    __tablename__="territory_ai_messages";__table_args__=(CheckConstraint("role IN ('USER','ASSISTANT')",name="role"),Index("ix_territory_ai_messages_conversation","conversation_id","created_at"))
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4);conversation_id:Mapped[UUID]=mapped_column(ForeignKey("territory_ai_conversations.id",ondelete="CASCADE"),nullable=False);role:Mapped[str]=mapped_column(String(20),nullable=False);content:Mapped[str]=mapped_column(Text,nullable=False);citations:Mapped[list]=mapped_column(JSON_VALUE,default=list,server_default="[]",nullable=False);intent:Mapped[str|None]=mapped_column(String(50));territory_id:Mapped[int|None]=mapped_column(ForeignKey("parishes.id",ondelete="SET NULL"));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False);conversation:Mapped[TerritoryAIConversation]=relationship(back_populates="messages")
