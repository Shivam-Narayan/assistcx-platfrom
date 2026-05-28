# # Default libraries
# from datetime import datetime
# from typing import Optional, List
# from uuid import UUID

# # Installed libraries
# from pydantic import BaseModel, ConfigDict


# class TaskProgressBase(BaseModel):
#     step_order: int
#     step_code: str
#     title: Optional[str] = None
#     description: Optional[str] = None
#     status: Optional[str] = "PENDING"
#     started_at: Optional[datetime] = None
#     executed_at: Optional[datetime] = None
#     execution_time: Optional[int] = None


# class TaskProgressDetail(TaskProgressBase):
#     id: UUID
#     email_data_id: UUID
#     created_at: Optional[datetime] = None
#     updated_at: Optional[datetime] = None

#     model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# class TaskProgressResponse(BaseModel):
#     task_progress: List[TaskProgressDetail]
#     total_execution_time: float
#     total: int
