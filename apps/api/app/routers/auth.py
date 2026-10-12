"""POST /auth/login, POST /auth/logout, GET /auth/me."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import COOKIE_NAME, get_current_user
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    settings = get_settings()
    token = create_access_token(user_id=user.id, role=user.role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
        max_age=settings.jwt_expires_minutes * 60,
    )
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
