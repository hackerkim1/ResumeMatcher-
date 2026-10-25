"""数据结构（Pydantic）：模型的输出格式、模块之间传递的数据都在这里定义

字段的 description 会被写进提示词，是给模型的指令，要写具体。
"""
from typing import List
from pydantic import BaseModel, Field


class ResumeInfo(BaseModel):
    """从简历中抽取出的结构化信息"""
    name: str = Field(description="候选人姓名，找不到就填'未知'")
    school: str = Field(description="最高学历对应的学校全称，找不到就填'未知'")
    degree: str = Field(description="最高学历，只能是 专科、本科、硕士、博士、未知 之一")
    skills: List[str] = Field(description="候选人掌握的技术技能，每项是简短名词，如 Python、PyTorch")
    years_of_experience: float = Field(description="工作或实习总年限，没有写明就填 0")
    projects: List[str] = Field(description="项目经历，每个项目用一句话概括")


class JobRequirement(BaseModel):
    """从岗位描述(JD)中抽取出的要求"""
    title: str = Field(description="岗位名称")
    required_skills: List[str] = Field(description="必须具备的技能，每项是简短名词")
    preferred_skills: List[str] = Field(description="加分项技能，没有就返回空列表")
    min_years: float = Field(description="要求的最低工作年限，应届生可投或没有写明就填 0")
    min_degree: str = Field(description="要求的最低学历，只能是 专科、本科、硕士、博士、不限 之一")
    school_requirement: str = Field(description="对学校层次的要求原文，如'985/211优先'，没有写就填空字符串")


class SkillCheck(BaseModel):
    """对单项岗位技能的判断"""
    skill: str = Field(description="被判断的岗位技能，原样照抄")
    matched: bool = Field(description="简历是否体现了该技能（同义词、相近表述也算体现）")
    evidence: str = Field(description="简历中的依据，一句话；没有体现就填'无'")


class MatchReport(BaseModel):
    """模型负责判断和建议的部分，总分不在这里，由 scoring 根据判断计算"""
    required_checks: List[SkillCheck] = Field(description="对岗位每一项必备技能逐项判断，数量与必备技能一致")
    preferred_checks: List[SkillCheck] = Field(description="对岗位每一项加分技能逐项判断，没有加分技能就返回空列表")
    suggestions: List[str] = Field(description="针对该岗位修改简历的具体建议，3到5条")
    interview_questions: List[str] = Field(description="面试官可能针对简历提出的问题，3到5条")
