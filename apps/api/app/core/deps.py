"""Auth dependencies: get_current_user reads the JWT from the httpOnly cookie;
require_role(...) builds a dependency that additionally checks the user's role.
"""

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token, hash_password
from app.db.models import User
from app.db.session import get_db

COOKIE_NAME = "access_token"

DEV_BYPASS_EMAIL = "dev@local.test"


def _get_or_create_dev_user(db: Session) -> User:
    user = db.query(User).filter(User.email == DEV_BYPASS_EMAIL).first()
    if user is None:
        user = User(
            email=DEV_BYPASS_EMAIL,
            password_hash=hash_password("not-a-real-password"),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    access_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    if get_settings().auth_disabled:
        return _get_or_create_dev_user(db)

    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    try:
        payload = decode_access_token(access_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found"
        )
    return user


def require_role(*roles: str):
    """Usage: Depends(require_role("admin")) or Depends(require_role("admin", "estimator"))."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        return user

    return dependency
