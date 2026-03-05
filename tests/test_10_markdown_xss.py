"""테스트: 마크다운 렌더 XSS 방어"""


def test_index_loads_dompurify_script(client):
    """index.html에 DOMPurify 스크립트가 로드되는지 확인"""
    res = client.get("/")
    html = res.text
    assert "dompurify" in html.lower()
    assert "purify.min.js" in html


def test_app_uses_dompurify_when_rendering_markdown(client):
    """app.js에서 marked 결과를 DOMPurify로 sanitize 하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function parseMarkdownSafe" in js
    assert "DOMPurify.sanitize" in js
    assert "parseMarkdownSafe(state.aiResult)" in js
