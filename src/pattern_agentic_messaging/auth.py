import slim_bindings
from typing import Optional, Tuple

_AuthPair = Tuple[slim_bindings.IdentityProvider, slim_bindings.IdentityVerifier]

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
    verifier = slim_bindings.IdentityVerifier.Jwt(
        public_key=None,
        autoresolve=jwks_url is not None,
        issuer=issuer,
        audience=audience,
        subject=subject,
    )
    return provider, verifier
