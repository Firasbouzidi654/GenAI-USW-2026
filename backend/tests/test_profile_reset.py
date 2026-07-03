import pytest

from app.api.v1 import profile


class _FakeDb:
    def __init__(self):
        self.executed = 0
        self.committed = False
        self.rolled_back = False

    async def execute(self, _statement):
        self.executed += 1

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_profile_reset_clears_uploaded_files(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    chat_dir = upload_dir / "chat-1"
    chat_dir.mkdir(parents=True)
    (chat_dir / "lecture.pdf").write_bytes(b"%PDF-1.4")
    (upload_dir / "global.pdf").write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(profile, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(profile, "clear_collection", lambda: True)

    db = _FakeDb()
    result = await profile.reset_profile(db)

    assert result == {"reset": True, "chroma_cleared": True, "uploads_cleared": True}
    assert db.committed is True
    assert list(upload_dir.iterdir()) == []
