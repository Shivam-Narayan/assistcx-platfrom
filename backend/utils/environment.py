import os
import json
import redis
from dotenv import load_dotenv
from logger import configure_logging
from contextlib import contextmanager

load_dotenv()
logger = configure_logging(__name__)


class Environment:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Environment, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            self.redis_client = None
            self._initialized = True

    @contextmanager
    def get_redis_client(self):
        try:
            if self.redis_client is None:
                self.redis_client = redis.from_url(self.redis_url)
            yield self.redis_client
        except redis.RedisError as e:
            logger.error(f"Redis connection error: {e}")
            raise
        finally:
            if self.redis_client:
                self.redis_client.close()
                self.redis_client = None

    def get_environment(self, organization_schema="public"):
        try:
            with self.get_redis_client() as client:
                env_data = client.get(f"{organization_schema}:environment")
                if env_data is None:
                    logger.error(f"Missing environment for: {organization_schema}")
                    return None
                org_env = json.loads(env_data.decode("utf-8"))
                return org_env
        except Exception as e:
            logger.error(f"Error getting environment: {e}")
            return None

    def get_environment_key(self, key: str, organization_schema: str = "public"):
        """
        Get a specific key from the environment data.
        """
        try:
            with self.get_redis_client() as client:
                env_data = client.get(f"{organization_schema}:environment")
                if env_data is None:
                    logger.error(f"Missing environment for: {organization_schema}")
                    return None

                org_env = json.loads(env_data.decode("utf-8"))
                return org_env.get(key.upper())

        except Exception as e:
            logger.error(f"Error getting environment key {key}: {e}")
            return None

    def get_preferences(self, organization_schema="public"):
        try:
            with self.get_redis_client() as client:
                preference_data = client.get(f"{organization_schema}:preferences")
                if preference_data is None:
                    logger.error(f"Missing preferences for: {organization_schema}")
                    return None
                org_preference = json.loads(preference_data.decode("utf-8"))
                return org_preference
        except Exception as e:
            logger.error(f"Error getting preferences: {e}")
            return None

    def set_environment(self, environment_data, organization_schema="public"):
        try:
            with self.get_redis_client() as client:
                client.set(
                    f"{organization_schema}:environment", json.dumps(environment_data)
                )
        except Exception as e:
            logger.error(f"Error getting environment: {e}")
            return None

    def set_preferences(self, preference_data, organization_schema="public"):
        try:
            with self.get_redis_client() as client:
                client.set(
                    f"{organization_schema}:preferences", json.dumps(preference_data)
                )
        except Exception as e:
            logger.error(f"Error getting environment: {e}")
            return None


environment = Environment()
