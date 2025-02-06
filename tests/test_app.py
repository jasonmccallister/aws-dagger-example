import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_api(client):
    response = client.get("/api")
    assert response.status_code == 200
    assert response.get_json() == {"message": "Hello, Flask!"}
