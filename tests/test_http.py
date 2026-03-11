import pytest
import base64
import os
from pathlib import Path

# Must set env BEFORE importing app
os.environ["DOCUMENT_INDEX_DB_PATH"] = "/tmp/test-doc-index-http.db"
os.environ["MCP_API_KEY"] = "test-mcp-key"

from fastapi.testclient import TestClient
from document_index_mcp.http_server import app
from document_index_mcp.tools import _db_cache


@pytest.fixture(autouse=True)
def clean_db():
    db_path = Path("/tmp/test-doc-index-http.db")
    _db_cache.clear()
    if db_path.exists():
        db_path.unlink()
    yield
    _db_cache.clear()
    if db_path.exists():
        db_path.unlink()


client = TestClient(app)


def _headers(*, org_id: str = "org-1", user_id: str | None = "user-1", allow_org_write: bool = False) -> dict[str, str]:
    headers = {
        "X-API-Key": "test-mcp-key",
        "X-Org-Id": org_id,
    }
    if user_id:
        headers["X-User-Id"] = user_id
    if allow_org_write:
        headers["X-Allow-Org-Write"] = "true"
    return headers


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_http_requires_api_key():
    response = client.get("/documents", headers={"X-Org-Id": "org-1"})
    assert response.status_code == 401


def test_index_and_search():
    content = (
        "1. Security Policy\n"
        "All employees must complete security awareness training annually.\n"
    )
    encoded = base64.b64encode(content.encode()).decode()
    response = client.post("/index", json={
        "filename": "policy.txt",
        "content_base64": encoded,
    }, headers=_headers())
    assert response.status_code == 200
    doc_id = response.json()["doc_id"]
    assert response.json()["filename"] == "policy.txt"

    response = client.post("/search", json={"query": "security training"}, headers=_headers())
    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1

    response = client.get("/documents", headers=_headers())
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = client.get(f"/documents/{doc_id}", headers=_headers())
    assert response.status_code == 200

    response = client.get("/statistics", headers=_headers())
    assert response.status_code == 200
    assert response.json()["doc_count"] == 1

    response = client.delete(f"/documents/{doc_id}", headers=_headers())
    assert response.status_code == 200


def test_http_visibility_is_scoped_by_org_and_owner():
    content = "1. Heading\nOwn conversation doc."
    encoded = base64.b64encode(content.encode()).decode()

    own = client.post(
        "/index",
        json={"filename": "own.txt", "content_base64": encoded},
        headers=_headers(org_id="org-1", user_id="user-1"),
    )
    assert own.status_code == 200
    own_doc_id = own.json()["doc_id"]

    other = client.post(
        "/index",
        json={"filename": "other.txt", "content_base64": encoded},
        headers=_headers(org_id="org-1", user_id="user-2"),
    )
    assert other.status_code == 200

    org_doc = client.post(
        "/index",
        json={"filename": "org.txt", "content_base64": encoded, "scope": "organization"},
        headers=_headers(org_id="org-1", user_id="admin-1", allow_org_write=True),
    )
    assert org_doc.status_code == 200

    client.post(
        "/index",
        json={"filename": "foreign.txt", "content_base64": encoded},
        headers=_headers(org_id="org-2", user_id="user-9"),
    )

    listing = client.get("/documents", headers=_headers(org_id="org-1", user_id="user-1"))
    assert listing.status_code == 200
    assert listing.json()["total"] == 2

    forbidden = client.get(
        f"/documents/{other.json()['doc_id']}",
        headers=_headers(org_id="org-1", user_id="user-1"),
    )
    assert forbidden.status_code == 404

    allowed = client.get(
        f"/documents/{own_doc_id}",
        headers=_headers(org_id="org-1", user_id="user-1"),
    )
    assert allowed.status_code == 200


def test_http_org_writes_require_explicit_header():
    content = "1. Heading\nOrg document."
    encoded = base64.b64encode(content.encode()).decode()

    create = client.post(
        "/index",
        json={"filename": "org.txt", "content_base64": encoded, "scope": "organization"},
        headers=_headers(org_id="org-1", user_id="user-1"),
    )
    assert create.status_code == 403
