"""从国聘（iguopin.com）小规模抓取公开岗位，仅供个人学习使用

运行方式：
  python -m resume_matcher.crawler --keyword 数据分析          # 一个关键词
  python -m resume_matcher.crawler --track 数据                # 一个专业方向的所有关键词
  python -m resume_matcher.crawler --all                       # 所有专业方向（约 27 个关键词）

约束都写在代码里，并有测试：
  - 先读 robots.txt，被禁止就一个请求都不发；读不到也不抓
  - 请求之间至少间隔 1 秒（默认 3 秒）
  - 每个关键词最多 30 条，一次运行总共最多 300 条，超过就报错，不悄悄截断；
    总量平均分给各个关键词，避免前面的方向把名额用光
  - 每个关键词最多翻 3 页，一次运行最多 60 次请求，即使程序出错也不会无限请求
  - 遇到登录、验证码、限流、数据结构异常，立刻停止，不重试、不绕过；已收集的会保存
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
from urllib.robotparser import RobotFileParser

from resume_matcher.config import CRAWLED_FILE
from resume_matcher.jobsfile import append_new
from resume_matcher.tracks import TRACKS, all_keywords, keywords_for, track_of as default_track_of

API_URL = "https://gp-api.iguopin.com/api/jobs/v1/recom-job"
ROBOTS_URL = "https://gp-api.iguopin.com/robots.txt"
USER_AGENT = "ResumeMatcher-student-project (personal learning, low request rate)"
ROBOTS_AGENT = "ResumeMatcher"

MAX_PER_KEYWORD = 30
MAX_TOTAL_JOBS = 300
MAX_PAGES_PER_KEYWORD = 3
MAX_REQUESTS = 60
MIN_DELAY = 1.0
DEFAULT_DELAY = 3.0
PAGE_SIZE = 20

# 真实数据里，“专业要求”有时写的是这类话，它不是专业类别
_PLACEHOLDER_MAJORS = {"详见职位描述", "详见岗位描述", "详见招聘简章", "详见招聘公告"}
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
    keyword: str = ""  # 是用哪个关键词搜到的
    track: str = ""    # 这个关键词属于哪个专业方向（我们自己定的分类）


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


def _majors(raw) -> list:
    if not isinstance(raw, list):
        return []
    cleaned = (_text(m) for m in raw)
    return list(dict.fromkeys(m for m in cleaned if m and m not in _PLACEHOLDER_MAJORS))


def parse_job(item: dict, today: datetime.date):
    """把接口里的一条岗位转成 JobRecord，只保留白名单字段；过期、没有描述、没有编号的返回 None"""
    job_id, title = _text(item.get("job_id")), _text(item.get("job_name"))
    jd_text = html_to_text(item.get("contents"))
    if not job_id or not title or not jd_text:
        return None
    if _is_expired(item.get("end_time"), today):
        return None
    return JobRecord(
        job_id=job_id,
        title=title,
        company=_text(item.get("company_name")),
        category=_text(item.get("category_cn")),
        majors=_majors(item.get("major_cn")),
        education=_text(item.get("education_cn")),
        experience=_text(item.get("experience_cn")),
        nature=_text(item.get("nature_cn")),
        salary=_salary(item),
        updated=_text(item.get("update_time")),
        jd_text=jd_text,
    )


def render_job_text(rec: JobRecord) -> str:
    """排成和样例岗位类似的文本：既用于向量化，也用于交给模型分析"""
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


def record_to_row(rec: JobRecord, fetched_on: datetime.date) -> dict:
    """转成 jobs.jsonl 里的一行：元数据 + 完整正文（text）"""
    return {
        "job_id": rec.job_id, "title": rec.title, "company": rec.company, "category": rec.category,
        "majors": rec.majors, "education": rec.education, "experience": rec.experience,
        "nature": rec.nature, "salary": rec.salary, "updated": rec.updated,
        "keyword": rec.keyword, "track": rec.track,
        "source": "iguopin", "fetched_on": fetched_on.isoformat(),
        "text": render_job_text(rec),
    }


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

    def __init__(self, post_json=http_post_json, get_text=http_get_text, sleep=time.sleep, today=None,
                 max_requests=MAX_REQUESTS):
        self._post, self._get, self._sleep = post_json, get_text, sleep
        self._today = today or datetime.date.today()
        self._max_requests = max_requests
        self._requests = 0

    def _check_robots(self):
        try:
            status, text = self._get(ROBOTS_URL)
        except Exception:
            raise CrawlStopped("无法读取 robots.txt，为稳妥起见不抓取") from None
        if status == 404:
            return  # 没有发布规则
        if status != 200 or not robots_allows(text, API_URL):
            raise CrawlStopped("robots.txt 不允许抓取这个接口，或无法确认")

    def _fetch(self, page, page_size, keyword, delay):
        """发一次请求。全局请求次数和间隔都在这里管：每两次请求之间睡 delay 秒，不管是不是同一个关键词"""
        if self._requests >= self._max_requests:
            raise CrawlStopped("已达到本次运行的请求次数上限")
        if self._requests:
            self._sleep(delay)
        self._requests += 1
        status, text = self._post(API_URL, build_body(page, page_size, keyword))
        return check_response(status, text)

    def _collect(self, keyword, quota, seen, delay, page_size, track):
        """为一个关键词收集最多 quota 条（跨关键词去重），最多翻 MAX_PAGES_PER_KEYWORD 页"""
        records, skipped, page = [], 0, 1
        while len(records) < quota and page <= MAX_PAGES_PER_KEYWORD:
            try:
                items, total = self._fetch(page, page_size, keyword, delay)
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
                    rec.keyword, rec.track = keyword or "", track or ""
                    seen.add(rec.job_id)
                    records.append(rec)
                    if len(records) >= quota:
                        break
            if total is not None and page * page_size >= total:
                break
            page += 1
        return records, skipped

    def crawl(self, max_jobs: int, delay: float = DEFAULT_DELAY, page_size: int = PAGE_SIZE,
              keyword=None, track=None) -> CrawlResult:
        """抓一个关键词（或不带关键词的默认列表）"""
        if not 1 <= max_jobs <= MAX_PER_KEYWORD:
            raise ValueError(f"--max-jobs 必须在 1 到 {MAX_PER_KEYWORD} 之间（小规模抓取，不追求大而全）")
        if delay < MIN_DELAY:
            raise ValueError(f"请求间隔不能低于 {MIN_DELAY} 秒")

        self._check_robots()
        self._requests = 0
        records, skipped = self._collect(keyword, max_jobs, set(), delay, page_size, track)
        return CrawlResult(records=records, skipped=skipped, pages=self._requests)

    def crawl_many(self, keywords, delay: float = DEFAULT_DELAY, page_size: int = PAGE_SIZE,
                   total_max: int = MAX_TOTAL_JOBS, per_keyword: int = MAX_PER_KEYWORD,
                   track_of=None) -> CrawlResult:
        """抓多个关键词。总量平均分给各关键词（再受 per_keyword 限制），保证每个方向都有数据"""
        keywords = list(keywords)
        if not keywords:
            raise ValueError("至少需要一个关键词")
        if not 1 <= total_max <= MAX_TOTAL_JOBS:
            raise ValueError(f"总量必须在 1 到 {MAX_TOTAL_JOBS} 之间")
        if not 1 <= per_keyword <= MAX_PER_KEYWORD:
            raise ValueError(f"每个关键词的条数必须在 1 到 {MAX_PER_KEYWORD} 之间")
        if delay < MIN_DELAY:
            raise ValueError(f"请求间隔不能低于 {MIN_DELAY} 秒")
        quota = min(per_keyword, total_max // len(keywords))
        if quota < 1:
            raise ValueError("总量太小，平均下来每个关键词不足 1 条；请减少关键词或提高总量")

        self._check_robots()
        self._requests = 0
        records, seen, skipped = [], set(), 0
        for keyword in keywords:
            if len(records) >= total_max:
                break
            try:
                got, skip = self._collect(keyword, quota, seen, delay, page_size,
                                          track_of(keyword) if track_of else None)
            except CrawlStopped as stop:
                stop.records = records + stop.records  # 前面关键词已经收集到的也要保留
                raise
            records += got
            skipped += skip
        return CrawlResult(records=records, skipped=skipped, pages=self._requests)


# ---------- 命令行 ----------

def main(argv=None, post_json=http_post_json, get_text=http_get_text, sleep=time.sleep, today=None,
         tracks=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    tracks = TRACKS if tracks is None else tracks

    parser = argparse.ArgumentParser(description="从国聘小规模抓取公开岗位（仅供个人学习）")
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--keyword", help="只抓一个关键词，如 数据分析")
    what.add_argument("--track", help="抓一个专业方向的所有关键词，如 数据")
    what.add_argument("--all", action="store_true", help="抓所有专业方向的所有关键词")
    parser.add_argument("--max-jobs", type=int, default=MAX_PER_KEYWORD,
                        help=f"只抓一个关键词时的条数，上限 {MAX_PER_KEYWORD}")
    parser.add_argument("--per-keyword", type=int, default=MAX_PER_KEYWORD, help="多个关键词时，每个最多几条")
    parser.add_argument("--total-max", type=int, default=MAX_TOTAL_JOBS, help=f"多个关键词时的总量，上限 {MAX_TOTAL_JOBS}")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"请求间隔秒数，不低于 {MIN_DELAY}")
    parser.add_argument("--output", default=str(CRAWLED_FILE), help="保存到这个 jobs.jsonl 文件")
    args = parser.parse_args(argv)

    today = today or datetime.date.today()
    crawler = Crawler(post_json=post_json, get_text=get_text, sleep=sleep, today=today)
    find_track = lambda keyword: default_track_of(keyword, tracks)  # noqa: E731

    try:
        if args.all or args.track:
            keywords = all_keywords(tracks) if args.all else keywords_for(args.track, tracks)
            result = crawler.crawl_many(keywords, args.delay, total_max=args.total_max,
                                        per_keyword=args.per_keyword, track_of=find_track)
        else:
            result = crawler.crawl(args.max_jobs, args.delay, keyword=args.keyword,
                                   track=find_track(args.keyword))
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        return 1
    except CrawlStopped as stop:
        print(f"已停止：{stop}", file=sys.stderr)
        if stop.records:
            saved = append_new([record_to_row(r, today) for r in stop.records], args.output)
            print(f"停止前已收集 {len(stop.records)} 条，新写入 {saved} 条到 {args.output}", file=sys.stderr)
        return 1

    saved = append_new([record_to_row(r, today) for r in result.records], args.output)
    print(f"完成：请求 {result.pages} 次，保留 {len(result.records)} 条，跳过 {result.skipped} 条"
          f"（过期或没有描述），新写入 {saved} 条到 {args.output}")
    print("这些数据仅供个人学习，目录已被 .gitignore 排除，不会被提交。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
