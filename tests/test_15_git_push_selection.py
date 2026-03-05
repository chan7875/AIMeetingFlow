"""테스트: Git Push 파일 선택 기능"""

from unittest.mock import AsyncMock, patch

from web.routers.git import _parse_changed_files


def test_git_push_modal_has_file_list(client):
    """Git Push 모달에 파일 선택 리스트 UI가 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="git-files-list"' in html
    assert 'id="git-push-run-btn"' in html


def test_app_has_git_push_file_selection_logic(client):
    """app.js에 변경 파일 조회/체크박스 선택 로직이 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function loadGitPushFiles" in js
    assert "git-file-checkbox" in js
    assert "files: selectedFiles" in js


def test_parse_changed_files_handles_rename_and_untracked():
    """git status --short 파싱이 rename/untracked를 처리하는지 확인"""
    parsed = _parse_changed_files(" M a.md\nA  b.txt\nR  old.md -> new.md\n?? c.md\n")
    paths = [row["path"] for row in parsed]
    assert "a.md" in paths
    assert "b.txt" in paths
    assert "new.md" in paths
    assert "c.md" in paths


def test_git_changes_endpoint_returns_files(client):
    """변경 파일 조회 API가 파싱된 목록을 반환하는지 확인"""
    mocked = AsyncMock(return_value=(0, " M alpha.md\n?? beta.txt\n", ""))
    with patch("web.routers.git._run_git_capture", mocked):
        res = client.get("/api/git/changes")
    assert res.status_code == 200
    data = res.json()
    assert data["is_git_repo"] is True
    assert [row["path"] for row in data["files"]] == ["alpha.md", "beta.txt"]


def test_git_push_requires_selected_files(client):
    """Push API는 선택 파일이 없으면 400을 반환하는지 확인"""
    res = client.post("/api/git/push", json={"message": "msg", "files": []})
    assert res.status_code == 400
