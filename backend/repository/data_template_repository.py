# Custom libraries
from logger import configure_logging

# Database modules
from models.agent import Agent
from models.data_template import DataTemplate
from schemas.data_template_schema import DataTemplateCreate

# Default libraries
from typing import Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class DataTemplateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_template(
        self, template_data: DataTemplateCreate
    ) -> Optional[DataTemplate]:
        new_template = DataTemplate(**template_data.model_dump())
        try:
            self.db.add(new_template)
            self.db.commit()
            self.db.refresh(new_template)
            return new_template
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Data template with same template class name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_template(self, update_data: dict) -> Optional[DataTemplate]:
        identifier = update_data.get("template_uuid")
        query_filter = (
            DataTemplate.id == identifier
            if isinstance(identifier, UUID)
            else DataTemplate.template_class == identifier
        )
        template = self.db.query(DataTemplate).filter(query_filter).first()
        if not template:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(template, key):
                    setattr(template, key, value)
            self.db.commit()
            self.db.refresh(template)
            return template
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Data template with same template class name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_or_update_template(self, data: dict) -> Optional[DataTemplate]:
        template_class = data.get("template_class")
        if not template_class:
            return None
        template = (
            self.db.query(DataTemplate)
            .filter(DataTemplate.template_class == template_class)
            .first()
        )
        if template:
            return self.update_template(template.id, data)
        else:
            return self.create_template(data)

    def get_template(self, identifier: Union[UUID, str]) -> Optional[DataTemplate]:
        if isinstance(identifier, UUID):
            query_filter = DataTemplate.id == identifier
        elif isinstance(identifier, str):
            query_filter = DataTemplate.template_class == identifier
        else:
            raise ValueError("Identifier must be a UUID or a template_class string")
        try:
            return self.db.query(DataTemplate).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_data_templates(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[DataTemplate], int]:
        query = self.db.query(DataTemplate)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(DataTemplate, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(DataTemplate, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(DataTemplate, key) == values)

        # Apply sorting
        if hasattr(DataTemplate, sort_by):
            order = (
                desc(getattr(DataTemplate, sort_by))
                if sort_order == "desc"
                else getattr(DataTemplate, sort_by)
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                data_templates = query.offset(skip).limit(page_size).all()
            else:
                data_templates = query.all()

            return data_templates, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_data_templates(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[DataTemplate], int]:
        query = self.db.query(DataTemplate)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(DataTemplate, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(DataTemplate, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(DataTemplate, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    DataTemplate.name.ilike(f"%{keyword}%"),
                    DataTemplate.template_class.ilike(f"%{keyword}%"),
                    DataTemplate.description.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(DataTemplate, sort_by):
            order = (
                asc(getattr(DataTemplate, sort_by))
                if sort_order == "asc"
                else desc(getattr(DataTemplate, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                data_templates = query.offset(skip).limit(page_size).all()
            else:
                data_templates = query.all()

            return data_templates, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_data_template(self, identifier: Union[UUID, str]) -> Optional[bool]:
        query_filter = (
            DataTemplate.id == identifier
            if isinstance(identifier, UUID)
            else DataTemplate.template_class == identifier
        )
        data_template = self.db.query(DataTemplate).filter(query_filter).first()
        if not data_template:
            return False
        # Check if any agent is using this data_template
        agents = (
            self.db.query(Agent)
            .filter(Agent.data_templates.any(data_template.template_class))
            .all()
        )
        if agents:
            agent_names = ", ".join(agent.name for agent in agents)
            raise HTTPException(
                status_code=409,
                detail=f"The Data Template '{data_template.template_class}' is assigned to the following agents: '{agent_names}'. Please delete or update the associated agents first.",
            )
        try:
            self.db.delete(data_template)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    # def paginated_data_templates(
    #     self,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[DataTemplate], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(DataTemplate)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(DataTemplate, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(DataTemplate, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(DataTemplate, key) == values)

    #     # Apply sorting
    #     if hasattr(DataTemplate, sort_by):
    #         order = (
    #             asc(getattr(DataTemplate, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(DataTemplate, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         templates = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return templates, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0

    # def paginated_search_templates(
    #     self,
    #     keyword: str,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[DataTemplate], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(DataTemplate)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(DataTemplate, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(DataTemplate, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(DataTemplate, key) == values)

    #     # Apply search
    #     if keyword:
    #         query = query.filter(
    #             or_(
    #                 DataTemplate.name.ilike(f"%{keyword}%"),
    #                 DataTemplate.template_class.ilike(f"%{keyword}%"),
    #                 DataTemplate.description.ilike(f"%{keyword}%"),
    #             )
    #         )

    #     # Apply sorting
    #     if hasattr(DataTemplate, sort_by):
    #         order = (
    #             asc(getattr(DataTemplate, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(DataTemplate, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         templates = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return templates, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0
