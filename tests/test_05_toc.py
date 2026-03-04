"""테스트: 마크다운 TOC 자동 생성 기능"""


def test_toc_container_in_html(client):
    """HTML에 TOC 컨테이너가 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="toc-container"' in html
    assert 'id="toc-list"' in html


def test_toc_generation_function(client):
    """app.js에 generateTOC 함수가 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function generateTOC" in js
    assert "function toggleToc" in js


def test_toc_styles_exist(client):
    """CSS에 TOC 관련 스타일이 있는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".toc-item" in css
    assert ".toc-h1" in css
    assert ".toc-h2" in css
    assert ".toc-h3" in css


def test_toc_anchor_scroll_margin(client):
    """헤딩에 scroll-margin-top이 설정되는지 확인"""
    res = client.get("/static/style.css")
    assert "scroll-margin-top" in res.text
