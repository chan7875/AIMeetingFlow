"""테스트: 프롬프트 템플릿 저장/불러오기"""


def test_prompt_template_controls_exist_in_html(client):
    """프롬프트 템플릿 선택/저장/삭제 UI가 존재하는지 확인"""
    res = client.get("/")
    html = res.text
    assert 'id="prompt-template-select"' in html
    assert "savePromptTemplate()" in html
    assert "deletePromptTemplate()" in html


def test_prompt_template_functions_exist_in_js(client):
    """템플릿 로컬저장 함수가 app.js에 정의되어 있는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "PROMPT_TEMPLATE_STORAGE_KEY" in js
    assert "function initPromptTemplates" in js
    assert "function applyPromptTemplate" in js
    assert "function savePromptTemplate" in js
    assert "function deletePromptTemplate" in js


def test_prompt_template_styles_exist(client):
    """프롬프트 템플릿 바 스타일이 존재하는지 확인"""
    res = client.get("/static/style.css")
    css = res.text
    assert ".prompt-template-bar" in css
    assert "#prompt-template-select" in css
