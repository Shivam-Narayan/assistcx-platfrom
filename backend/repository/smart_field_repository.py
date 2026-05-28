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


class SmartFieldRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_smart_fields(
        self, collection_id: UUID, smart_fields_data: List[dict]
    ) -> Optional[List[dict]]:
        """
        Create/replace smart fields for a data collection.
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

            # Set the smart fields directly
            data_collection.smart_fields = smart_fields_data
            self.db.commit()
            self.db.refresh(data_collection)
            
            return smart_fields_data
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_smart_fields(self, collection_id: UUID) -> List[dict]:
        """
        Get all smart fields for a data collection.
        """
        try:
            data_collection = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == collection_id)
                .first()
            )
            
            if not data_collection:
                return []
                
            return data_collection.smart_fields or []
            
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def update_smart_fields(
        self, collection_id: UUID, smart_fields_data: List[dict]
    ) -> Optional[List[dict]]:
        """
        Update smart fields for a data collection.
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
            
            # Update the smart fields
            data_collection.smart_fields = smart_fields_data
            self.db.commit()
            self.db.refresh(data_collection)
            
            return smart_fields_data
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def delete_smart_fields(self, collection_id: UUID) -> bool:
        """
        Delete all smart fields for a data collection.
        """
        try:
            data_collection = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == collection_id)
                .first()
            )
            
            if not data_collection:
                return False
            
            # Clear the smart fields
            data_collection.smart_fields = []
            self.db.commit()
            
            return True
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return False