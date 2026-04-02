from __future__ import annotations

import base64
import json
from datetime import timedelta
from typing import Any, Optional, Tuple

from pydantic import BaseModel
from slim_bindings import (
    IdentityProviderConfig,
    IdentityVerifierConfig,
    JwtAlgorithm,
    JwtAuth,
    JwtKeyConfig,
    JwtKeyData,
    JwtKeyFormat,
    JwtKeyType,
    StaticJwtAuth,
)

from .exceptions import AuthenticationError

_AuthPair = Tuple[IdentityProviderConfig, IdentityVerifierConfig]

_STANDARD_CLAIMS = frozenset({"iss", "sub", "aud", "exp", "nbf", "iat", "jti"})
_DEFAULT_DURATION = timedelta(seconds=3600)


class JWTClaims(BaseModel):
    iss: Optional[str] = None
    sub: Optional[str] = None
    aud: Optional[str | list[str]] = None
    exp: Optional[int] = None
    nbf: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None
    extra: dict[str, Any] = {}

    @classmethod
    def from_token(cls, token: str) -> JWTClaims:
        payload_segment = token.split(".")[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        standard = {k: payload.pop(k) for k in list(payload) if k in _STANDARD_CLAIMS}
        return cls(**standard, extra=payload)


def create_none_auth() -> _AuthPair:
    return IdentityProviderConfig.NONE(), IdentityVerifierConfig.NONE()


def create_shared_secret_auth(identity: str, secret: str) -> _AuthPair:
    provider = IdentityProviderConfig.SHARED_SECRET(id=identity, data=secret)
    verifier = IdentityVerifierConfig.SHARED_SECRET(id=identity, data=secret)
    return provider, verifier


def _fetch_jwks(url: str) -> str:
    import httpx
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        raise AuthenticationError(f"Failed to fetch JWKS from {url}: {e}")


def create_jwt_auth(
    token_path: str,
    *,
    jwks_url: Optional[str] = None,
    jwks_content: Optional[str] = None,
    issuer: Optional[str] = None,
    audience: Optional[list[str]] = None,
    subject: Optional[str] = None,
    duration: timedelta = _DEFAULT_DURATION,
) -> _AuthPair:
    provider = IdentityProviderConfig.STATIC_JWT(
        config=StaticJwtAuth(token_file=token_path, duration=duration)
    )

    if jwks_content:
        key_data = jwks_content
    elif jwks_url:
        key_data = _fetch_jwks(jwks_url)
    else:
        raise AuthenticationError("Either jwks_url or jwks_content must be provided for JWT auth")

    key = JwtKeyType.DECODING(
        key=JwtKeyConfig(
            algorithm=JwtAlgorithm.RS256,
            format=JwtKeyFormat.JWKS,
            key=JwtKeyData.DATA(key_data),
        )
    )
    verifier = IdentityVerifierConfig.JWT(
        config=JwtAuth(
            key=key,
            audience=audience,
            issuer=issuer,
            subject=subject,
            duration=duration,
        )
    )
    return provider, verifier
