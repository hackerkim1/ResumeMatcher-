from langchain_core.language_models.fake_chat_models import FakeListChatModel

from resume_matcher.extractors import build_resume_chain, build_job_chain
from resume_matcher.schemas import ResumeInfo, JobRequirement

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


JOB_JSON = (
    '{"title": "大模型应用开发工程师", "required_skills": ["Python", "LangChain"], '
    '"preferred_skills": ["FastAPI"], "min_years": 0, "min_degree": "本科", '
    '"school_requirement": ""}'
)


def test_job_chain_parses_plain_json():
    chain = build_job_chain(FakeListChatModel(responses=[JOB_JSON]))
    result = chain.invoke({"text": "任意岗位描述"})
    assert isinstance(result, JobRequirement)
    assert result.required_skills == ["Python", "LangChain"]
    assert result.preferred_skills == ["FastAPI"]
    assert result.school_requirement == ""


def test_job_chain_parses_json_in_code_fence():
    chain = build_job_chain(FakeListChatModel(responses=[f"```json\n{JOB_JSON}\n```"]))
    assert chain.invoke({"text": "x"}).title == "大模型应用开发工程师"


def test_job_prompt_contains_rules_and_schema():
    chain = build_job_chain(FakeListChatModel(responses=[JOB_JSON]))
    prompt_text = chain.first.invoke({"text": "我的岗位描述"}).to_string()
    assert "我的岗位描述" in prompt_text
    assert "专科、本科、硕士、博士、不限" in prompt_text
    assert "优先" in prompt_text  # 提示词里要写明“优先”类措辞怎么处理
    # 技能要拆成独立的单项，否则同一份 JD 每次拆出的项数不同，总分会波动
    assert "每一项只写一个" in prompt_text
