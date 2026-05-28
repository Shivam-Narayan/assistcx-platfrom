# Custom libraries
from logger import configure_logging
from utils.authentication import Authentication
from utils.crypto_utils import encrypt_string, decrypt_string
from utils.schema_utils import get_user_schema, set_schema

# Database modules
from repository.configuration_repository import ConfigurationRepository
from repository.user_repository import UserRepository

# Default libraries
import json
import os
import secrets
from typing import Optional
from urllib.parse import urlencode

# Installed libraries
import httpx
import jwt
import msal
import redis
from dotenv import load_dotenv


load_dotenv()
logger = configure_logging(logger_name=__name__)


class SSOService:
    """Handles all SSO/OIDC logic: discovery, authorization URL building,
    IdP code exchange, ID token validation, and one-time code management."""

    # Well-known OIDC discovery URLs
    MICROSOFT_WELL_KNOWN = (
        "https://login.microsoftonline.com/{tenant_id}/v2.0"
        "/.well-known/openid-configuration"
    )
    MICROSOFT_JWKS_URL = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
    GOOGLE_WELL_KNOWN = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )

    # Redis key prefixes and TTLs
    STATE_PREFIX = "sso:state:"
    STATE_TTL = 300  # 5 minutes
    CODE_PREFIX = "sso:code:"
    CODE_TTL = 60  # 60 seconds
    WELLKNOWN_PREFIX = "sso:wellknown:"
    WELLKNOWN_TTL = 3600  # 1 hour

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.frontend_url = os.getenv("NEXTAUTH_URL", "http://localhost:3000")
        self.authentication = Authentication()

    # ── Redis helpers ──────────────────────────────────────────────────

    def _get_redis(self):
        return redis.from_url(self.redis_url, decode_responses=True)

    def _redis_set(self, key: str, value: dict, ttl: int):
        client = self._get_redis()
        try:
            client.setex(key, ttl, json.dumps(value))
        finally:
            client.close()

    def _redis_get_and_delete(self, key: str) -> Optional[dict]:
        """Atomically retrieve and delete a key (single-use pattern)."""
        client = self._get_redis()
        try:
            pipe = client.pipeline()
            pipe.get(key)
            pipe.delete(key)
            results = pipe.execute()
            data = results[0]
            return json.loads(data) if data else None
        finally:
            client.close()

    def _redis_get(self, key: str) -> Optional[dict]:
        client = self._get_redis()
        try:
            data = client.get(key)
            return json.loads(data) if data else None
        finally:
            client.close()

    # ── Auth config helpers ────────────────────────────────────────────

    def _get_auth_config(self, org_schema: str) -> Optional[dict]:
        """Read auth_config from the org's Configuration table."""
        with set_schema(org_schema) as db:
            config_repo = ConfigurationRepository(db)
            config = config_repo.get_configuration()
            if config and config.auth_config:
                return config.auth_config
        return None

    def _get_client_secret(self, auth_config: dict) -> Optional[str]:
        """Decrypt the stored client secret."""
        encrypted = auth_config.get("sso_client_secret_encrypted")
        if encrypted:
            return decrypt_string(encrypted)
        return None

    # ── OIDC Discovery ─────────────────────────────────────────────────

    def _get_well_known_url(self, auth_config: dict) -> Optional[str]:
        provider = auth_config.get("sso_provider")
        if provider == "microsoft":
            tenant_id = auth_config.get("sso_tenant_id")
            if not tenant_id:
                return None
            return self.MICROSOFT_WELL_KNOWN.format(tenant_id=tenant_id)
        elif provider == "google":
            return self.GOOGLE_WELL_KNOWN
        elif provider == "oidc":
            return auth_config.get("sso_well_known_url")
        return None

    def get_well_known_config(self, auth_config: dict, org_schema: str) -> Optional[dict]:
        """Fetch OIDC discovery document, cached in Redis for 1 hour."""
        cache_key = f"{self.WELLKNOWN_PREFIX}{org_schema}"
        cached = self._redis_get(cache_key)
        if cached:
            return cached

        well_known_url = self._get_well_known_url(auth_config)
        if not well_known_url:
            return None

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(well_known_url)
                resp.raise_for_status()
                data = resp.json()

            result = {
                "authorization_endpoint": data.get("authorization_endpoint"),
                "token_endpoint": data.get("token_endpoint"),
                "jwks_uri": data.get("jwks_uri"),
                "issuer": data.get("issuer"),
            }
            self._redis_set(cache_key, result, self.WELLKNOWN_TTL)
            return result
        except Exception as e:
            logger.error(f"Failed to fetch OIDC discovery from {well_known_url}: {e}")
            return None

    # ── Email discovery ────────────────────────────────────────────────

    def discover_email(self, email: str) -> dict:
        """Given an email, return the org's auth method and SSO provider info."""
        default_response = {
            "auth_method": "password",
            "sso_provider": None,
            "sso_provider_name": None,
        }

        # ROOT user always gets password auth
        if email and email.strip().lower() == os.getenv("PLATFORM_ROOT_USER", "").strip().lower():
            return default_response

        org_schema = get_user_schema(email)
        if not org_schema:
            return default_response

        auth_config = self._get_auth_config(org_schema)
        if not auth_config:
            return default_response

        auth_method = auth_config.get("auth_method", "password")
        if auth_method == "password":
            return default_response

        return {
            "auth_method": auth_method,
            "sso_provider": auth_config.get("sso_provider"),
            "sso_provider_name": auth_config.get("sso_provider_name"),
        }

    # ── Build authorize URL ────────────────────────────────────────────

    def build_authorize_url(self, email: str, provider: str) -> str:
        """Generate state, store in Redis, build and return the IdP authorization URL."""
        org_schema = get_user_schema(email)
        if not org_schema:
            raise ValueError("User not found")

        auth_config = self._get_auth_config(org_schema)
        if not auth_config:
            raise ValueError("SSO not configured for this organization")

        client_id = auth_config.get("sso_client_id")
        if not client_id:
            raise ValueError("SSO client_id not configured")

        # Generate and store state
        state = secrets.token_urlsafe(32)
        self._redis_set(f"{self.STATE_PREFIX}{state}", {
            "provider": provider,
            "email": email,
            "org_schema": org_schema,
        }, self.STATE_TTL)

        redirect_uri = f"{self.backend_url}/auth/sso/callback"
        scopes = auth_config.get("sso_scopes", "openid email profile")

        # Build authorization URL based on provider
        well_known = self.get_well_known_config(auth_config, org_schema)

        if provider == "microsoft":
            tenant_id = auth_config.get("sso_tenant_id", "common")
            authorize_url = (
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
            )
        elif provider == "google":
            authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
        elif provider == "oidc" and well_known:
            authorize_url = well_known.get("authorization_endpoint")
            if not authorize_url:
                raise ValueError("OIDC authorization_endpoint not found in discovery")
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
        }

        # Google-specific params
        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "select_account"

        return f"{authorize_url}?{urlencode(params)}"

    # ── Handle IdP callback ────────────────────────────────────────────

    def handle_callback(self, code: str, state: str) -> dict:
        """Process IdP callback: validate state, exchange code, generate app tokens.

        Returns:
            dict with 'sso_code' and 'redirect_url' on success,
            or 'error' and 'redirect_url' on failure.
        """
        frontend_callback = f"{self.frontend_url}/sso-complete"

        # 1. Validate state (single-use)
        state_data = self._redis_get_and_delete(f"{self.STATE_PREFIX}{state}")
        if not state_data:
            return {
                "error": "invalid_state",
                "redirect_url": f"{frontend_callback}?error=invalid_state",
            }

        provider = state_data["provider"]
        discovery_email = state_data["email"]
        org_schema = state_data["org_schema"]

        # 2. Read SSO config
        auth_config = self._get_auth_config(org_schema)
        if not auth_config:
            return {
                "error": "sso_not_configured",
                "redirect_url": f"{frontend_callback}?error=sso_not_configured",
            }

        # 3. Exchange IdP code for IdP tokens
        try:
            idp_result = self._exchange_idp_code(
                code, provider, auth_config, org_schema
            )
        except Exception as e:
            logger.error(f"IdP code exchange failed: {e}")
            return {
                "error": "token_exchange_failed",
                "redirect_url": f"{frontend_callback}?error=token_exchange_failed",
            }

        # 4. Extract email from IdP response
        idp_email = idp_result.get("email")
        if not idp_email:
            logger.error("No email found in IdP response")
            return {
                "error": "no_email",
                "redirect_url": f"{frontend_callback}?error=no_email",
            }
        idp_email = idp_email.strip().lower()

        # 5. Validate email matches discovery email
        if discovery_email and idp_email != discovery_email.strip().lower():
            logger.warning(
                f"Email mismatch: discovery={discovery_email}, idp={idp_email}"
            )
            return {
                "error": "email_mismatch",
                "redirect_url": f"{frontend_callback}?error=email_mismatch",
            }

        # 6. Look up user in the org schema
        with set_schema(org_schema) as db:
            user_repo = UserRepository(db)
            user = user_repo.get_user_by_id(idp_email)

            if not user:
                return {
                    "error": "user_not_found",
                    "redirect_url": f"{frontend_callback}?error=user_not_found",
                }

            if user.account_status != "active":
                return {
                    "error": "account_inactive",
                    "redirect_url": f"{frontend_callback}?error=account_inactive",
                }

            # 7. Generate platform app tokens, store auth record, update last_login
            access_token, refresh_token = self.authentication.create_user_session(
                user, db, org_schema
            )

        # 9. Generate one-time sso_code and store in Redis
        sso_code = secrets.token_urlsafe(48)
        self._redis_set(f"{self.CODE_PREFIX}{sso_code}", {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_uuid": str(user.id),
        }, self.CODE_TTL)

        return {
            "sso_code": sso_code,
            "redirect_url": f"{frontend_callback}?code={sso_code}",
        }

    # ── Exchange one-time code ─────────────────────────────────────────

    def exchange_code(self, code: str) -> Optional[dict]:
        """Exchange a one-time sso_code for app tokens. Returns None if invalid."""
        return self._redis_get_and_delete(f"{self.CODE_PREFIX}{code}")

    # ── IdP code exchange (provider-specific) ──────────────────────────

    def _exchange_idp_code(
        self, code: str, provider: str, auth_config: dict, org_schema: str
    ) -> dict:
        """Exchange IdP authorization code for tokens and extract user email.

        Returns:
            dict with 'email' key (and optionally 'name').
        """
        if provider == "microsoft":
            return self._exchange_microsoft(code, auth_config)
        elif provider == "google":
            return self._exchange_google(code, auth_config, org_schema)
        elif provider == "oidc":
            return self._exchange_oidc(code, auth_config, org_schema)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _exchange_microsoft(self, code: str, auth_config: dict) -> dict:
        """Use MSAL to exchange code and extract email from Microsoft ID token."""
        client_id = auth_config["sso_client_id"]
        client_secret = self._get_client_secret(auth_config)
        tenant_id = auth_config.get("sso_tenant_id", "common")

        authority = f"https://login.microsoftonline.com/{tenant_id}"
        redirect_uri = f"{self.backend_url}/auth/sso/callback"

        app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )

        # MSAL adds openid/profile/email automatically — only pass resource scopes
        result = app.acquire_token_by_authorization_code(
            code,
            scopes=["User.Read"],
            redirect_uri=redirect_uri,
        )

        if "error" in result:
            raise ValueError(
                f"MSAL error: {result.get('error_description', result.get('error'))}"
            )

        # Extract email from ID token claims
        id_token_claims = result.get("id_token_claims", {})
        email = (
            id_token_claims.get("preferred_username")
            or id_token_claims.get("mail")
            or id_token_claims.get("upn")
            or id_token_claims.get("email")
        )

        return {
            "email": email,
            "name": id_token_claims.get("name"),
        }

    def _exchange_google(self, code: str, auth_config: dict, org_schema: str) -> dict:
        """Exchange Google authorization code and validate ID token."""
        return self._exchange_standard_oidc(code, auth_config, org_schema)

    def _exchange_oidc(self, code: str, auth_config: dict, org_schema: str) -> dict:
        """Exchange custom OIDC authorization code and validate ID token."""
        return self._exchange_standard_oidc(code, auth_config, org_schema)

    def _exchange_standard_oidc(
        self, code: str, auth_config: dict, org_schema: str
    ) -> dict:
        """Standard OIDC code exchange for Google and custom OIDC providers."""
        client_id = auth_config["sso_client_id"]
        client_secret = self._get_client_secret(auth_config)
        redirect_uri = f"{self.backend_url}/auth/sso/callback"

        well_known = self.get_well_known_config(auth_config, org_schema)
        if not well_known:
            raise ValueError("Could not fetch OIDC discovery document")

        token_endpoint = well_known["token_endpoint"]
        jwks_uri = well_known["jwks_uri"]
        issuer = well_known["issuer"]

        # Exchange code for tokens
        with httpx.Client(timeout=15) as client:
            token_resp = client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

        id_token = token_data.get("id_token")
        if not id_token:
            raise ValueError("No id_token in token response")

        # Fetch JWKS and validate ID token
        with httpx.Client(timeout=10) as client:
            jwks_resp = client.get(jwks_uri)
            jwks_resp.raise_for_status()
            jwks_data = jwks_resp.json()

        # Decode and validate the ID token
        signing_key = self._get_signing_key(jwks_data, id_token)

        # Google's issuer can be "accounts.google.com" or "https://accounts.google.com"
        valid_issuers = [issuer]
        if "accounts.google.com" in issuer:
            valid_issuers = ["https://accounts.google.com", "accounts.google.com"]

        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=valid_issuers,
            options={"verify_exp": True},
        )

        # Extract email
        email = (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
        )

        return {
            "email": email,
            "name": claims.get("name"),
        }

    def _get_signing_key(self, jwks_data: dict, token: str):
        """Find the correct signing key from JWKS for the given token."""
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        for key in jwks_data.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))

        raise ValueError(f"Signing key not found for kid: {kid}")

    # ── Teams silent auth ───────────────────────────────────────────────

    def authenticate_teams_token(self, teams_token: str) -> dict:
        """Validate a Microsoft Teams SSO token and return app tokens.

        Returns:
            dict with 'user_uuid', 'access_token', 'refresh_token' on success.
        Raises:
            ValueError on invalid token or user not found.
        """
        # 1. Fetch Microsoft JWKS and validate the token
        try:
            unverified_claims = jwt.decode(teams_token, options={"verify_signature": False})
            platform_client_id = os.getenv("CLIENT_ID")

            with httpx.Client(timeout=10) as client:
                jwks_resp = client.get(self.MICROSOFT_JWKS_URL)
                jwks_resp.raise_for_status()
                jwks_data = jwks_resp.json()

            signing_key = self._get_signing_key(jwks_data, teams_token)
            # Teams tokens use Application ID URI as audience (api://host/client_id)
            token_aud = unverified_claims.get("aud", "")
            valid_audiences = [
                platform_client_id,
                f"api://{platform_client_id}",
            ]
            # Also accept the full URI if it contains the client_id
            if platform_client_id in token_aud:
                valid_audiences.append(token_aud)

            claims = jwt.decode(
                teams_token,
                signing_key,
                algorithms=["RS256"],
                audience=valid_audiences,
                options={"verify_exp": True, "verify_iss": False},
            )
        except jwt.ExpiredSignatureError:
            raise ValueError("Teams token has expired")
        except Exception as e:
            raise ValueError(f"Invalid Teams token: {e}")

        # 2. Extract email
        email = (
            claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("email")
        )
        if not email:
            raise ValueError("No email found in Teams token")
        email = email.strip().lower()

        # 3. Find user and create session
        org_schema = get_user_schema(email)
        if not org_schema:
            raise ValueError("User not found")

        with set_schema(org_schema) as db:
            user = UserRepository(db).get_user_by_id(email)
            if not user:
                raise ValueError("User not found")
            if user.account_status != "active":
                raise ValueError("Account is inactive")

            access_token, refresh_token = self.authentication.create_user_session(
                user, db, org_schema
            )

            return {
                "user_uuid": str(user.id),
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

    # ── Settings management ────────────────────────────────────────────

    def get_settings(self, db) -> dict:
        """Read auth_config from Configuration and return sanitized response."""
        config_repo = ConfigurationRepository(db)
        config = config_repo.get_configuration()

        auth_config = config.auth_config if config else None
        callback_url = f"{self.backend_url}/auth/sso/callback"

        if not auth_config:
            return {
                "auth_method": "password",
                "sso_provider": None,
                "sso_provider_name": None,
                "sso_client_id": None,
                "sso_tenant_id": None,
                "sso_well_known_url": None,
                "sso_scopes": "openid email profile",
                "client_secret_set": False,
                "callback_url": callback_url,
            }

        return {
            "auth_method": auth_config.get("auth_method", "password"),
            "sso_provider": auth_config.get("sso_provider"),
            "sso_provider_name": auth_config.get("sso_provider_name"),
            "sso_client_id": auth_config.get("sso_client_id"),
            "sso_tenant_id": auth_config.get("sso_tenant_id"),
            "sso_well_known_url": auth_config.get("sso_well_known_url"),
            "sso_scopes": auth_config.get("sso_scopes", "openid email profile"),
            "client_secret_set": bool(
                auth_config.get("sso_client_secret_encrypted")
            ),
            "callback_url": callback_url,
        }

    def update_settings(self, db, update_data: dict) -> dict:
        """Update auth_config on the Configuration model."""
        config_repo = ConfigurationRepository(db)
        config = config_repo.get_configuration()
        current_auth_config = dict(config.auth_config) if config and config.auth_config else {}

        # Merge update into current config
        for key in (
            "auth_method", "sso_provider", "sso_provider_name",
            "sso_client_id", "sso_tenant_id", "sso_well_known_url", "sso_scopes",
        ):
            if key in update_data and update_data[key] is not None:
                current_auth_config[key] = update_data[key]

        # Handle client secret — encrypt before storing
        if update_data.get("sso_client_secret"):
            current_auth_config["sso_client_secret_encrypted"] = encrypt_string(
                update_data["sso_client_secret"]
            )

        # Clear SSO fields when switching to password-only
        if current_auth_config.get("auth_method") == "password":
            current_auth_config = {"auth_method": "password"}

        # Validate the merged config before saving
        self._validate_auth_config(current_auth_config)

        # Verify credentials work against the IdP
        self._verify_sso_credentials(current_auth_config)

        # Upsert configuration
        result = config_repo.create_or_update_configuration(
            {"auth_config": current_auth_config}
        )

        if not result:
            raise ValueError("Failed to save authentication settings")

        return self.get_settings(db)

    def _validate_auth_config(self, config: dict):
        """Validate that SSO config is complete when auth_method requires it."""
        auth_method = config.get("auth_method", "password")

        if auth_method == "password":
            return

        # SSO or flexible — require provider and credentials
        provider = config.get("sso_provider")
        if not provider:
            raise ValueError("sso_provider is required when auth_method is 'sso' or 'flexible'")

        if not config.get("sso_client_id"):
            raise ValueError("sso_client_id is required for SSO")

        if not config.get("sso_client_secret_encrypted"):
            raise ValueError("sso_client_secret is required for SSO")

        if provider == "microsoft" and not config.get("sso_tenant_id"):
            raise ValueError("sso_tenant_id is required for Microsoft provider")

        if provider == "oidc":
            if not config.get("sso_well_known_url"):
                raise ValueError("sso_well_known_url is required for custom OIDC provider")
            if not config.get("sso_provider_name"):
                raise ValueError("sso_provider_name is required for custom OIDC provider")

    def _verify_sso_credentials(self, config: dict):
        """Test SSO credentials against the IdP to verify they are valid."""
        auth_method = config.get("auth_method", "password")
        if auth_method == "password":
            return

        provider = config.get("sso_provider")
        client_id = config.get("sso_client_id")
        client_secret = self._get_client_secret(config)

        if provider == "microsoft":
            self._verify_microsoft_credentials(client_id, client_secret, config.get("sso_tenant_id"))
        elif provider in ("google", "oidc"):
            self._verify_oidc_credentials(client_id, client_secret, config)

    def _verify_microsoft_credentials(self, client_id: str, client_secret: str, tenant_id: str):
        """Verify Microsoft credentials using MSAL client credentials flow."""
        try:
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            app = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=client_secret,
            )
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            if "error" in result:
                raise ValueError(
                    f"Microsoft SSO verification failed: {result.get('error_description', result.get('error'))}"
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Microsoft SSO verification failed: {e}")

    def _verify_oidc_credentials(self, client_id: str, client_secret: str, config: dict):
        """Verify Google/OIDC credentials by fetching discovery doc and testing token endpoint."""
        well_known_url = self._get_well_known_url(config)
        if not well_known_url:
            raise ValueError("Could not determine well-known URL for verification")

        try:
            with httpx.Client(timeout=10) as client:
                # Verify discovery URL is reachable
                discovery_resp = client.get(well_known_url)
                discovery_resp.raise_for_status()
                discovery = discovery_resp.json()

                token_endpoint = discovery.get("token_endpoint")
                if not token_endpoint:
                    raise ValueError("OIDC discovery document missing token_endpoint")

                # Test client credentials against token endpoint
                token_resp = client.post(
                    token_endpoint,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "openid",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                # 401/403 = invalid credentials, other errors may be grant_type not supported
                if token_resp.status_code in (401, 403):
                    raise ValueError("SSO verification failed: invalid client_id or client_secret")

                # Some providers don't support client_credentials grant but the discovery URL
                # being reachable and returning valid endpoints is a good enough signal
        except ValueError:
            raise
        except httpx.HTTPStatusError as e:
            raise ValueError(f"SSO verification failed: could not reach discovery URL ({e.response.status_code})")
        except Exception as e:
            raise ValueError(f"SSO verification failed: {e}")


# Module-level singleton
sso_service = SSOService()
