from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.extractors import build_resume_chain
from resume_matcher.schemas import ResumeInfo

RESUME_JSON = (
    '{"name": "张三", "school": "某某大学", "degree": "本科", '
    '"skills": ["Python", "SQL"], "years_of_experience": 0.5, "projects": ["问答系统"]}'
)


def test_resume_chain_parses_plain_json():
    chain = build_resume_chain(FakeListChatModel(responses=[RESUME_JSON]))
    result = chain.invoke({"text": "任意简历文本"})
    assert isinstance(result, ResumeInfo)
    assert result.name == "张三"
    assert result.skills == ["Python", "SQL"]
    assert result.years_of_experience == 0.5


def test_resume_chain_parses_json_in_code_fence():
    # 模型常把 JSON 包在 ```json 代码块里，解析器需要能处理
    fenced = f"```json\n{RESUME_JSON}\n```"
    chain = build_resume_chain(FakeListChatModel(responses=[fenced]))
    assert chain.invoke({"text": "x"}).school == "某某大学"


def test_prompt_contains_schema_instructions():
    chain = build_resume_chain(FakeListChatModel(responses=[RESUME_JSON]))
    prompt_text = chain.first.invoke({"text": "我的简历"}).to_string()
    assert "我的简历" in prompt_text
    # schema 里的字段名和字段说明都应该出现在提示词里
    assert "school" in prompt_text
    assert "专科、本科、硕士、博士、未知" in prompt_text
