import slim_bindings
from typing import Tuple

def create_shared_secret_auth(identity: str, secret: str) -> Tuple[slim_bindings.IdentityProvider, slim_bindings.IdentityVerifier]:
    provider = slim_bindings.IdentityProvider.SharedSecret(
        identity=identity,
        shared_secret=secret
    )
    verifier = slim_bindings.IdentityVerifier.SharedSecret(
        identity=identity,
        shared_secret=secret
    )
    return provider, verifier

def create_jwt_auth(jwt_path: str, iss: str, sub: str, aud: str, public_key: slim_bindings.Key) -> Tuple[slim_bindings.IdentityProvider, slim_bindings.IdentityVerifier]:
    provider = slim_bindings.IdentityProvider.StaticJwt(path=jwt_path)
    verifier = slim_bindings.IdentityVerifier.Jwt(
        public_key=public_key,
        issuer=iss,
        audience=[aud],
        subject=sub
    )
    return provider, verifier
