"""테스트: 파일 컨텍스트 메뉴 - 삭제/이름변경 API 및 UI"""


def test_rename_file(client, tmp_vault):
    """파일 이름 변경 API 정상 동작"""
    res = client.post("/api/rename", json={"path": "readme.txt", "new_name": "renamed.txt"})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "renamed.txt"
    assert (tmp_vault / "renamed.txt").exists()
    assert not (tmp_vault / "readme.txt").exists()


def test_rename_file_duplicate(client, tmp_vault):
    """이미 존재하는 이름으로 변경 시 409 에러"""
    (tmp_vault / "duplicate.txt").write_text("dup", encoding="utf-8")
    res = client.post("/api/rename", json={"path": "readme.txt", "new_name": "duplicate.txt"})
    assert res.status_code == 409


def test_rename_invalid_name(client):
    """잘못된 파일명(경로 포함) 시 400 에러"""
    res = client.post("/api/rename", json={"path": "readme.txt", "new_name": "../evil.txt"})
    assert res.status_code == 400


def test_delete_file(client, tmp_vault):
    """파일 삭제 API 정상 동작"""
    res = client.post("/api/delete", json={"path": "readme.txt"})
    assert res.status_code == 200
    assert not (tmp_vault / "readme.txt").exists()


def test_delete_directory(client, tmp_vault):
    """폴더 삭제 API 정상 동작"""
    res = client.post("/api/delete", json={"path": "Notes/sub"})
    assert res.status_code == 200
    assert not (tmp_vault / "Notes" / "sub").exists()


def test_delete_nonexistent(client):
    """존재하지 않는 파일 삭제 시 404 에러"""
    res = client.post("/api/delete", json={"path": "nonexistent.md"})
    assert res.status_code == 404


def test_context_menu_html_exists(client):
    """HTML에 컨텍스트 메뉴가 존재하는지 확인"""
    res = client.get("/")
    assert 'id="context-menu"' in res.text
    assert 'contextMenuAction' in res.text


def test_context_menu_js_functions(client):
    """app.js에 컨텍스트 메뉴 함수가 있는지 확인"""
    res = client.get("/static/app.js")
    assert "showContextMenu" in res.text
    assert "hideContextMenu" in res.text
    assert "contextMenuAction" in res.text
