# # Custom libraries
# from logger import configure_logging

# # Database modules
# from models.task_progress import TaskProgress
# from schemas.task_progress_schema import TaskProgressBase

# # Default libraries
# from typing import Optional, Tuple, Dict, List
# from uuid import UUID

# # Installed libraries
# from sqlalchemy import asc, desc, or_
# from sqlalchemy.exc import SQLAlchemyError
# from sqlalchemy.orm import Session


# logger = configure_logging(__name__)


# class TaskProgressRepository:
#     def __init__(self, db: Session):
#         self.db = db

#     def create_task_progress(
#         self, email_uuid: UUID, steps: List[TaskProgressBase]
#     ) -> List[TaskProgress]:
#         task_progress_records = []
#         for step in steps:
#             task_progress = TaskProgress(email_data_id=email_uuid, **step.model_dump())
#             self.db.add(task_progress)
#             task_progress_records.append(task_progress)
#         try:
#             self.db.commit()
#             return task_progress_records
#         except SQLAlchemyError as e:
#             logger.error(f"SQLAlchemy Error: {e}")
#             self.db.rollback()
#             return None

#     def update_task_progress(
#         self, email_uuid: UUID, step_code: str, update_data: Dict
#     ) -> Optional[TaskProgress]:
#         task_progress = (
#             self.db.query(TaskProgress)
#             .filter(
#                 TaskProgress.email_data_id == email_uuid,
#                 TaskProgress.step_code == step_code,
#             )
#             .first()
#         )
#         if not task_progress:
#             return None

#         try:
#             for key, value in update_data.items():
#                 if hasattr(task_progress, key):
#                     setattr(task_progress, key, value)
#             self.db.commit()
#             self.db.refresh(task_progress)
#             return task_progress
#         except SQLAlchemyError as e:
#             self.db.rollback()
#             logger.error(f"SQLAlchemy Error: {e}")
#             return None

#     def get_task_progress(
#         self,
#         email_uuid: UUID,
#         filters: Optional[Dict[str, any]] = None,
#         sort_by: str = "updated_at",
#         sort_order: str = "desc",
#     ) -> Tuple[List[TaskProgress], float, int]:
#         query = self.db.query(TaskProgress)

#         # Fetch data for specific email
#         query = query.filter(TaskProgress.email_data_id == email_uuid)

#         # Apply filters
#         if filters:
#             for key, values in filters.items():
#                 if hasattr(TaskProgress, key):
#                     if isinstance(values, list):
#                         # Handle multiple values for the same filter key
#                         condition = or_(
#                             *(getattr(TaskProgress, key) == value for value in values)
#                         )
#                         query = query.filter(condition)
#                     else:
#                         query = query.filter(getattr(TaskProgress, key) == values)

#         # Apply sorting
#         if hasattr(TaskProgress, sort_by):
#             order = (
#                 asc(getattr(TaskProgress, sort_by))
#                 if sort_order == "asc"
#                 else desc(getattr(TaskProgress, sort_by))
#             )
#             query = query.order_by(order)

#         try:
#             task_progress = query.all()
#             total = query.count()
#             total_execution_time = (
#                 sum(
#                     tp.execution_time
#                     for tp in task_progress
#                     if tp.execution_time is not None
#                 )
#                 / 1000
#             )
#             return task_progress, total_execution_time, total
#         except SQLAlchemyError as e:
#             logger.error(f"SQLAlchemy Error: {e}")
#             return []

#     def search_task_progress(
#         self,
#         email_uuid: UUID,
#         keyword: str = None,
#         filters: Optional[Dict[str, any]] = None,
#         sort_by: str = "updated_at",
#         sort_order: str = "desc",
#     ) -> Tuple[List[TaskProgress], float, int]:
#         query = self.db.query(TaskProgress)

#         # Fetch data for specific email
#         query = query.filter(TaskProgress.email_data_id == email_uuid)

#         # Apply filters
#         if filters:
#             for key, values in filters.items():
#                 if hasattr(TaskProgress, key):
#                     if isinstance(values, list):
#                         # Handle multiple values for the same filter key
#                         condition = or_(
#                             *(getattr(TaskProgress, key) == value for value in values)
#                         )
#                         query = query.filter(condition)
#                     else:
#                         query = query.filter(getattr(TaskProgress, key) == values)

#         # Apply search
#         if keyword:
#             query = query.filter(
#                 or_(
#                     TaskProgress.step_code.ilike(f"%{keyword}%"),
#                     TaskProgress.title.ilike(f"%{keyword}%"),
#                     TaskProgress.description.ilike(f"%{keyword}%"),
#                 )
#             )

#         # Apply sorting
#         if hasattr(TaskProgress, sort_by):
#             order = (
#                 asc(getattr(TaskProgress, sort_by))
#                 if sort_order == "asc"
#                 else desc(getattr(TaskProgress, sort_by))
#             )
#             query = query.order_by(order)

#         try:
#             task_progress = query.all()
#             total = query.count()
#             total_execution_time = (
#                 sum(
#                     tp.execution_time
#                     for tp in task_progress
#                     if tp.execution_time is not None
#                 )
#                 / 1000
#             )
#             return task_progress, total_execution_time, total
#         except SQLAlchemyError as e:
#             logger.error(f"SQLAlchemy Error: {e}")
#             return []
