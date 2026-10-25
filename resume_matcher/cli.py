"""命令行入口：解析参数、读取文件、调用各模块、打印结果

运行方式：
  python -m resume_matcher.cli match --resume 简历文件 --job 岗位文件
  python -m resume_matcher.cli recommend --resume 简历文件 [--k 3] [--brief]
"""
import argparse
import sys
from pathlib import Path

import pymupdf

from resume_matcher.cache import JobCache
from resume_matcher.config import JOB_CACHE_DIR, JOBS_DIR, VECTOR_DB_DIR
from resume_matcher.extractors import build_job_chain, build_resume_chain
from resume_matcher.judge import build_match_chain
from resume_matcher.library import JobLibrary
from resume_matcher.llm import MissingApiKeyError, get_embedding, get_llm
from resume_matcher.pipeline import analyze
from resume_matcher.recommend import recommend
from resume_matcher.report import format_ranking, format_report
from resume_matcher.scoring import load_schools


class UserError(Exception):
    """用户操作上的问题（不是程序 bug），直接把说明显示给用户"""


def read_document(path) -> str:
    """读取文本：pdf 用 PyMuPDF，其他按 UTF-8 文本读"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    if p.suffix.lower() == ".pdf":
        with pymupdf.open(p) as doc:
            return "\n".join(page.get_text() for page in doc)
    return p.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resume_matcher", description="简历 × 岗位匹配分析器")
    sub = parser.add_subparsers(dest="command", required=True)

    match = sub.add_parser("match", help="一份简历对一个岗位")
    match.add_argument("--resume", required=True, help="简历文件（.txt 或 .pdf）")
    match.add_argument("--job", required=True, help="岗位描述文件（.txt）")

    rec = sub.add_parser("recommend", help="一份简历对岗位库，推荐最合适的岗位")
    rec.add_argument("--resume", required=True, help="简历文件（.txt 或 .pdf）")
    rec.add_argument("--jobs-dir", default=str(JOBS_DIR), help="岗位库目录，里面是若干 .txt 岗位文件")
    rec.add_argument("--k", type=int, default=3, help="检索前几个候选岗位并详细评分")
    rec.add_argument("--brief", action="store_true", help="只显示排名，不显示每个岗位的完整报告")
    return parser


def _run_match(args) -> str:
    # 先读文件，再创建模型：文件有问题时不该去连网络
    resume_text = read_document(args.resume)
    jd_text = read_document(args.job)

    llm = get_llm()
    result = analyze(
        resume_text, jd_text,
        resume_chain=build_resume_chain(llm),
        job_chain=build_job_chain(llm),
        match_chain=build_match_chain(llm),
        cache=JobCache(JOB_CACHE_DIR),
        schools=load_schools(),
    )
    return format_report(result)


def _run_recommend(args) -> str:
    resume_text = read_document(args.resume)
    jobs_dir = Path(args.jobs_dir)
    if not any(jobs_dir.glob("*.txt")):
        raise UserError(f"没有找到岗位文件：{jobs_dir} 下没有 .txt 文件")

    llm = get_llm()
    library = JobLibrary(get_embedding(), VECTOR_DB_DIR)
    stats = library.sync(jobs_dir)
    header = f"岗位库已同步：新增 {stats['added']}，移除 {stats['removed']}，沿用 {stats['kept']}\n"

    recs = recommend(
        resume_text, library, args.k,
        resume_chain=build_resume_chain(llm),
        job_chain=build_job_chain(llm),
        match_chain=build_match_chain(llm),
        cache=JobCache(JOB_CACHE_DIR),
        schools=load_schools(),
    )
    parts = [header + format_ranking(recs)]
    if not args.brief:
        parts += [format_report(r.result) for r in recs]
    return "\n\n".join(parts)


HANDLERS = {"match": _run_match, "recommend": _run_recommend}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    try:
        output = HANDLERS[args.command](args)
    except FileNotFoundError as e:
        print(f"找不到文件：{e.args[0]}", file=sys.stderr)
        return 1
    except (UserError, MissingApiKeyError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except Exception as e:
        # 只显示错误类型，避免完整报错里带出 key 的片段
        print(f"分析失败：{type(e).__name__}，请稍后重试或检查网络与模型配置", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
