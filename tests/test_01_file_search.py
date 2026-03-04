"""테스트: 파일 검색/필터 기능 - 트리 API와 프론트엔드 검색 지원 확인"""


def test_tree_returns_files(client):
    """트리 API가 파일 목록을 정상 반환하는지 확인"""
    res = client.get("/api/tree")
    assert res.status_code == 200
    data = res.json()
    assert "children" in data
    names = [c["name"] for c in data["children"]]
    assert "Notes" in names


def test_tree_contains_nested_files(client):
    """중첩된 파일도 트리에 포함되는지 확인"""
    res = client.get("/api/tree")
    data = res.json()
    notes = next(c for c in data["children"] if c["name"] == "Notes")
    child_names = [c["name"] for c in notes["children"]]
    assert "hello.md" in child_names
    assert "sub" in child_names


def test_index_contains_search_input(client):
    """메인 페이지에 검색 입력 필드가 존재하는지 확인"""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert 'id="file-search-input"' in html
    assert "filterTree" in html


def test_static_app_js_has_filter_function(client):
    """app.js에 filterTree 함수가 정의되어 있는지 확인"""
    res = client.get("/static/app.js")
    assert res.status_code == 200
    assert "function filterTree" in res.text
    assert "function clearSearch" in res.text
