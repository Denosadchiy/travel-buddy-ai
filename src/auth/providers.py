"""
Authentication provider implementations for Apple, Google, and Email OTP.
"""
import httpx
import jwt
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.auth.config import auth_settings


class ProviderError(Exception):
    """Base exception for provider-related errors."""
    pass


class TokenVerificationError(ProviderError):
    """Token verification failed."""
    pass


# =============================================================================
# Apple Sign-In Provider
# =============================================================================

class AppleProvider:
    """
    Apple Sign-In token verification.
    Validates Apple ID tokens using Apple's public keys (JWKS).
    """

    APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
    APPLE_ISSUER = "https://appleid.apple.com"

    def __init__(self):
        self._jwks_cache: Optional[Dict] = None
        self._jwks_cache_time: Optional[datetime] = None

    async def _get_apple_public_keys(self) -> Dict:
        """Fetch Apple's public keys with caching."""
        # Cache keys for 1 hour
        if self._jwks_cache and self._jwks_cache_time:
            if datetime.utcnow() - self._jwks_cache_time < timedelta(hours=1):
                return self._jwks_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.APPLE_JWKS_URL)
            response.raise_for_status()
            self._jwks_cache = response.json()
            self._jwks_cache_time = datetime.utcnow()
            return self._jwks_cache

    async def verify_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify an Apple ID token and return the claims.

        Args:
            id_token: The Apple ID token from Sign in with Apple

        Returns:
            Token claims including 'sub' (Apple user ID) and optional 'email'

        Raises:
            TokenVerificationError: If token is invalid
        """
        try:
            # Get Apple's public keys
            jwks = await self._get_apple_public_keys()

            # Decode header to get key ID
            header = jwt.get_unverified_header(id_token)
            kid = header.get("kid")

            if not kid:
                raise TokenVerificationError("Token missing key ID")

            # Find matching public key
            public_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                    break

            if not public_key:
                raise TokenVerificationError("Public key not found")

            # Verify and decode token
            claims = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=auth_settings.apple_client_id,
                issuer=self.APPLE_ISSUER,
            )

            return {
                "sub": claims["sub"],  # Apple's unique user ID
                "email": claims.get("email"),
                "email_verified": claims.get("email_verified", False),
            }

        except jwt.ExpiredSignatureError:
            raise TokenVerificationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenVerificationError(f"Invalid token: {str(e)}")
        except Exception as e:
            raise TokenVerificationError(f"Token verification failed: {str(e)}")


# =============================================================================
# Google Sign-In Provider
# =============================================================================

class GoogleProvider:
    """
    Google Sign-In token verification.
    Validates Google ID tokens using Google's public keys.
    """

    GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
    GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"]

    def __init__(self):
        self._jwks_cache: Optional[Dict] = None
        self._jwks_cache_time: Optional[datetime] = None

    async def _get_google_public_keys(self) -> Dict:
        """Fetch Google's public keys with caching."""
        # Cache keys for 1 hour
        if self._jwks_cache and self._jwks_cache_time:
            if datetime.utcnow() - self._jwks_cache_time < timedelta(hours=1):
                return self._jwks_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.GOOGLE_CERTS_URL)
            response.raise_for_status()
            self._jwks_cache = response.json()
            self._jwks_cache_time = datetime.utcnow()
            return self._jwks_cache

    async def verify_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify a Google ID token and return the claims.

        Args:
            id_token: The Google ID token from Google Sign-In

        Returns:
            Token claims including 'sub' (Google user ID), 'email', 'name', 'picture'

        Raises:
            TokenVerificationError: If token is invalid
        """
        try:
            # Get Google's public keys
            jwks = await self._get_google_public_keys()

            # Decode header to get key ID
            header = jwt.get_unverified_header(id_token)
            kid = header.get("kid")

            if not kid:
                raise TokenVerificationError("Token missing key ID")

            # Find matching public key
            public_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                    break

            if not public_key:
                raise TokenVerificationError("Public key not found")

            # Get expected audiences (iOS client ID and optionally web client ID)
            audiences = [auth_settings.google_client_id]
            if auth_settings.google_client_id_web:
                audiences.append(auth_settings.google_client_id_web)

            # Verify and decode token
            claims = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=audiences,
                issuer=self.GOOGLE_ISSUERS,
            )

            return {
                "sub": claims["sub"],  # Google's unique user ID
                "email": claims.get("email"),
                "email_verified": claims.get("email_verified", False),
                "name": claims.get("name"),
                "picture": claims.get("picture"),
            }

        except jwt.ExpiredSignatureError:
            raise TokenVerificationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenVerificationError(f"Invalid token: {str(e)}")
        except Exception as e:
            raise TokenVerificationError(f"Token verification failed: {str(e)}")


# =============================================================================
# Email OTP Provider
# =============================================================================

class EmailOTPProvider:
    """
    Email OTP (One-Time Password) provider for passwordless email authentication.
    """

    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP code."""
        return ''.join(secrets.choice('0123456789') for _ in range(length))

    def hash_otp(self, code: str) -> str:
        """Hash an OTP code for storage."""
        return hashlib.sha256(code.encode()).hexdigest()

    def verify_otp(self, code: str, code_hash: str) -> bool:
        """Verify an OTP code against its hash."""
        return self.hash_otp(code) == code_hash

    async def send_otp_email(self, email: str, code: str) -> bool:
        """
        Send an OTP email to the user.

        Args:
            email: Recipient email address
            code: OTP code to send

        Returns:
            True if email was sent successfully (or logged in dev mode)
        """
        if auth_settings.otp_dev_mode:
            # Development mode: just log the code
            print(f"[DEV MODE] OTP for {email}: {code}")
            return True

        if not auth_settings.smtp_host or not auth_settings.smtp_user:
            raise ProviderError("SMTP not configured")

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Your Travel Buddy login code: {code}"
            msg["From"] = f"{auth_settings.smtp_from_name} <{auth_settings.smtp_from_email}>"
            msg["To"] = email

            # Plain text version
            text = f"""
Your Travel Buddy login code is: {code}

This code expires in {auth_settings.otp_expire_minutes} minutes.

If you didn't request this code, please ignore this email.
            """

            # HTML version
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 400px; margin: 0 auto; padding: 40px 20px; }}
        .code {{ font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #FF7043; text-align: center; padding: 20px; background: #FFF3E0; border-radius: 12px; margin: 20px 0; }}
        .footer {{ font-size: 14px; color: #666; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Your login code</h2>
        <div class="code">{code}</div>
        <p>Enter this code in the app to continue.</p>
        <p class="footer">This code expires in {auth_settings.otp_expire_minutes} minutes.<br>
        If you didn't request this code, please ignore this email.</p>
    </div>
</body>
</html>
            """

            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))

            # Send email (SSL or STARTTLS depending on config)
            if auth_settings.smtp_use_ssl:
                with smtplib.SMTP_SSL(auth_settings.smtp_host, auth_settings.smtp_port) as server:
                    server.login(auth_settings.smtp_user, auth_settings.smtp_password)
                    server.sendmail(auth_settings.smtp_from_email, email, msg.as_string())
            else:
                with smtplib.SMTP(auth_settings.smtp_host, auth_settings.smtp_port) as server:
                    server.starttls()
                    server.login(auth_settings.smtp_user, auth_settings.smtp_password)
                    server.sendmail(auth_settings.smtp_from_email, email, msg.as_string())

            return True

        except Exception as e:
            print(f"Failed to send OTP email: {e}")
            raise ProviderError(f"Failed to send email: {str(e)}")


# Global provider instances
apple_provider = AppleProvider()
google_provider = GoogleProvider()
email_otp_provider = EmailOTPProvider()
