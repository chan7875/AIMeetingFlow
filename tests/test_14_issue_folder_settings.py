"""테스트: 설정 모달 Issue 폴더 경로"""

from unittest.mock import patch


def test_settings_modal_has_issue_folder_input(client):
    """설정 모달에 Issue 폴더 입력 필드가 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="settings-issue-folder-input"' in html


def test_app_sends_issue_folder_in_config_save(client):
    """saveSettings가 issue_folder를 함께 전송하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "settings-issue-folder-input" in js
    assert "issue_folder" in js


def test_update_config_accepts_issue_folder(client, tmp_vault):
    """설정 저장 API가 issue_folder를 받아 응답에 포함하는지 확인"""
    with patch("web.routers.files.set_vault_path", return_value=tmp_vault), patch(
        "web.routers.files.set_issue_folder", return_value="Team/Issues"
    ):
        res = client.post(
            "/api/config",
            json={"vault_path": str(tmp_vault), "issue_folder": "Team/Issues"},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["issue_folder"] == "Team/Issues"


def test_update_config_rejects_invalid_issue_folder(client, tmp_vault):
    """절대경로/상위경로는 issue_folder로 거부되는지 확인"""
    res_abs = client.post(
        "/api/config",
        json={"vault_path": str(tmp_vault), "issue_folder": "/absolute/path"},
    )
    assert res_abs.status_code == 400

    res_parent = client.post(
        "/api/config",
        json={"vault_path": str(tmp_vault), "issue_folder": "../outside"},
    )
    assert res_parent.status_code == 400
