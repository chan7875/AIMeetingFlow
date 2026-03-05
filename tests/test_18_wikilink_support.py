"""테스트: Obsidian 위키링크([[...]]) 지원"""


def test_wikilink_transform_and_bind_functions_exist(client):
    """app.js에 위키링크 변환/바인딩 함수가 존재하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function transformWikiLinks" in js
    assert "function resolveWikiLinkTarget" in js
    assert "function bindWikiLinks" in js
    assert "wikilink:" in js


def test_markdown_parser_uses_wikilink_transform(client):
    """parseMarkdownSafe가 위키링크 전처리를 사용하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "marked.parse(transformWikiLinks" in js


def test_wikilink_styles_exist(client):
    """위키링크 표시 스타일이 존재하는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert 'a[data-wikilink="true"]' in css
