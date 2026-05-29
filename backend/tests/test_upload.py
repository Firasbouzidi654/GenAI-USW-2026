import io
from unittest.mock import AsyncMock, patch


def test_upload_valid_pdf(client):
    with patch("app.api.v1.upload.process_document", new_callable=AsyncMock):
        response = client.post(
            "/api/upload",
            files={"file": ("lecture.pdf", io.BytesIO(b"%PDF-1.4 test content"), "application/pdf")},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "filename": "lecture.pdf"}


def test_upload_non_pdf_rejected(client):
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", io.BytesIO(b"some text"), "text/plain")},
    )
    assert response.status_code == 400


def test_upload_calls_process_document(client):
    with patch("app.api.v1.upload.process_document", new_callable=AsyncMock) as mock_pipeline:
        client.post(
            "/api/upload",
            files={"file": ("lecture.pdf", io.BytesIO(b"%PDF-1.4 test content"), "application/pdf")},
        )
    mock_pipeline.assert_called_once()
    assert "lecture.pdf" in mock_pipeline.call_args[0][0]