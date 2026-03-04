"""테스트: 접근성(ARIA) 개선 - ARIA 속성 및 키보드 접근성 확인"""


def test_sidebar_has_navigation_role(client):
    """사이드바에 role="navigation"이 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'role="navigation"' in html
    assert 'aria-label="파일 탐색기"' in html


def test_tree_container_has_tree_role(client):
    """트리 컨테이너에 role="tree"가 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'role="tree"' in html


def test_modals_have_dialog_role(client):
    """모달에 role="dialog" 및 aria-modal="true"가 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert html.count('role="dialog"') >= 4
    assert html.count('aria-modal="true"') >= 4


def test_section_bars_have_aria_expanded(client):
    """접기/펼치기 바에 aria-expanded 속성이 있는지 확인"""
    res = client.get("/")
    html = res.text
    assert html.count('aria-expanded="true"') >= 3


def test_focus_visible_style_exists(client):
    """CSS에 :focus-visible 스타일이 있는지 확인"""
    res = client.get("/static/style.css")
    assert ":focus-visible" in res.text


def test_tree_items_have_treeitem_role(client):
    """app.js에서 treeitem role이 설정되는지 확인"""
    res = client.get("/static/app.js")
    assert "treeitem" in res.text


def test_keyboard_navigation_code_exists(client):
    """app.js에 방향키 네비게이션 코드가 있는지 확인"""
    res = client.get("/static/app.js")
    assert "ArrowUp" in res.text
    assert "ArrowDown" in res.text
