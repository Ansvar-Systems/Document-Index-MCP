import pytest
import base64
import os
from pathlib import Path

# Must set env BEFORE importing app
os.environ["DOCUMENT_INDEX_DB_PATH"] = "/tmp/test-doc-index-http.db"

from fastapi.testclient import TestClient
from document_index_mcp.http_server import app


@pytest.fixture(autouse=True)
def clean_db():
    db_path = Path("/tmp/test-doc-index-http.db")
    if db_path.exists():
        db_path.unlink()
    yield
    if db_path.exists():
        db_path.unlink()


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_index_and_search():
    content = (
        "1. Security Policy\n"
        "All employees must complete security awareness training annually.\n"
    )
    encoded = base64.b64encode(content.encode()).decode()
    response = client.post("/index", json={
        "filename": "policy.txt",
        "content_base64": encoded,
    })
    assert response.status_code == 200
    doc_id = response.json()["doc_id"]
    assert response.json()["filename"] == "policy.txt"

    response = client.post("/search", json={"query": "security training"})
    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1

    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = client.get(f"/documents/{doc_id}")
    assert response.status_code == 200

    response = client.get("/statistics")
    assert response.status_code == 200
    assert response.json()["doc_count"] == 1

    response = client.delete(f"/documents/{doc_id}")
    assert response.status_code == 200
