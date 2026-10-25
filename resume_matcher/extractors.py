"""抽取与对比链：把非结构化文本变成 schemas 里定义的结构化数据

llm 作为参数传入（而不是在模块里写死），测试时可以换成假模型。
"""
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from resume_matcher.llm import get_llm
from resume_matcher.schemas import ResumeInfo, JobRequirement

RESUME_PROMPT = (
    "你是专业的简历分析助手。请从下面的简历文本中抽取信息。\n"
    "规则：\n"
    "1. 只依据简历原文，找不到的信息按字段说明里的默认值填写，不要编造。\n"
    "2. 学历只能填 专科、本科、硕士、博士、未知 之一，不要写成“大学本科”等其他说法。\n"
    "3. 学校填学校全称，不要把公司名当成学校。\n"
    "4. 工作年限只统计实习和工作经历，不含学校项目；把各段时长累加后折算成年（月数除以 12）。\n"
    "5. 技能只写具体的技术名词，不写“学习能力强”之类的空话。"
)


JOB_PROMPT = (
    "你是专业的招聘分析助手。请从下面的岗位描述中抽取岗位要求。\n"
    "规则：\n"
    "1. 只依据岗位描述原文，不要编造，也不要补充你认为该岗位“应该”要求的技能。\n"
    "2. “必备、要求、熟练、熟悉、掌握”的技能放进必备技能；“加分、优先、更佳”的技能放进加分技能。\n"
    "3. 技能只写具体的技术名词，沟通能力、责任心等软素质不算技能，不要抽取。\n"
    "   每一项只写一个技术名词：“A 或 B”“A 和 B”要拆成两项；"
    "不带括号，不带“经验、了解、熟悉、熟练”等程度词。\n"
    "   正确示例：LangChain、Agent、工具调用、高并发。\n"
    "   错误示例：LangChain或类似框架、Agent或工具调用经验、Python数据分析（pandas）。\n"
    "4. 应届生可投或没有写年限时，最低年限填 0；写“1 年以上”则填 1。\n"
    "5. 学历带“优先”二字的不算硬性门槛，最低学历填“不限”；写“本科及以上”则填本科。\n"
    "6. 学校层次要求（如 985/211 优先）照抄原文，没有提到就填空字符串。"
)


def make_structured_chain(llm, schema, system_prompt: str):
    """通用工厂：生成 prompt | llm | parser 的链，输出是 schema 对应的 Pydantic 对象"""
    parser = PydanticOutputParser(pydantic_object=schema)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt + "\n\n{format_instructions}"),
        ("human", "{text}"),
    ]).partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | parser


def build_resume_chain(llm=None):
    """简历抽取链。输入 {"text": 简历文本}，输出 ResumeInfo"""
    return make_structured_chain(llm or get_llm(), ResumeInfo, RESUME_PROMPT)


def build_job_chain(llm=None):
    """岗位描述抽取链。输入 {"text": JD 文本}，输出 JobRequirement"""
    return make_structured_chain(llm or get_llm(), JobRequirement, JOB_PROMPT)
