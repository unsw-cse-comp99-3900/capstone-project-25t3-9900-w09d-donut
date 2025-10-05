import pytest

from server import create_app


@pytest.fixture
def app():
    return create_app("testing")


@pytest.fixture
def client(app):
    return app.test_client()


def test_healthcheck(client):
    # TODO: Expand coverage once endpoints are implemented
    response = client.get("/api/health")
    assert response.status_code == 200
