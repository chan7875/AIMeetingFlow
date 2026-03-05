"""테스트: 원본/AI 결과 분할 비교 뷰"""


def test_split_view_button_exists(client):
    """AI 패널 헤더에 분할뷰 버튼이 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="split-view-btn"' in html
    assert "toggleSplitView()" in html


def test_split_view_functions_exist_in_js(client):
    """app.js에 분할뷰 렌더/토글 함수가 구현되어 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "splitViewEnabled" in js
    assert "function renderSplitComparison" in js
    assert "function toggleSplitView" in js
    assert "split-original-pane" in js
    assert "split-ai-pane" in js


def test_split_view_styles_exist(client):
    """style.css에 분할뷰 레이아웃 스타일이 존재하는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".split-compare" in css
    assert ".split-pane" in css
    assert ".split-pane-body" in css
