import io
from unittest.mock import MagicMock, patch


def test_upload_valid_pdf(client, tmp_path):
    with patch("app.api.v1.upload.UPLOAD_DIR", tmp_path), \
         patch("app.api.v1.upload.process_document_sync", new_callable=MagicMock):
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


def test_upload_pdf_content_type_with_non_pdf_filename_rejected(client):
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert response.status_code == 400


def test_upload_rejects_unsafe_chat_id(client, tmp_path):
    with patch("app.api.v1.upload.UPLOAD_DIR", tmp_path), \
         patch("app.api.v1.upload.process_document_sync", new_callable=MagicMock):
        response = client.post(
            "/api/upload",
            data={"chat_id": "../outside"},
            files={"file": ("lecture.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )

    assert response.status_code == 400
    assert not (tmp_path.parent / "outside").exists()


def test_upload_calls_process_document(client, tmp_path):
    with patch("app.api.v1.upload.UPLOAD_DIR", tmp_path), \
         patch("app.api.v1.upload.process_document_sync", new_callable=MagicMock) as mock_pipeline:
        client.post(
            "/api/upload",
            files={"file": ("lecture.pdf", io.BytesIO(b"%PDF-1.4 test content"), "application/pdf")},
        )
    mock_pipeline.assert_called_once()
    assert "lecture.pdf" in mock_pipeline.call_args[0][0]
