"""테스트: AI 결과 UX 마무리(복사/저장 동작)"""

from pathlib import Path
from unittest.mock import patch


def test_result_copy_button_exists(client):
    """실행결과 섹션에 복사 버튼이 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="copy-result-btn"' in html
    assert "copyAIResult()" in html


def test_result_ux_js_functions_exist(client):
    """app.js에 결과 복사/저장 분기 로직이 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function copyAIResult" in js
    assert "function updateResultActionButtons" in js
    assert "/api/ai/save-result" in js


def test_save_result_endpoint_saves_ai_output(client, tmp_vault):
    """save-result API가 AI 결과를 issue 파일로 저장하는지 확인"""
    with patch("web.routers.ai.get_vault_path", return_value=tmp_vault):
        res = client.post(
            "/api/ai/save-result",
            json={"file_path": "Notes/hello.md", "ai_output": "# 저장 테스트\n본문"},
        )
    assert res.status_code == 200
    data = res.json()
    saved_path = tmp_vault / data["saved_path"]
    assert saved_path.exists()
    assert "저장 테스트" in saved_path.read_text(encoding="utf-8")


def test_save_result_endpoint_rejects_empty_output(client, tmp_vault):
    """save-result API가 빈 결과를 거부하는지 확인"""
    with patch("web.routers.ai.get_vault_path", return_value=tmp_vault):
        res = client.post(
            "/api/ai/save-result",
            json={"file_path": "Notes/hello.md", "ai_output": "   "},
        )
    assert res.status_code == 400
