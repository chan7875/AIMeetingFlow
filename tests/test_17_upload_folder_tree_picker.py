"""테스트: 업로드 폴더 피커 트리 탐색"""


def test_upload_picker_tree_functions_exist(client):
    """app.js에 트리형 폴더 피커 함수가 존재하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "uploadPickerExpanded" in js
    assert "function renderUploadFolderNode" in js
    assert "folder-tree-arrow" in js
    assert "state.uploadPickerExpanded" in js


def test_upload_picker_tree_styles_exist(client):
    """style.css에 트리형 폴더 피커 스타일이 있는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".folder-tree-item" in css
    assert ".folder-tree-arrow" in css
    assert ".folder-tree-children" in css
