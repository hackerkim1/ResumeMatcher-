"""命令行入口：解析参数、读取文件、调用各模块、打印结果

运行方式：
  python -m resume_matcher.cli match --resume 简历文件 --job 岗位文件
  python -m resume_matcher.cli recommend --resume 简历文件 [--k 3] [--brief]
"""
import argparse
import sys
from pathlib import Path

from resume_matcher.config import JOBS_DIR
from resume_matcher.documents import DocumentError, read_document
from resume_matcher.llm import MissingApiKeyError
from resume_matcher.pipeline import analyze
from resume_matcher.recommend import recommend
from resume_matcher.report import format_ranking, format_report
from resume_matcher.services import build_library, build_services


class UserError(Exception):
    """用户操作上的问题（不是程序 bug），直接把说明显示给用户"""


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

    s = build_services()
    result = analyze(resume_text, jd_text, s.resume_chain, s.job_chain, s.match_chain, s.cache, s.schools)
    return format_report(result)


def _run_recommend(args) -> str:
    resume_text = read_document(args.resume)
    jobs_dir = Path(args.jobs_dir)
    if not any(jobs_dir.glob("*.txt")):
        raise UserError(f"没有找到岗位文件：{jobs_dir} 下没有 .txt 文件")

    s = build_services()
    library, stats = build_library(jobs_dir)
    header = f"岗位库已同步：新增 {stats['added']}，移除 {stats['removed']}，沿用 {stats['kept']}\n"

    recs = recommend(resume_text, library, args.k, s.resume_chain, s.job_chain, s.match_chain,
                     s.cache, s.schools)
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
    except (UserError, DocumentError, MissingApiKeyError) as e:
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
