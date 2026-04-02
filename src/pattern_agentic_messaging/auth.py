from __future__ import annotations

import base64
import json
from typing import Any, Optional, Tuple

import slim_bindings
from pydantic import BaseModel

_AuthPair = Tuple[slim_bindings.IdentityProvider, slim_bindings.IdentityVerifier]

_STANDARD_CLAIMS = frozenset({"iss", "sub", "aud", "exp", "nbf", "iat", "jti"})


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

_NONE_AUTH_SENTINEL = "pa-messaging-no-auth-00000000000"


def create_none_auth(identity: str) -> _AuthPair:
    provider = slim_bindings.IdentityProvider.SharedSecret(
        identity=identity,
        shared_secret=_NONE_AUTH_SENTINEL,
    )
    verifier = slim_bindings.IdentityVerifier.SharedSecret(
        identity=identity,
        shared_secret=_NONE_AUTH_SENTINEL,
    )
    return provider, verifier


def create_shared_secret_auth(identity: str, secret: str) -> _AuthPair:
    provider = slim_bindings.IdentityProvider.SharedSecret(
        identity=identity,
        shared_secret=secret,
    )
    verifier = slim_bindings.IdentityVerifier.SharedSecret(
        identity=identity,
        shared_secret=secret,
    )
    return provider, verifier


def create_jwt_auth(
    token_path: str,
    *,
    jwks_url: Optional[str] = None,
    issuer: Optional[str] = None,
    audience: Optional[list[str]] = None,
    subject: Optional[str] = None,
) -> _AuthPair:
    provider = slim_bindings.IdentityProvider.StaticJwt(path=token_path)
    placeholder_key = slim_bindings.Key(
        key=slim_bindings.KeyData.Content('{"keys":[]}'),
        format=slim_bindings.KeyFormat.Jwks,
        algorithm=slim_bindings.Algorithm.RS256,
    )
    verifier = slim_bindings.IdentityVerifier.Jwt(
        public_key=placeholder_key,
        autoresolve=True,
        issuer=issuer,
        audience=audience,
        subject=subject,
    )
    return provider, verifier
