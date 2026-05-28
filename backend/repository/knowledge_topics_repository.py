# Custom libraries
from logger import configure_logging

# Database modules
from models.data_collection import DataCollection

# Default libraries
from typing import Optional, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = configure_logging(__name__)


class KnowledgeTopicsRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_knowledge_topics(
        self, collection_id: UUID, knowledge_topics_data: List[dict]
    ) -> Optional[List[dict]]:
        """
        Create/replace knowledge topics for a data collection.
        """
        try:
            # Get the data collection
            data_collection = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == collection_id)
                .first()
            )
            
            if not data_collection:
                raise HTTPException(
                    status_code=404,
                    detail="Data collection not found."
                )

            # Set the knowledge topics directly
            data_collection.knowledge_topics = knowledge_topics_data
            self.db.commit()
            self.db.refresh(data_collection)
            
            return knowledge_topics_data
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_knowledge_topics(self, collection_id: UUID) -> List[dict]:
        """
        Get all knowledge topics for a data collection.
        """
        try:
            data_collection = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == collection_id)
                .first()
            )
            
            if not data_collection:
                return []
                
            return data_collection.knowledge_topics or []
            
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def update_knowledge_topics(
        self, collection_id: UUID, knowledge_topics_data: List[dict]
    ) -> Optional[List[dict]]:
        """
        Update knowledge topics for a data collection.
        """
        try:
            data_collection = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == collection_id)
                .first()
            )
            
            if not data_collection:
                raise HTTPException(
                    status_code=404,
                    detail="Data collection not found."
                )
            
            # Update the knowledge topics
            data_collection.knowledge_topics = knowledge_topics_data
            self.db.commit()
            self.db.refresh(data_collection)
            
            return knowledge_topics_data
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def delete_knowledge_topics(self, collection_id: UUID) -> bool:
        """
        Delete all knowledge topics for a data collection.
        """
        try:
            data_collection = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == collection_id)
                .first()
            )
            
            if not data_collection:
                return False
            
            # Clear the knowledge topics
            data_collection.knowledge_topics = []
            self.db.commit()
            
            return True
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return False