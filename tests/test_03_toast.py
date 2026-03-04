"""테스트: Toast 알림 수동 닫기 기능"""


def test_toast_function_has_close_button(client):
    """toast 함수에 닫기 버튼 코드가 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "toast-close" in js
    assert "toast-message" in js


def test_toast_error_no_auto_dismiss(client):
    """에러 Toast는 자동 닫기가 비활성화되는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "type !== 'error'" in js


def test_toast_close_style_exists(client):
    """Toast 닫기 버튼 스타일이 존재하는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".toast-close" in css
    assert ".toast-message" in css


def test_toast_has_role_alert(client):
    """Toast에 role="alert" 속성이 설정되는지 확인"""
    res = client.get("/static/app.js")
    assert 'role' in res.text
    assert 'alert' in res.text
