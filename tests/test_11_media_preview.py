"""테스트: 이미지/PDF 트리 표시 및 뷰어 미리보기"""


def test_tree_includes_image_and_pdf_files(client):
    """트리 API에 이미지/PDF 파일이 포함되는지 확인"""
    res = client.get("/api/tree")
    assert res.status_code == 200
    data = res.json()
    notes = next(c for c in data["children"] if c["name"] == "Notes")
    names = [c["name"] for c in notes["children"]]
    assert "diagram.png" in names
    assert "manual.pdf" in names


def test_app_has_media_preview_functions(client):
    """app.js에 이미지/PDF 미리보기 분기 함수가 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function renderImagePreview" in js
    assert "function renderPdfPreview" in js
    assert "IMAGE_EXTENSIONS" in js
    assert "PDF_EXTENSIONS" in js


def test_css_has_media_preview_styles(client):
    """CSS에 미리보기 스타일이 추가되었는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".viewer-media-preview" in css
    assert ".viewer-preview-image" in css
    assert ".viewer-preview-pdf" in css
