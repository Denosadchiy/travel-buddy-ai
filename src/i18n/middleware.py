"""
FastAPI middleware for language detection and context setup.

Reads language from request headers and sets LocaleContext for the duration
of the request.
"""

from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.auth.jwt import verify_token, TokenExpiredError, TokenInvalidError
from src.config import settings
from src.i18n.locale import (
    SupportedLanguage,
    LocaleContext,
    LocaleResolution,
    resolve_language,
)


class LocaleMiddleware(BaseHTTPMiddleware):
    """
    Middleware to detect and set request language.

    Language detection priority:
    1. Profile locale:
       - access token claim `locale` (if present)
       - X-User-Language header (optional profile locale from client)
    2. `lang` query parameter
    3. X-Language header (explicit app setting from iOS/Android)
    4. Accept-Language header (browser/system preference)
    5. Global fallback language

    The resolved locale is stored in:
    - LocaleContext (thread-local/async-safe context variable)
    - request.state.language (for direct access in endpoints)
    - request.state.resolved_locale (resolved locale code)
    - request.state.locale_source (which source won)
    - request.state.locale_is_fallback (whether fallback was used)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        resolution = self._resolve_language(request)
        language = resolution.language

        # Set context for this request
        LocaleContext.set(language)

        # Also store resolution on request state for direct access
        request.state.language = language
        request.state.resolved_locale = language.value
        request.state.locale_source = resolution.source
        request.state.locale_is_fallback = resolution.is_fallback

        try:
            response = await call_next(request)
            # Expose locale resolution metadata in response headers
            response.headers["Content-Language"] = language.value
            response.headers["X-Resolved-Locale"] = language.value
            response.headers["X-Locale-Source"] = resolution.source
            response.headers["X-Locale-Is-Fallback"] = (
                "true" if resolution.is_fallback else "false"
            )
            return response
        finally:
            # Reset context after request
            LocaleContext.reset()

    @staticmethod
    def _fallback_language() -> SupportedLanguage:
        return SupportedLanguage.from_code(
            settings.i18n_fallback_language,
            fallback=SupportedLanguage.ENGLISH,
        )

    @staticmethod
    def _extract_profile_locale_from_access_token(request: Request) -> Optional[str]:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None

        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            return None

        try:
            payload = verify_token(token, expected_type="access")
            claim_locale = payload.get("locale") or payload.get("lang")
            if isinstance(claim_locale, str):
                return claim_locale
        except (TokenExpiredError, TokenInvalidError, ValueError):
            return None

        return None

    def _resolve_language(self, request: Request) -> LocaleResolution:
        """
        Resolve language from request data with explicit precedence.

        Args:
            request: FastAPI/Starlette request object

        Returns:
            LocaleResolution metadata
        """
        profile_from_token = self._extract_profile_locale_from_access_token(request)
        profile_from_header = request.headers.get("X-User-Language")
        profile_locale = profile_from_token or profile_from_header
        query_locale = request.query_params.get("lang")
        explicit_locale = request.headers.get("X-Language")
        accept_language = request.headers.get("Accept-Language")

        return resolve_language(
            fallback_language=self._fallback_language(),
            profile_locale=profile_locale,
            query_locale=query_locale,
            explicit_locale=explicit_locale,
            accept_language=accept_language,
        )
