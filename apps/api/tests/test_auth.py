"""Sub-phase 1.5: auth + roles.

Login/logout/me are tested against the real app/DB (same pattern as test_health.py).
Role access is tested against a small isolated app (same pattern as test_errors.py) so
it doesn't depend on any real protected business route existing yet.
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.deps import require_role
from app.core.security import hash_password
from app.db.models import User
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _create_user(email: str, password: str, role: str) -> User:
    db = SessionLocal()
    user = User(email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def _delete_user(user_id: int) -> None:
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def test_login_success_sets_cookie_and_me_works() -> None:
    user = _create_user("estimator1@example.com", "correct-password", "estimator")
    try:
        login_response = client.post(
            "/auth/login", json={"email": user.email, "password": "correct-password"}
        )
        assert login_response.status_code == 200
        assert "access_token" in login_response.cookies
        body = login_response.json()
        assert body == {"id": user.id, "email": user.email, "role": "estimator"}

        me_response = client.get("/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["email"] == user.email
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def test_login_wrong_password_is_401() -> None:
    user = _create_user("estimator2@example.com", "correct-password", "estimator")
    try:
        response = client.post(
            "/auth/login", json={"email": user.email, "password": "wrong-password"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
    finally:
        _delete_user(user.id)


def test_me_without_cookie_is_401() -> None:
    client.cookies.clear()
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_logout_clears_cookie() -> None:
    user = _create_user("estimator3@example.com", "correct-password", "estimator")
    try:
        client.post(
            "/auth/login", json={"email": user.email, "password": "correct-password"}
        )
        assert client.get("/auth/me").status_code == 200

        logout_response = client.post("/auth/logout")
        assert logout_response.status_code == 200

        assert client.get("/auth/me").status_code == 401
    finally:
        client.cookies.clear()
        _delete_user(user.id)


def _make_role_test_app() -> FastAPI:
    test_app = FastAPI()

    @test_app.get("/admin-only")
    def admin_only(user: User = Depends(require_role("admin"))) -> dict:
        return {"ok": True}

    return test_app


def test_require_role_denies_wrong_role_allows_right_role() -> None:
    admin = _create_user("admin1@example.com", "pw", "admin")
    estimator = _create_user("estimator4@example.com", "pw", "estimator")
    viewer = _create_user("viewer1@example.com", "pw", "viewer")
    role_client = TestClient(_make_role_test_app())
    try:
        from app.core.security import create_access_token

        admin_token = create_access_token(user_id=admin.id, role=admin.role)
        estimator_token = create_access_token(user_id=estimator.id, role=estimator.role)
        viewer_token = create_access_token(user_id=viewer.id, role=viewer.role)

        role_client.cookies.set("access_token", admin_token)
        assert role_client.get("/admin-only").status_code == 200

        role_client.cookies.set("access_token", estimator_token)
        assert role_client.get("/admin-only").status_code == 403

        role_client.cookies.set("access_token", viewer_token)
        assert role_client.get("/admin-only").status_code == 403
    finally:
        _delete_user(admin.id)
        _delete_user(estimator.id)
        _delete_user(viewer.id)
