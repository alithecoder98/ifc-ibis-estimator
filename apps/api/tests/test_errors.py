"""Unit tests for the uniform {"error": {"code", "message"}} error shape.

Uses a small isolated FastAPI app (not app.main) so these stay unit tests, independent
of any real route or infra.
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers


def _make_test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise HTTPException(status_code=404, detail="not found here")

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("something broke")

    return app


client = TestClient(_make_test_app(), raise_server_exceptions=False)


def test_http_exception_has_uniform_shape() -> None:
    response = client.get("/boom")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "not found here"}
    }


def test_unhandled_exception_has_uniform_shape() -> None:
    response = client.get("/crash")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }


def test_route_not_found_has_uniform_shape() -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
