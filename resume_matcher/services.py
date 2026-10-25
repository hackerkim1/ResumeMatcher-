"""把模型、链、缓存、院校名单、岗位库组装起来，命令行和网页共用"""
from dataclasses import dataclass

from resume_matcher.cache import JobCache
from resume_matcher.config import JOB_CACHE_DIR, VECTOR_DB_DIR
from resume_matcher.extractors import build_job_chain, build_resume_chain
from resume_matcher.judge import build_match_chain
from resume_matcher.library import JobLibrary
from resume_matcher.llm import get_embedding, get_llm
from resume_matcher.scoring import load_schools


@dataclass
class Services:
    resume_chain: object
    job_chain: object
    match_chain: object
    cache: JobCache
    schools: dict


def build_services() -> Services:
    llm = get_llm()
    return Services(
        resume_chain=build_resume_chain(llm),
        job_chain=build_job_chain(llm),
        match_chain=build_match_chain(llm),
        cache=JobCache(JOB_CACHE_DIR),
        schools=load_schools(),
    )


def build_library(jobs_dir):
    """创建岗位库并与岗位目录同步，返回 (岗位库, 同步统计)"""
    library = JobLibrary(get_embedding(), VECTOR_DB_DIR)
    return library, library.sync(jobs_dir)
