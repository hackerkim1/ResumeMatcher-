"""从国聘（iguopin.com）小规模抓取公开岗位，仅供个人学习使用

运行方式：
  python -m resume_matcher.crawler --keyword 数据分析 --max-jobs 30

约束都写在代码里，并有测试：
  - 先读 robots.txt，被禁止就一个请求都不发；读不到也不抓
  - 请求之间至少间隔 1 秒（默认 3 秒）；总量硬上限 100 条，超过就报错，不悄悄截断
  - 遇到登录、验证码、限流、数据结构异常，立刻停止，不重试、不绕过
  - 只保留岗位文字和专业、学历等要求；联系人和各种内部 ID 一律丢弃
  - 不带 Cookie 或令牌，不伪装浏览器，User-Agent 如实说明用途
"""
import argparse
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.robotparser import RobotFileParser

from resume_matcher.config import CRAWLED_DIR

API_URL = "https://gp-api.iguopin.com/api/jobs/v1/recom-job"
ROBOTS_URL = "https://gp-api.iguopin.com/robots.txt"
USER_AGENT = "ResumeMatcher-student-project (personal learning, low request rate)"
ROBOTS_AGENT = "ResumeMatcher"

HARD_MAX_JOBS = 100
MIN_DELAY = 1.0
DEFAULT_DELAY = 3.0
PAGE_SIZE = 20

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
_BLOCK_TAGS = {"br", "p", "div", "li", "tr", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}


class CrawlStopped(Exception):
    """被拦下或遇到异常，已停止。records 是停止前已经收集到的岗位"""

    def __init__(self, reason: str, records=None):
        super().__init__(reason)
        self.records = records or []


@dataclass
class JobRecord:
    job_id: str
    title: str
    company: str
    category: str
    majors: list = field(default_factory=list)
    education: str = ""
    experience: str = ""
    nature: str = ""
    salary: str = ""
    updated: str = ""
    jd_text: str = ""


@dataclass
class CrawlResult:
    records: list
    skipped: int
    pages: int


