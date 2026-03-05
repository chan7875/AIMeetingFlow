"""테스트: 대용량 마크다운 청크 렌더링"""


def test_large_markdown_chunk_render_functions_exist(client):
    """app.js에 대용량 렌더링 임계치/청크 함수가 존재하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "LARGE_MARKDOWN_THRESHOLD" in js
    assert "LARGE_RENDER_CHUNK_SIZE" in js
    assert "function splitMarkdownChunks" in js
    assert "async function renderLargeMarkdownInChunks" in js


def test_render_viewer_markdown_has_large_file_branch(client):
    """renderViewerMarkdown에 임계치 분기 로직이 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "if (source.length > LARGE_MARKDOWN_THRESHOLD)" in js
    assert "renderLargeMarkdownInChunks" in js


def test_large_markdown_notice_style_exists(client):
    """대용량 렌더 모드 안내 스타일이 존재하는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".viewer-large-notice" in css
    assert ".viewer-chunk" in css
