"""테스트: 모바일 터치 타겟 확대 및 경험 개선"""


def test_mobile_touch_target_min_width(client):
    """모바일 헤더 버튼 최소 터치 타겟 44px 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert "min-width: 44px" in css
    assert "min-height: 44px" in css


def test_mobile_sidebar_gpu_acceleration(client):
    """사이드바 드로어에 GPU 가속(translate3d) 적용 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert "translate3d" in css
    assert "will-change: transform" in css


def test_mobile_ai_panel_height(client):
    """모바일 AI 패널 최소 높이 40vh 확인"""
    res = client.get("/static/style.css")
    assert "min-height: 40vh" in res.text


def test_mobile_safe_area_padding(client):
    """safe-area-inset-bottom padding 확인"""
    res = client.get("/static/style.css")
    assert "safe-area-inset-bottom" in res.text


def test_mobile_tree_item_touch_target(client):
    """모바일 트리 아이템 터치 타겟 확대 확인"""
    res = client.get("/static/style.css")
    assert "min-height: 40px" in res.text
