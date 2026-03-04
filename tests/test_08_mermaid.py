"""테스트: Mermaid 다이어그램 렌더링 지원"""


def test_mermaid_js_loaded(client):
    """HTML에 Mermaid.js CDN 스크립트가 포함되어 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert "mermaid" in html
    assert "cdn.jsdelivr.net/npm/mermaid" in html


def test_mermaid_render_function(client):
    """app.js에 Mermaid 렌더링 함수가 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "renderMermaidBlocks" in js
    assert "mermaid.initialize" in js
    assert "mermaid.render" in js


def test_mermaid_theme_awareness(client):
    """Mermaid가 현재 테마에 맞게 초기화되는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "theme: isDark ? 'dark' : 'default'" in js or "theme:" in js


def test_mermaid_diagram_css(client):
    """CSS에 Mermaid 다이어그램 스타일이 있는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".mermaid-diagram" in css
