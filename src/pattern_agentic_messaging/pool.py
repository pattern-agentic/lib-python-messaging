from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Optional

from .app import PASlimApp
from .config import PASlimConfig

logger = logging.getLogger(__name__)


class SlimConnectionPool:

    def __init__(self, endpoint: str, **config_kwargs):
        self._template = PASlimConfig(local_name="", endpoint=endpoint, **config_kwargs)
        self._apps: dict[str, PASlimApp] = {}
        self._refcounts: dict[str, int] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def with_no_auth(self) -> SlimConnectionPool:
        self._template.with_no_auth()
        return self

    def with_shared_secret(self, secret: str) -> SlimConnectionPool:
        self._template.with_shared_secret(secret)
        return self

    def with_jwt_auth(
        self,
        token_path: str,
        *,
        jwks_url: Optional[str] = None,
        jwks_content: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[list[str]] = None,
        subject: Optional[str] = None,
    ) -> SlimConnectionPool:
        self._template.with_jwt_auth(
            token_path, jwks_url=jwks_url, issuer=issuer,
            audience=audience, subject=subject,
        )
        self._template.jwt_jwks_content = jwks_content
        return self

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def acquire(self, key: str, local_name: str) -> PASlimApp:
        lock = await self._get_lock(key)

        async with lock:
            if key not in self._apps:
                config = replace(self._template, local_name=local_name)
                app = PASlimApp(config)
                await app.__aenter__()
                self._apps[key] = app
                self._refcounts[key] = 0
                logger.info(f"SLIM pool connection opened: key={key} name={local_name}")

            self._refcounts[key] += 1
            return self._apps[key]

    async def release(self, key: str) -> None:
        lock = await self._get_lock(key)

        async with lock:
            if key not in self._apps:
                return

            self._refcounts[key] = max(0, self._refcounts[key] - 1)

            if self._refcounts[key] > 0:
                return

            app = self._apps.pop(key)
            self._refcounts.pop(key, None)

            try:
                await app.__aexit__(None, None, None)
                logger.info(f"SLIM pool connection closed: key={key}")
            except Exception as e:
                logger.warning(f"SLIM pool disconnect failed: key={key} error={e}")

        async with self._global_lock:
            if key in self._locks and key not in self._apps:
                del self._locks[key]

    async def shutdown(self) -> None:
        async with self._global_lock:
            keys = list(self._apps.keys())

        for key in keys:
            app = self._apps.pop(key, None)
            if app:
                try:
                    await app.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"SLIM pool shutdown error: key={key} error={e}")

        self._refcounts.clear()
        self._locks.clear()
        logger.info("SLIM connection pool shut down")
