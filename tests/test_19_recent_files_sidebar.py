"""테스트: 최근 열람 파일 사이드바"""


def test_recent_files_ui_exists_in_sidebar(client):
    """사이드바에 최근 열람 섹션이 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'class="recent-files-box"' in html
    assert 'id="recent-files-list"' in html


def test_recent_files_logic_exists_in_js(client):
    """app.js에 최근 열람 목록 저장/렌더 함수가 존재하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "RECENT_FILES_STORAGE_KEY" in js
    assert "function initRecentFiles" in js
    assert "function addRecentFile" in js
    assert "function renderRecentFiles" in js


def test_recent_files_styles_exist(client):
    """recent files 관련 CSS 스타일이 존재하는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".recent-files-box" in css
    assert ".recent-file-item" in css
    assert ".recent-file-name" in css
