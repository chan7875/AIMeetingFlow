"""테스트: Auto-watch 오류 상태 UI 표시"""


def test_autowatch_button_error_class_logic_exists(client):
    """app.js에 auto-watch 오류 클래스 토글 로직이 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "toggle-error" in js
    assert "const hasError" in js
    assert "status.last_error" in js


def test_autowatch_error_button_style_exists(client):
    """style.css에 auto-watch 오류 버튼 스타일이 있는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".header-btn.toggle-error" in css
