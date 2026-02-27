from openai import AsyncOpenAI
from config.settings import settings
from models.prompt_settings import get_prompt_profile

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


YOUTUBE_SYSTEM_PROMPT = "너는 유튜브 자막을 정리해서 작성하는 도우미야."

YOUTUBE_USER_PROMPT = """아래 유튜브 자막(SRT)을 분석해서 다음 JSON 형식으로 정리해줘.

- videoTitle: SEO 최적화된 제목 (25자 이내)
- tags: 5~10개 키워드 (띄어쓰기 없이, 쉼표 구분)
- youtubeDesc: 자연스러운 유튜브 설명문 (SEO 키워드 포함)
- chapters: 배열, 각 항목은:
  - title: 소주제 제목
  - start: "hh:mm:ss"
  - end: "hh:mm:ss"
  - body: 5~6문장 요약
  - summary: 1~2문장 캐주얼 요약
  - thumbnailTitle: ~10자 썸네일 텍스트
  - shorts: 2~3문장 Shorts 스크립트 (캐주얼)
  - screenshotTimestamp: "hh:mm:ss" (썸네일 프레임)

순수 JSON만 출력해. 코드 블록이나 설명 없이.

자막:
{srt_text}"""

NEWS_SYSTEM_PROMPT = "너는 유튜브 자막을 정리해서 작성하는 도우미야."

NEWS_USER_PROMPT = """아래 텍스트를 분석해서 다음 JSON 형식으로 정리해줘.

- videoTitle: 핵심 주제 1줄 (25자 이내, 이모지 포함)
- tags: 5~10개 키워드 (띄어쓰기 없이, 쉼표 구분)
- youtubeDesc: 자연스러운 유튜브 설명문 (SEO 키워드 포함)
- chapters: 배열, 각 항목은:
  - title: 소주제 제목
  - start: "00:00:00"
  - end: "00:00:00"
  - body: 5~6문장 요약
  - summary: 1~2문장 캐주얼 요약
  - thumbnailTitle: ~10자 썸네일 텍스트
  - shorts: 2~3문장 Shorts 스크립트 (캐주얼)
  - screenshotTimestamp: "00:00:00"

순수 JSON만 출력해. 코드 블록이나 설명 없이.

텍스트:
{text}"""

THREADS_SYSTEM_PROMPT = "너는 Threads에 올릴 짧은 스토리형 포스트를 작성하는 도우미야."

THREADS_USER_PROMPT = """아래 내용을 Threads 포스트로 다시 써줘.
- 대화하듯 친근한 톤
- 짧은 문장, 줄바꿈 활용
- 이모지, 구어체 OK
- 반드시 450자 이내

내용:
{text}"""


async def generate_youtube_content(srt_text: str) -> str:
    """Generate structured content from YouTube SRT subtitles."""
    client = _get_client()
    profile = get_prompt_profile("youtube")
    user_template = profile.get("user_prompt_template") or YOUTUBE_USER_PROMPT
    prompt = user_template.replace("{srt_text}", srt_text)
    tone = profile.get("tone", "professional")
    language = profile.get("language", "ko")
    audience = profile.get("audience", "일반 대중")
    style_directive = f"톤: {tone}. 출력 언어: {language}. 타깃 독자층: {audience}."
    system_prompt = (profile.get("system_prompt") or YOUTUBE_SYSTEM_PROMPT).strip()
    system_prompt = f"{system_prompt}\n\n{style_directive}"
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""


async def generate_news_content(text: str) -> str:
    """Generate structured content from raw text/notes."""
    client = _get_client()
    profile = get_prompt_profile("news_text")
    user_template = profile.get("user_prompt_template") or NEWS_USER_PROMPT
    prompt = user_template.replace("{text}", text)
    tone = profile.get("tone", "professional")
    language = profile.get("language", "ko")
    audience = profile.get("audience", "실무자")
    style_directive = f"톤: {tone}. 출력 언어: {language}. 타깃 독자층: {audience}."
    system_prompt = (profile.get("system_prompt") or NEWS_SYSTEM_PROMPT).strip()
    system_prompt = f"{system_prompt}\n\n{style_directive}"
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""


async def generate_threads_post(text: str) -> str:
    """Generate a Threads-style short post (max 450 chars)."""
    client = _get_client()
    profile = get_prompt_profile("threads")
    user_template = profile.get("user_prompt_template") or THREADS_USER_PROMPT
    prompt = user_template.replace("{text}", text)
    tone = profile.get("tone", "casual")
    language = profile.get("language", "ko")
    audience = profile.get("audience", "SNS 사용자")
    style_directive = f"톤: {tone}. 출력 언어: {language}. 타깃 독자층: {audience}."
    system_prompt = (profile.get("system_prompt") or THREADS_SYSTEM_PROMPT).strip()
    system_prompt = f"{system_prompt}\n\n{style_directive}"
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
    )
    return resp.choices[0].message.content or ""


async def call_chatgpt(system_prompt: str, user_prompt: str) -> str:
    """Generic ChatGPT call."""
    client = _get_client()
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""
