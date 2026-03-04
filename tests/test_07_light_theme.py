"""테스트: 라이트 테마 지원"""


def test_light_theme_css_variables(client):
    """CSS에 라이트 테마 변수가 정의되어 있는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert '[data-theme="light"]' in css
    assert "prefers-color-scheme: light" in css


def test_theme_toggle_button_exists(client):
    """HTML에 테마 토글 버튼이 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="theme-toggle-btn"' in html
    assert "toggleTheme()" in html


def test_theme_js_functions(client):
    """app.js에 테마 관련 함수가 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function initTheme" in js
    assert "function toggleTheme" in js
    assert "function applyTheme" in js
    assert "localStorage" in js


def test_hljs_theme_switching(client):
    """highlight.js 테마 전환을 위한 두 CSS 링크가 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="hljs-dark-theme"' in html
    assert 'id="hljs-light-theme"' in html


def test_text_dim_contrast_improved(client):
    """--text-dim 색상이 개선되었는지 확인 (#9399b2)"""
    res = client.get("/static/style.css")
    assert "#9399b2" in res.text
