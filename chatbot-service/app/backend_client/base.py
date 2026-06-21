"""HTTP client to Nicholas's FastAPI backend.

Two defensive measures baked in (PROMPT rule #2):

1. We never hardcode a single raw path. The backend currently has a
   double-prefix routing bug (e.g. the products list lives at
   `/products/products/`, not `/products/`). Each call passes a list of
   *candidate* paths — clean first, doubled as fallback — and we cache whichever
   one actually responds, so this keeps working once the bug is fixed.
2. The base URL is config-driven (`BACKEND_BASE_URL`).
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self) -> None:
        self._base = settings.backend_base_url.rstrip("/")
        self._timeout = settings.backend_request_timeout_seconds
        # Service-to-service auth header (backend's require_service_key).
        self._headers = (
            {"X-Service-Key": settings.backend_service_api_key}
            if settings.backend_service_api_key
            else {}
        )
        # Cache: candidate-tuple -> resolved working path.
        self._resolved: dict[tuple[str, ...], str] = {}

    async def get_first_ok(
        self, candidates: list[str], params: dict | None = None
    ) -> httpx.Response | None:
        """Try candidate paths in order; return the first non-404 response.

        Returns None if every candidate 404s or the backend is unreachable.
        """
        key = tuple(candidates)
        if key in self._resolved:
            candidates = [self._resolved[key]]

        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            last_exc: Exception | None = None
            for path in candidates:
                url = f"{self._base}{path}"
                try:
                    resp = await client.get(url, params=params)
                except httpx.HTTPError as exc:  # connection/timeout
                    last_exc = exc
                    logger.warning("Backend unreachable at %s: %s", url, exc)
                    continue
                if resp.status_code == 404:
                    logger.debug("Backend 404 at %s, trying next candidate", url)
                    continue
                self._resolved[key] = path
                return resp
            if last_exc:
                logger.error("Backend request failed for all candidates: %s", candidates)
            return None


backend_client = BackendClient()
