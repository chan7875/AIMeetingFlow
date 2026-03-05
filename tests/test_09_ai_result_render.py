"""테스트: AI 결과 마크다운 렌더링 파이프라인"""


def test_render_ai_result_function_exists(client):
    """AI 결과 렌더링 공통 함수가 존재하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "function renderAIResult" in js
    assert "state.aiResult = (rawText || '').trim()" in js
    assert "parseMarkdownSafe(state.aiResult)" in js


def test_run_ai_uses_streaming_path(client):
    """runAI가 스트리밍 실행 경로를 재사용하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "async function runAI()" in js
    assert "await runAIStream();" in js


def test_stream_done_uses_render_ai_result(client):
    """SSE done 이벤트에서 공통 렌더 함수를 호출하는지 확인"""
    res = client.get("/static/app.js")
    js = res.text
    assert "event === 'done'" in js
    assert "renderAIResult(" in js
