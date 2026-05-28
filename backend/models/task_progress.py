# from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, Text
# from sqlalchemy.dialects.postgresql import UUID
# from sqlalchemy.orm import relationship
# from sqlalchemy.sql import func
# from database import Base
# import uuid


# class TaskProgress(Base):
#     __tablename__ = "task_progress"

#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
#     email_data_id = Column(UUID, ForeignKey("emails.id"))
#     step_order = Column(Integer)
#     step_code = Column(String)
#     title = Column(String)
#     description = Column(Text)
#     status = Column(String, default="PENDING")
#     started_at = Column(DateTime)
#     executed_at = Column(DateTime)
#     execution_time = Column(Integer)
#     created_at = Column(DateTime, default=func.now())
#     updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

#     # Relationships
#     email = relationship("Email", back_populates="task_progress")


# """
# We will move away from this in the future, but for now we need to keep it here.
# Email will have a basic string for status
# """
