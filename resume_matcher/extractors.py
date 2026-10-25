"""抽取与对比链：把非结构化文本变成 schemas 里定义的结构化数据

llm 作为参数传入（而不是在模块里写死），测试时可以换成假模型。
"""
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from resume_matcher.llm import get_llm
from resume_matcher.schemas import ResumeInfo

RESUME_PROMPT = (
    "你是专业的简历分析助手。请从下面的简历文本中抽取信息。\n"
    "规则：\n"
    "1. 只依据简历原文，找不到的信息按字段说明里的默认值填写，不要编造。\n"
    "2. 学历只能填 专科、本科、硕士、博士、未知 之一，不要写成“大学本科”等其他说法。\n"
    "3. 学校填学校全称，不要把公司名当成学校。\n"
    "4. 工作年限只统计实习和工作经历，不含学校项目；把各段时长累加后折算成年（月数除以 12）。\n"
    "5. 技能只写具体的技术名词，不写“学习能力强”之类的空话。"
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
