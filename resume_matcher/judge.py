"""逐项对比：模型判断简历是否体现了岗位的每项技能，并给出依据

技能清单以 JD 为准：模型漏判、多判、改写技能名，都由 align_checks 在代码里纠正，
这样评分的分母不会受模型波动影响。
"""
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from resume_matcher.grounding import verify_checks
from resume_matcher.llm import get_llm
from resume_matcher.schemas import JobRequirement, MatchReport, SkillCheck

JUDGE_PROMPT = (
    "你是资深招聘顾问。请判断简历是否体现了岗位要求的每一项技能，并给出修改建议和面试题。\n"
    "规则：\n"
    "1. 必备技能和加分技能都要逐项判断，每项输出一条，技能名原样照抄清单，不要改写、合并或增删。\n"
    "2. 依据必须直接摘抄简历原文中的句子或片段，不要改写，不要概括；没有体现就填“无”。\n"
    "3. 以下情况算体现：技能清单中列出；项目或实习中用到；同义或相近的说法"
    "（例如“检索增强生成”等同于 RAG）；具体工具属于该类别（例如 Chroma 属于向量数据库）。\n"
    "4. 以下情况不算体现：只是相邻领域（例如会 scikit-learn 不等于会 PyTorch）；"
    "需要你推测才能得出的结论；简历里完全没有提到。\n"
    "5. 只依据简历原文判断，不要替候选人编造经历。\n"
    "6. 修改建议和面试题要结合候选人的实际项目，具体可操作，不要说空话。各 3 到 5 条。\n\n"
    "{format_instructions}"
)

HUMAN_TEMPLATE = (
    "【岗位】{job_title}\n\n"
    "【必备技能】\n{required_list}\n\n"
    "【加分技能】\n{preferred_list}\n\n"
    "【简历原文】\n{resume_text}"
)


def build_match_chain(llm=None):
    """逐项对比链。输入 resume_text、job_title、required_list、preferred_list，输出 MatchReport"""
    parser = PydanticOutputParser(pydantic_object=MatchReport)
    prompt = ChatPromptTemplate.from_messages([
        ("system", JUDGE_PROMPT),
        ("human", HUMAN_TEMPLATE),
    ]).partial(format_instructions=parser.get_format_instructions())
    return prompt | (llm or get_llm()) | parser


def _norm(name: str) -> str:
    return name.strip().casefold()


def align_checks(expected: list[str], checks: list[SkillCheck]) -> list[SkillCheck]:
    """让判断结果与 JD 的技能清单一一对应：按 JD 顺序、漏的补未满足、多的丢掉、重复的取第一个"""
    by_name: dict[str, SkillCheck] = {}
    for c in checks:
        by_name.setdefault(_norm(c.skill), c)

    aligned = []
    for skill in expected:
        found = by_name.get(_norm(skill))
        if found is None:
            # 宁可保守：模型没判断的技能不给分
            aligned.append(SkillCheck(skill=skill, matched=False, evidence="模型未给出判断"))
        else:
            aligned.append(found.model_copy(update={"skill": skill}))  # 技能名以 JD 为准
    return aligned


def _numbered(skills: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(skills, 1)) if skills else "（无）"


def judge(resume_text: str, job: JobRequirement, chain) -> MatchReport:
    """对比简历原文和岗位要求，返回与 JD 技能清单对齐、且依据核对过的报告"""
    report = chain.invoke({
        "resume_text": resume_text,
        "job_title": job.title,
        "required_list": _numbered(job.required_skills),
        "preferred_list": _numbered(job.preferred_skills),
    })
    return report.model_copy(update={
        "required_checks": verify_checks(
            align_checks(job.required_skills, report.required_checks), resume_text),
        "preferred_checks": verify_checks(
            align_checks(job.preferred_skills, report.preferred_checks), resume_text),
    })
