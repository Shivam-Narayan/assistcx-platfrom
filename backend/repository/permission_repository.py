# Custom libraries
from logger import configure_logging

# Database modules
from models.agent import Agent
from models.data_collection import DataCollection
from models.data_template import DataTemplate
from models.email import Email
# from models.intent import Intent  # intents module deprecated alongside intent routes
from models.mailbox_polling import MailboxPolling
from models.permission import Permission
from models.user_role import UserRole
from repository.user_access_repository import UserAccessRepository
from repository.user_role_repository import UserRoleRepository

# Default libraries
from typing import Optional, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class PermissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_permissions(self, permissions: List[Dict]) -> List[Permission]:
        permission_records = []
        for permission in permissions:
            permission = Permission(**permission)
            self.db.add(permission)
            permission_records.append(permission)
        try:
            self.db.commit()
            return permission_records
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Permission already exists.",
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return []

    def update_permissions(self, update_data: List[Dict]) -> List[Permission]:
        try:
            # Delete permissions not in update_data
            update_keys = [update_item["key"] for update_item in update_data]
            permissions_to_delete = (
                self.db.query(Permission)
                .filter(~Permission.key.in_(update_keys))
                .all()
            )
            for permission_to_delete in permissions_to_delete:
                try:
                    self.db.delete(permission_to_delete)
                    logger.info(f"Permissions to delete: {permission_to_delete.key}")
                except SQLAlchemyError as e:
                    logger.error(f"SQLAlchemy Error: {e}")
                    self.db.rollback()

            updated_permissions = []
            for update_item in update_data:
                key_to_update = update_item.get("key")
                if not key_to_update:
                    logger.warning("Update data is missing the 'key' field.")
                    continue
                permission = (
                    self.db.query(Permission)
                    .filter(Permission.key == key_to_update)
                    .first()
                )
                if permission:
                    for field, value in update_item.items():
                        setattr(permission, field, value)
                else:
                    permission = Permission(**update_item)
                    self.db.add(permission)

                updated_permissions.append(permission)

            self.db.commit()
            return updated_permissions
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_all_permissions(
        self, field_restrictions: Optional[bool] = False
    ) -> List[Permission]:
        try:
            if field_restrictions:
                permissions = (
                    self.db.query(Permission)
                    .filter(Permission.data_filters.isnot(None))
                    .filter(Permission.data_filters != [])
                    .order_by(Permission.display_order, Permission.created_at)
                    .all()
                )
                for permission in permissions:
                    unique_values = self.get_data_filter_values(permission)
                    permission.data_filters = unique_values
            else:
                permissions = (
                    self.db.query(Permission)
                    .order_by(Permission.display_order, Permission.created_at)
                    .all()
                )
            return permissions
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_data_filter_values(self, permission: Permission) -> Dict[str, List[str]]:
        unique_values = {}
        modules = {
            "agents": [Agent],
            "knowledge": [DataCollection],
            "data_templates": [DataTemplate],
            # "intents": [Intent],
            "mailbox_pollings": [MailboxPolling],
            "task_inbox": [Email],
        }

        if permission.module in modules:
            models = modules[permission.module]

            for model in models:
                columns = model.__table__.columns
                for data_filter in permission.data_filters:
                    if data_filter in columns:
                        query = select(model.__table__.c[data_filter]).distinct()
                        if model is DataCollection and data_filter == "name":
                            query = query.where(
                                model.__table__.c[data_filter] != "ROOT",
                                model.__table__.c["availability"] != "PRIVATE",
                            )
                        result = self.db.execute(query).fetchall()
                        unique_values.setdefault(data_filter, []).extend(
                            [row[0] for row in result if row[0] is not None]
                        )

        unique_values = {
            key: list(set(values)) for key, values in unique_values.items()
        }
        return unique_values

    def get_user_role_permissions(
        self, user_role_id: UUID, field_restrictions: Optional[bool] = False
    ) -> List[Permission]:
        try:
            user_role = (
                self.db.query(UserRole).filter(UserRole.id == user_role_id).first()
            )
            if not user_role:
                return None

            # Get the module keys from the role's permissions
            role_perms = user_role.role_permissions or {}
            module_keys = list(role_perms.get("modules", {}).keys())

            if not module_keys:
                return []

            query = (
                self.db.query(Permission)
                .filter(Permission.key.in_(module_keys))
                .order_by(Permission.display_order, Permission.created_at)
            )

            if field_restrictions:
                query = query.filter(
                    Permission.data_filters.isnot(None),
                    Permission.data_filters != [],
                )

            permissions = query.all()

            if field_restrictions:
                for permission in permissions:
                    permission.data_filters = self.get_data_filter_values(permission)

            return permissions

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_web_app_permissions(self, role_permissions: dict) -> List[str]:
        """
        Get web routes for frontend page visibility from role permissions.
        New format: reads directly from role_permissions dict + PLATFORM_MODULES config.
        """
        try:
            from utils.rbac_utils import get_web_routes
            return get_web_routes(role_permissions)
        except Exception as e:
            logger.error(f"Error in get_web_app_permissions: {e}")
            return []

    def delete_permission(self, identifier: UUID) -> Optional[bool]:
        query_filter = (
            Permission.id == identifier
            if isinstance(identifier, UUID)
            else Permission.key == identifier
        )
        permission = self.db.query(Permission).filter(query_filter).first()
        if not permission:
            return False

        try:
            self.db.delete(permission)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False