# ---------- 解析 ----------

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html) -> str:
    """把岗位描述里的 HTML 转成纯文本：换行标签变成换行，去掉标签，合并空行"""
    if not html:
        return ""
    extractor = _TextExtractor()
    extractor.feed(str(html))
    text = "".join(extractor.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _is_expired(end_time, today: datetime.date) -> bool:
    try:
        return datetime.date.fromisoformat(_text(end_time)[:10]) < today
    except ValueError:
        return False  # 写的是“长期有效”之类，无法判断就保留


def _salary(item: dict) -> str:
    if item.get("is_negotiable"):
        return "面议"
    low, high = item.get("min_wage") or 0, item.get("max_wage") or 0
    return f"{low}-{high}{_text(item.get('wage_unit_cn'))}" if high > 0 else "未公布"


def parse_job(item: dict, today: datetime.date):
    """把接口里的一条岗位转成 JobRecord，只保留白名单字段；过期、没有描述、没有编号的返回 None"""
    job_id, title = _text(item.get("job_id")), _text(item.get("job_name"))
    jd_text = html_to_text(item.get("contents"))
    if not job_id or not title or not jd_text:
        return None
    if _is_expired(item.get("end_time"), today):
        return None
    majors = item.get("major_cn")
    return JobRecord(
        job_id=job_id,
        title=title,
        company=_text(item.get("company_name")),
        category=_text(item.get("category_cn")),
        majors=list(dict.fromkeys(_text(m) for m in majors if _text(m))) if isinstance(majors, list) else [],
        education=_text(item.get("education_cn")),
        experience=_text(item.get("experience_cn")),
        nature=_text(item.get("nature_cn")),
        salary=_salary(item),
        updated=_text(item.get("update_time")),
        jd_text=jd_text,
    )


def render_job_text(rec: JobRecord) -> str:
    """排成和样例岗位类似的文本，方便直接放进岗位库"""
    return "\n".join([
        f"岗位：{rec.title}",
        f"单位：{rec.company}",
        f"岗位类别：{rec.category}",
        f"专业要求：{'、'.join(rec.majors) or '不限'}",
        f"学历要求：{rec.education}",
        f"经验要求：{rec.experience}",
        f"招聘性质：{rec.nature}",
        f"薪资：{rec.salary}",
        f"更新时间：{rec.updated}",
        "",
        rec.jd_text,
        "",
    ])


# ---------- 请求与校验 ----------

def build_body(page: int, page_size: int, keyword=None) -> dict:
    """和网站页面自己发出的请求格式一致（在浏览器里观察得到），不带地区等其他筛选"""
    search = {"page": page, "page_size": page_size}
    if keyword:
        search["keyword"] = keyword
    return {"search": search, "recom": {"update_time": True, "company_nature": True, "hot_job": True}}


def robots_allows(robots_text: str, url: str, agent: str = ROBOTS_AGENT) -> bool:
    """没有 robots.txt（空、或返回的是普通网页）视为没有规则"""
    lines = robots_text.splitlines() if "user-agent" in robots_text.lower() else []
    parser = RobotFileParser()
    parser.parse(lines)
    return parser.can_fetch(agent, url)


def check_response(status: int, text: str):
    """校验一次返回，正常则给出 (岗位列表, 总数)；任何异常都当作停止信号，不重试"""
    if status != 200:
        raise CrawlStopped(f"网站返回 HTTP {status}，可能需要登录或触发了限制")
    try:
        payload = json.loads(text)
    except ValueError:
        raise CrawlStopped("返回的不是正常数据，可能是验证页面或登录页") from None
    if not isinstance(payload, dict) or str(payload.get("code")) != "200":
        code = payload.get("code") if isinstance(payload, dict) else None
        raise CrawlStopped(f"接口返回的业务码是 {code}，可能需要登录或触发了限制")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise CrawlStopped("返回的数据结构和预期不同，网站可能改版了")
    total = data.get("total")
    return data["list"], total if isinstance(total, int) else None


def http_get_text(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def http_post_json(url: str, body: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


class Crawler:
    """联网和睡眠都从参数传入，测试时换成假的"""

    def __init__(self, post_json=http_post_json, get_text=http_get_text, sleep=time.sleep, today=None):
        self._post, self._get, self._sleep = post_json, get_text, sleep
        self._today = today or datetime.date.today()

    def _check_robots(self):
        try:
            status, text = self._get(ROBOTS_URL)
        except Exception:
            raise CrawlStopped("无法读取 robots.txt，为稳妥起见不抓取") from None
        if status == 404:
            return  # 没有发布规则
        if status != 200 or not robots_allows(text, API_URL):
            raise CrawlStopped("robots.txt 不允许抓取这个接口，或无法确认")

    def crawl(self, max_jobs: int, delay: float = DEFAULT_DELAY, page_size: int = PAGE_SIZE,
              keyword=None) -> CrawlResult:
        if not 1 <= max_jobs <= HARD_MAX_JOBS:
            raise ValueError(f"--max-jobs 必须在 1 到 {HARD_MAX_JOBS} 之间（小规模抓取，不追求大而全）")
        if delay < MIN_DELAY:
            raise ValueError(f"请求间隔不能低于 {MIN_DELAY} 秒")

        self._check_robots()
        records, seen, skipped, pages, page = [], set(), 0, 0, 1
        while len(records) < max_jobs:
            if pages:
                self._sleep(delay)
            try:
                status, text = self._post(API_URL, build_body(page, page_size, keyword))
                pages += 1
                items, total = check_response(status, text)
            except CrawlStopped as stop:
                stop.records = records
                raise
            except Exception:
                raise CrawlStopped("请求失败，已停止", records) from None
            if not items:
                break
            for item in items:
                rec = parse_job(item, self._today)
                if rec is None:
                    skipped += 1
                elif rec.job_id not in seen:
                    seen.add(rec.job_id)
                    records.append(rec)
                    if len(records) >= max_jobs:
                        break
            if total is not None and page * page_size >= total:
                break
            page += 1
        return CrawlResult(records=records, skipped=skipped, pages=pages)


# ---------- 保存 ----------

def save_records(records, out_dir, fetched_on: datetime.date) -> int:
    """每个岗位一个 txt（文件名是岗位编号），另有 index.jsonl 记录元数据；已存在的不重复写，返回新增数量"""
    if any(not _SAFE_ID.fullmatch(r.job_id) for r in records):
        raise ValueError("岗位编号含有不安全的字符，已拒绝保存")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    new_lines = []
    for rec in records:
        path = out / f"{rec.job_id}.txt"
        if path.exists():
            continue
        path.write_text(render_job_text(rec), encoding="utf-8")
        new_lines.append(json.dumps({
            "job_id": rec.job_id, "title": rec.title, "company": rec.company, "category": rec.category,
            "majors": rec.majors, "education": rec.education, "experience": rec.experience,
            "nature": rec.nature, "salary": rec.salary, "updated": rec.updated,
            "source": "iguopin", "fetched_on": fetched_on.isoformat(),
        }, ensure_ascii=False))
    if new_lines:
        with open(out / "index.jsonl", "a", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")
    return len(new_lines)


# ---------- 命令行 ----------

def main(argv=None, post_json=http_post_json, get_text=http_get_text, sleep=time.sleep, today=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="从国聘小规模抓取公开岗位（仅供个人学习）")
    parser.add_argument("--keyword", help="搜索关键词，如 数据分析")
    parser.add_argument("--max-jobs", type=int, default=30, help=f"最多保留几条，上限 {HARD_MAX_JOBS}")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"请求间隔秒数，不低于 {MIN_DELAY}")
    parser.add_argument("--output", default=str(CRAWLED_DIR), help="保存目录")
    args = parser.parse_args(argv)

    today = today or datetime.date.today()
    crawler = Crawler(post_json=post_json, get_text=get_text, sleep=sleep, today=today)
    try:
        result = crawler.crawl(args.max_jobs, args.delay, keyword=args.keyword)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        return 1
    except CrawlStopped as stop:
        print(f"已停止：{stop}", file=sys.stderr)
        if stop.records:
            saved = save_records(stop.records, args.output, today)
            print(f"停止前已收集 {len(stop.records)} 条，新写入 {saved} 个文件到 {args.output}", file=sys.stderr)
        return 1

    saved = save_records(result.records, args.output, today)
    print(f"完成：请求 {result.pages} 次，保留 {len(result.records)} 条，跳过 {result.skipped} 条"
          f"（过期或没有描述），新写入 {saved} 个文件到 {args.output}")
    print("这些数据仅供个人学习，目录已被 .gitignore 排除，不会被提交。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
