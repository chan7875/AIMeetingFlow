"""테스트: 볼트 전체 텍스트 검색 API + UI"""


def test_search_api_returns_matching_files(client):
    """검색 API가 일치하는 파일 경로를 반환하는지 확인"""
    res = client.get("/api/search?q=nested")
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "nested"
    paths = [row["path"] for row in data["results"]]
    assert "Notes/sub/deep.md" in paths


def test_search_api_validates_query(client):
    """검색어가 없으면 400 에러를 반환하는지 확인"""
    res = client.get("/api/search?q=")
    assert res.status_code == 400


def test_content_search_modal_exists(client):
    """HTML에 볼트 내용 검색 모달이 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="content-search-modal"' in html
    assert "openContentSearchModal()" in html
    assert 'id="content-search-results"' in html


def test_content_search_js_functions_exist(client):
    """app.js에 내용 검색 함수가 구현되어 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function openContentSearchModal" in js
    assert "async function runContentSearch" in js
    assert "renderContentSearchResults" in js
    assert "/api/search?q=" in js


def test_content_search_styles_exist(client):
    """style.css에 내용 검색 모달 스타일이 있는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".content-search-results" in css
    assert ".content-search-item" in css
