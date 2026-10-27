import pytest


FRONTEND_ORIGIN = "https://facturation.elbouazzatiholding.ma"


@pytest.fixture
def cors_client(client, settings):
    settings.CORS_ALLOWED_ORIGINS = [FRONTEND_ORIGIN]
    settings.CORS_ALLOW_ALL_ORIGINS = False
    return client


@pytest.mark.parametrize(
    ("path", "method", "headers"),
    [
        ("/api/ai/v1/capabilities/?language=fr", "GET", "authorization,cache-control"),
        ("/api/ai/v1/conversations/", "GET", "authorization,cache-control"),
        ("/api/ai/v1/conversations/", "POST", "authorization,cache-control,content-type"),
    ],
)
def test_chat_preflight_allows_authenticated_uncached_requests(cors_client, path, method, headers):
    response = cors_client.options(
        path,
        HTTP_ORIGIN=FRONTEND_ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD=method,
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headers,
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == FRONTEND_ORIGIN
    assert response["Access-Control-Allow-Credentials"] == "true"
    allowed = {header.strip() for header in response["Access-Control-Allow-Headers"].lower().split(",")}
    assert set(headers.split(",")) <= allowed


def test_chat_preflight_does_not_allow_untrusted_origins(cors_client):
    response = cors_client.options(
        "/api/ai/v1/capabilities/?language=fr",
        HTTP_ORIGIN="https://untrusted.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,cache-control",
    )

    assert "Access-Control-Allow-Origin" not in response
