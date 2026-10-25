import json
from datetime import date

import pytest

from resume_matcher.crawler import (
    MAX_PAGES_PER_KEYWORD,
    MAX_PER_KEYWORD,
    MAX_REQUESTS,
    MAX_TOTAL_JOBS,
    CrawlStopped,
    Crawler,
    build_body,
    check_response,
    html_to_text,
    main,
    parse_job,
    record_to_row,
    render_job_text,
    robots_allows,
)
from resume_matcher.jobsfile import read_rows
from resume_matcher.tracks import all_keywords

TODAY = date(2026, 10, 25)


def make_item(job_id="100", **overrides):
    """按真实接口观察到的字段结构造的假数据（公司、联系人都是虚构的）"""
    item = {
        "job_id": job_id,
        "job_name": "数据分析师",
        "company_name": "示例企业有限公司",
        "contents": '<span style="font-size:14px">岗位职责：<br />1.负责数据分析&nbsp;和报表<br />'
                    "任职要求：<br />1.熟悉 SQL 和 Python</span>",
        "category_cn": "科研、咨询",
        "major_cn": ["统计学类", "计算机类"],
        "education_cn": "本科",
        "experience_cn": "1-3年",
        "nature_cn": "社招",
        "min_wage": 10000,
        "max_wage": 15000,
        "wage_unit_cn": "元/月",
        "is_negotiable": False,
        "update_time": "2026-10-23 13:45:03",
        "end_time": "2026-11-30 23:59:59",
        "contact_user": {"id": "9", "name": "联系人张某", "im_id": "im-secret-123"},
        "user_id": "user-secret-456",
        "company_id": "company-secret-789",
    }
    item.update(overrides)
    return item


def ok_payload(items, total=None):
    return {"code": 200, "msg": "OK", "data": {"total": len(items) if total is None else total, "list": items}}


# ---------- html_to_text ----------

def test_html_to_text_turns_breaks_into_newlines_and_drops_tags():
    text = html_to_text('<span style="x">岗位职责：<br />1.负责分析<br/>2.写报告</span>')
    assert text.splitlines() == ["岗位职责：", "1.负责分析", "2.写报告"]


def test_html_to_text_handles_entities_and_nbsp():
    assert html_to_text("A&nbsp;B &amp; C&lt;D") == "A B & C<D"


def test_html_to_text_collapses_blank_lines():
    assert html_to_text("a<br /><br /><br />b") == "a\nb"


def test_html_to_text_of_empty_input_is_empty():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


# ---------- parse_job ----------

def test_parse_job_maps_the_fields_we_keep():
    rec = parse_job(make_item(), TODAY)
    assert rec.job_id == "100"
    assert rec.title == "数据分析师"
    assert rec.company == "示例企业有限公司"
    assert rec.majors == ["统计学类", "计算机类"]
    assert rec.education == "本科"
    assert rec.experience == "1-3年"
    assert rec.salary == "10000-15000元/月"
    assert "负责数据分析 和报表" in rec.jd_text


def test_parse_job_never_keeps_contact_or_internal_ids():
    rec = parse_job(make_item(), TODAY)
    everything = json.dumps(rec.__dict__, ensure_ascii=False) + render_job_text(rec)
    for secret in ["联系人张某", "im-secret-123", "user-secret-456", "company-secret-789"]:
        assert secret not in everything


def test_parse_job_skips_expired_postings():
    assert parse_job(make_item(end_time="2026-10-24 23:59:59"), TODAY) is None


def test_parse_job_keeps_a_posting_that_ends_today():
    assert parse_job(make_item(end_time="2026-10-25 23:59:59"), TODAY) is not None


def test_parse_job_skips_postings_without_description_or_id_or_title():
    assert parse_job(make_item(contents=""), TODAY) is None
    assert parse_job(make_item(contents="<br />"), TODAY) is None
    assert parse_job(make_item(job_id=""), TODAY) is None
    assert parse_job(make_item(job_name=""), TODAY) is None


def test_parse_job_tolerates_an_unparseable_end_time():
    assert parse_job(make_item(end_time="长期有效"), TODAY) is not None
    assert parse_job(make_item(end_time=None), TODAY) is not None


def test_salary_text_for_negotiable_and_undisclosed():
    assert parse_job(make_item(is_negotiable=True), TODAY).salary == "面议"
    assert parse_job(make_item(min_wage=0, max_wage=0), TODAY).salary == "未公布"


def test_duplicate_majors_are_removed_and_order_is_kept():
    # 真实数据里出现过同一个专业类重复两次的情况
    rec = parse_job(make_item(major_cn=["工商管理类", "金融类", "工商管理类", " "]), TODAY)
    assert rec.majors == ["工商管理类", "金融类"]


def test_missing_majors_means_unrestricted():
    rec = parse_job(make_item(major_cn=None), TODAY)
    assert rec.majors == []
    assert "专业要求：不限" in render_job_text(rec)


def test_a_placeholder_instead_of_a_major_means_unrestricted():
    # 真实数据里出现过“详见职位描述”，它不是专业类别
    assert parse_job(make_item(major_cn=["详见职位描述"]), TODAY).majors == []
    assert parse_job(make_item(major_cn=["详见职位描述", "金融类"]), TODAY).majors == ["金融类"]


# ---------- render_job_text / record_to_row ----------

def test_rendered_text_has_the_key_lines_and_the_description():
    text = render_job_text(parse_job(make_item(), TODAY))
    for expected in ["岗位：数据分析师", "单位：示例企业有限公司", "专业要求：统计学类、计算机类",
                     "学历要求：本科", "经验要求：1-3年", "薪资：10000-15000元/月", "熟悉 SQL 和 Python"]:
        assert expected in text


def test_record_to_row_carries_the_text_and_the_metadata():
    rec = parse_job(make_item(), TODAY)
    rec.keyword, rec.track = "数据分析", "数据"
    row = record_to_row(rec, TODAY)
    assert row["job_id"] == "100" and row["title"] == "数据分析师"
    assert row["keyword"] == "数据分析" and row["track"] == "数据"
    assert row["majors"] == ["统计学类", "计算机类"]
    assert row["source"] == "iguopin" and row["fetched_on"] == "2026-10-25"
    assert row["text"] == render_job_text(rec)


def test_record_to_row_never_contains_contact_details():
    row = record_to_row(parse_job(make_item(), TODAY), TODAY)
    everything = json.dumps(row, ensure_ascii=False)
    for secret in ["联系人张某", "im-secret-123", "user-secret-456", "company-secret-789"]:
        assert secret not in everything


# ---------- build_body ----------

def test_body_has_page_and_size_and_no_keyword_by_default():
    body = build_body(page=2, page_size=20)
    assert body["search"] == {"page": 2, "page_size": 20}
    assert "recom" in body


def test_body_includes_the_keyword_when_given():
    assert build_body(1, 20, keyword="数据分析")["search"]["keyword"] == "数据分析"


# ---------- robots ----------

def test_no_robots_page_means_no_restriction():
    assert robots_allows("", "https://x.test/api/jobs/v1/recom-job")
    assert robots_allows("<!DOCTYPE html><html>找不到该页</html>", "https://x.test/api/jobs/v1/recom-job")


def test_empty_disallow_allows_everything():
    assert robots_allows("User-agent: *\nDisallow:\n", "https://x.test/api/jobs/v1/recom-job")


def test_a_matching_disallow_blocks():
    robots = "User-agent: *\nDisallow: /api/jobs/\n"
    assert not robots_allows(robots, "https://x.test/api/jobs/v1/recom-job")
    assert robots_allows(robots, "https://x.test/api/base/site")


def test_a_blanket_disallow_blocks_everything():
    assert not robots_allows("User-agent: *\nDisallow: /\n", "https://x.test/api/jobs/v1/recom-job")


# ---------- check_response ----------

def test_check_response_returns_the_list_for_a_normal_reply():
    items, total = check_response(200, json.dumps(ok_payload([make_item()], total=60)))
    assert len(items) == 1 and total == 60


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_check_response_stops_on_bad_http_status(status):
    with pytest.raises(CrawlStopped):
        check_response(status, "{}")


def test_check_response_stops_when_the_body_is_not_json():
    with pytest.raises(CrawlStopped):
        check_response(200, "<html>请完成验证</html>")


def test_check_response_stops_on_a_business_error_code():
    with pytest.raises(CrawlStopped):
        check_response(200, json.dumps({"code": 401, "msg": "请先登录", "data": None}))


def test_check_response_stops_when_the_structure_is_unexpected():
    with pytest.raises(CrawlStopped):
        check_response(200, json.dumps({"code": 200, "msg": "OK", "data": {"nope": 1}}))


# ---------- Crawler.crawl（单个关键词） ----------

class FakeSite:
    """按页返回假数据，并记录被调用的次数"""

    def __init__(self, pages, total=None, robots=(404, "")):
        self.pages, self.total, self.robots = pages, total, robots
        self.posts, self.gets = [], []

    def get_text(self, url):
        self.gets.append(url)
        return self.robots

    def post_json(self, url, body):
        self.posts.append(body)
        page = body["search"]["page"]
        items = self.pages[page - 1] if page <= len(self.pages) else []
        return 200, json.dumps(ok_payload(items, total=self.total))


def make_crawler(site, sleeps, **kwargs):
    return Crawler(post_json=site.post_json, get_text=site.get_text, sleep=sleeps.append, today=TODAY, **kwargs)


def items(*ids):
    return [make_item(job_id=i, job_name=f"岗位{i}") for i in ids]


def test_crawl_collects_across_pages_and_stops_at_max_jobs():
    site = FakeSite([items("1", "2"), items("3", "4"), items("5", "6")], total=6)
    result = make_crawler(site, []).crawl(max_jobs=3, delay=1.0, page_size=2)
    assert [r.job_id for r in result.records] == ["1", "2", "3"]
    assert len(site.posts) == 2  # 够了就不再请求第 3 页


def test_crawl_sleeps_between_requests_but_not_before_the_first():
    site = FakeSite([items("1"), items("2"), items("3")], total=3)
    sleeps = []
    make_crawler(site, sleeps).crawl(max_jobs=3, delay=2.5, page_size=1)
    assert len(site.posts) == 3
    assert sleeps == [2.5, 2.5]


def test_crawl_removes_duplicates():
    site = FakeSite([items("1", "2"), items("2", "3")], total=4)
    result = make_crawler(site, []).crawl(max_jobs=10, delay=1.0, page_size=2)
    assert [r.job_id for r in result.records] == ["1", "2", "3"]


def test_crawl_stops_on_an_empty_page():
    site = FakeSite([items("1"), []], total=99)
    result = make_crawler(site, []).crawl(max_jobs=10, delay=1.0, page_size=1)
    assert [r.job_id for r in result.records] == ["1"]
    assert len(site.posts) == 2


def test_crawl_stops_once_the_reported_total_is_reached():
    site = FakeSite([items("1", "2")], total=2)
    make_crawler(site, []).crawl(max_jobs=10, delay=1.0, page_size=2)
    assert len(site.posts) == 1


def test_crawl_counts_skipped_expired_postings():
    expired = make_item(job_id="9", end_time="2026-01-01 00:00:00")
    site = FakeSite([[make_item(job_id="1"), expired]], total=2)
    result = make_crawler(site, []).crawl(max_jobs=10, delay=1.0, page_size=2)
    assert [r.job_id for r in result.records] == ["1"]
    assert result.skipped == 1


def test_crawl_passes_the_keyword_to_every_request_and_tags_the_records():
    site = FakeSite([items("1"), items("2")], total=2)
    result = make_crawler(site, []).crawl(max_jobs=2, delay=1.0, page_size=1, keyword="数据分析")
    assert all(b["search"]["keyword"] == "数据分析" for b in site.posts)
    assert {r.keyword for r in result.records} == {"数据分析"}


def test_crawl_makes_no_job_request_when_robots_forbids_it():
    site = FakeSite([items("1")], robots=(200, "User-agent: *\nDisallow: /\n"))
    with pytest.raises(CrawlStopped):
        make_crawler(site, []).crawl(max_jobs=3, delay=1.0)
    assert site.posts == []


def test_crawl_refuses_when_robots_cannot_be_read():
    def broken_get(url):
        raise OSError("network down")

    site = FakeSite([items("1")])
    crawler = Crawler(post_json=site.post_json, get_text=broken_get, sleep=lambda s: None, today=TODAY)
    with pytest.raises(CrawlStopped):
        crawler.crawl(max_jobs=3, delay=1.0)
    assert site.posts == []


def test_crawl_stops_without_retrying_when_the_site_asks_for_login():
    calls = []

    def post_json(url, body):
        calls.append(body)
        return 200, json.dumps({"code": 401, "msg": "请先登录", "data": None})

    crawler = Crawler(post_json=post_json, get_text=lambda u: (404, ""), sleep=lambda s: None, today=TODAY)
    with pytest.raises(CrawlStopped):
        crawler.crawl(max_jobs=5, delay=1.0)
    assert len(calls) == 1


def test_a_stop_in_the_middle_keeps_what_was_already_collected_and_asks_for_nothing_more():
    calls = []

    def post_json(url, body):
        calls.append(body["search"]["page"])
        if body["search"]["page"] == 1:
            return 200, json.dumps(ok_payload(items("1", "2"), total=10))
        return 403, "{}"

    crawler = Crawler(post_json=post_json, get_text=lambda u: (404, ""), sleep=lambda s: None, today=TODAY)
    with pytest.raises(CrawlStopped) as stop:
        crawler.crawl(max_jobs=10, delay=1.0, page_size=2)
    assert [r.job_id for r in stop.value.records] == ["1", "2"]
    assert calls == [1, 2]  # 被拦下之后没有再请求第 3 页，也没有重试第 2 页


def test_crawl_rejects_a_delay_below_the_minimum():
    with pytest.raises(ValueError):
        make_crawler(FakeSite([]), []).crawl(max_jobs=3, delay=0.2)


def test_crawl_rejects_more_than_the_per_keyword_limit():
    with pytest.raises(ValueError):
        make_crawler(FakeSite([]), []).crawl(max_jobs=MAX_PER_KEYWORD + 1, delay=1.0)


def test_crawl_rejects_a_non_positive_max_jobs():
    with pytest.raises(ValueError):
        make_crawler(FakeSite([]), []).crawl(max_jobs=0, delay=1.0)


# ---------- Crawler.crawl_many（多个关键词） ----------

class KeywordSite:
    """按关键词返回不同的岗位：每个关键词有自己的一串岗位编号"""

    def __init__(self, by_keyword, robots=(404, ""), expired=False):
        self.by_keyword, self.robots, self.expired = by_keyword, robots, expired
        self.posts, self.gets = [], []

    def get_text(self, url):
        self.gets.append(url)
        return self.robots

    def post_json(self, url, body):
        self.posts.append(body)
        keyword = body["search"].get("keyword")
        page, size = body["search"]["page"], body["search"]["page_size"]
        ids = self.by_keyword.get(keyword, [])
        end = "2000-01-01 00:00:00" if self.expired else "2026-12-31 23:59:59"
        chunk = [make_item(job_id=i, job_name=f"岗位{i}", end_time=end) for i in ids[(page - 1) * size: page * size]]
        return 200, json.dumps(ok_payload(chunk, total=len(ids)))


TRACK_OF = {"a": "T1", "b": "T1", "c": "T2"}.get


def ids_of(result):
    return [r.job_id for r in result.records]


def test_crawl_many_collects_every_keyword_and_tags_keyword_and_track():
    site = KeywordSite({"a": ["1", "2"], "b": ["3"], "c": ["4"]})
    result = make_crawler(site, []).crawl_many(["a", "b", "c"], delay=1.0, track_of=TRACK_OF)
    assert ids_of(result) == ["1", "2", "3", "4"]
    by_id = {r.job_id: (r.keyword, r.track) for r in result.records}
    assert by_id == {"1": ("a", "T1"), "2": ("a", "T1"), "3": ("b", "T1"), "4": ("c", "T2")}


def test_crawl_many_removes_jobs_found_by_more_than_one_keyword():
    site = KeywordSite({"a": ["1", "2"], "b": ["2", "3"]})
    result = make_crawler(site, []).crawl_many(["a", "b"], delay=1.0, track_of=TRACK_OF)
    assert ids_of(result) == ["1", "2", "3"]
    assert {r.job_id: r.keyword for r in result.records}["2"] == "a"  # 先找到它的关键词


def test_crawl_many_shares_the_total_evenly_so_no_track_is_starved():
    many = [str(i) for i in range(10)]
    site = KeywordSite({"a": [f"a{i}" for i in many], "b": [f"b{i}" for i in many], "c": [f"c{i}" for i in many]})
    result = make_crawler(site, []).crawl_many(["a", "b", "c"], delay=1.0, total_max=6, track_of=TRACK_OF)
    assert len(result.records) == 6
    assert sorted(r.keyword for r in result.records) == ["a", "a", "b", "b", "c", "c"]


def test_crawl_many_never_gives_a_keyword_more_than_the_per_keyword_cap():
    site = KeywordSite({"a": [f"a{i}" for i in range(10)], "b": [f"b{i}" for i in range(10)]})
    result = make_crawler(site, []).crawl_many(["a", "b"], delay=1.0, per_keyword=3, track_of=TRACK_OF)
    assert len(result.records) == 6


def test_crawl_many_sleeps_between_every_two_requests_across_keywords():
    site = KeywordSite({"a": ["1"], "b": ["2"]})
    sleeps = []
    make_crawler(site, sleeps).crawl_many(["a", "b"], delay=2.0, track_of=TRACK_OF)
    assert len(site.posts) == 2
    assert sleeps == [2.0]


def test_crawl_many_reads_robots_only_once():
    site = KeywordSite({"a": ["1"], "b": ["2"]})
    make_crawler(site, []).crawl_many(["a", "b"], delay=1.0, track_of=TRACK_OF)
    assert len(site.gets) == 1


def test_crawl_many_makes_no_job_request_when_robots_forbids_it():
    site = KeywordSite({"a": ["1"]}, robots=(200, "User-agent: *\nDisallow: /\n"))
    with pytest.raises(CrawlStopped):
        make_crawler(site, []).crawl_many(["a"], delay=1.0, track_of=TRACK_OF)
    assert site.posts == []


def test_crawl_many_stops_at_the_global_request_limit():
    site = KeywordSite({"a": ["1"], "b": ["2"], "c": ["3"]})
    with pytest.raises(CrawlStopped) as stop:
        make_crawler(site, [], max_requests=2).crawl_many(["a", "b", "c"], delay=1.0, track_of=TRACK_OF)
    assert len(site.posts) == 2
    assert [r.job_id for r in stop.value.records] == ["1", "2"]


def test_the_default_request_limit_is_small():
    assert MAX_REQUESTS <= 60


def test_the_total_cap_leaves_a_useful_quota_per_keyword():
    # 总量上限平均分给每个关键词；方向表里的关键词太多，每个方向就几乎没有数据
    assert MAX_TOTAL_JOBS // len(all_keywords()) >= 8


def test_crawling_every_keyword_fits_inside_the_request_limit():
    # 每个关键词最多 3 页，但正常情况下 1 页就够；至少保证“每个关键词 1 页”不会超过全局请求上限
    assert len(all_keywords()) <= MAX_REQUESTS


def test_crawl_many_does_not_page_forever_when_everything_is_expired():
    site = KeywordSite({"a": [str(i) for i in range(100)]}, expired=True)
    result = make_crawler(site, []).crawl_many(["a"], delay=1.0, page_size=2, track_of=TRACK_OF)
    assert len(site.posts) == MAX_PAGES_PER_KEYWORD
    assert result.records == [] and result.skipped == MAX_PAGES_PER_KEYWORD * 2


def test_crawl_many_keeps_earlier_keywords_when_a_later_one_is_blocked():
    class BlockOnB(KeywordSite):
        def post_json(self, url, body):
            if body["search"].get("keyword") == "b":
                self.posts.append(body)
                return 429, "{}"
            return super().post_json(url, body)

    site = BlockOnB({"a": ["1", "2"], "b": ["3"], "c": ["4"]})
    with pytest.raises(CrawlStopped) as stop:
        make_crawler(site, []).crawl_many(["a", "b", "c"], delay=1.0, track_of=TRACK_OF)
    assert [r.job_id for r in stop.value.records] == ["1", "2"]
    assert all(b["search"].get("keyword") != "c" for b in site.posts)  # 被拦下后没有再去请求后面的关键词


@pytest.mark.parametrize("kwargs", [
    {"keywords": []},
    {"keywords": ["a"], "total_max": MAX_TOTAL_JOBS + 1},
    {"keywords": ["a"], "per_keyword": MAX_PER_KEYWORD + 1},
    {"keywords": ["a"], "per_keyword": 0},
    {"keywords": ["a", "b", "c"], "total_max": 2},  # 平均下来每个关键词不足 1 条
    {"keywords": ["a"], "delay": 0.1},
])
def test_crawl_many_rejects_bad_arguments_before_any_request(kwargs):
    site = KeywordSite({"a": ["1"]})
    kwargs.setdefault("delay", 1.0)
    with pytest.raises(ValueError):
        make_crawler(site, []).crawl_many(track_of=TRACK_OF, **kwargs)
    assert site.posts == [] and site.gets == []


# ---------- main ----------

TRACKS = {"T1": ["a", "b"], "T2": ["c"]}


def run_main(tmp_path, site, *extra):
    return main(
        ["--output", str(tmp_path / "jobs.jsonl"), "--delay", "1", *extra],
        post_json=site.post_json, get_text=site.get_text, sleep=lambda s: None, today=TODAY, tracks=TRACKS,
    )


def test_main_single_keyword_saves_jobs_and_reports(tmp_path, capsys):
    site = FakeSite([items("1", "2")], total=2)
    assert run_main(tmp_path, site, "--max-jobs", "2") == 0
    assert [r["job_id"] for r in read_rows(tmp_path / "jobs.jsonl")] == ["1", "2"]
    assert "2" in capsys.readouterr().out


def test_main_all_crawls_every_keyword_of_every_track(tmp_path):
    site = KeywordSite({"a": ["1"], "b": ["2"], "c": ["3"]})
    assert run_main(tmp_path, site, "--all") == 0
    rows = {r["job_id"]: r["track"] for r in read_rows(tmp_path / "jobs.jsonl")}
    assert rows == {"1": "T1", "2": "T1", "3": "T2"}


def test_main_track_crawls_only_that_tracks_keywords(tmp_path):
    site = KeywordSite({"a": ["1"], "b": ["2"], "c": ["3"]})
    assert run_main(tmp_path, site, "--track", "T2") == 0
    assert [r["job_id"] for r in read_rows(tmp_path / "jobs.jsonl")] == ["3"]


def test_main_unknown_track_lists_the_valid_ones(tmp_path, capsys):
    assert run_main(tmp_path, KeywordSite({}), "--track", "没有这个方向") == 1
    assert "T1" in capsys.readouterr().err


def test_main_rejects_combining_all_with_a_keyword(tmp_path):
    with pytest.raises(SystemExit):
        run_main(tmp_path, KeywordSite({}), "--all", "--keyword", "a")


def test_main_running_twice_does_not_duplicate_jobs(tmp_path):
    site = KeywordSite({"a": ["1"], "b": ["2"], "c": ["3"]})
    run_main(tmp_path, site, "--all")
    run_main(tmp_path, site, "--all")
    assert len(read_rows(tmp_path / "jobs.jsonl")) == 3


def test_main_reports_a_stop_and_exits_with_an_error(tmp_path, capsys):
    site = FakeSite([items("1")], robots=(200, "User-agent: *\nDisallow: /\n"))
    assert run_main(tmp_path, site) == 1
    assert "停止" in capsys.readouterr().err
    assert not (tmp_path / "jobs.jsonl").exists()


def test_main_saves_the_partial_result_when_stopped_midway(tmp_path, capsys):
    class HalfSite(FakeSite):
        def post_json(self, url, body):
            if body["search"]["page"] == 1:
                return 200, json.dumps(ok_payload(items("1", "2"), total=100))
            return 429, "{}"

    assert run_main(tmp_path, HalfSite([]), "--max-jobs", "10") == 1
    assert [r["job_id"] for r in read_rows(tmp_path / "jobs.jsonl")] == ["1", "2"]
    assert "停止" in capsys.readouterr().err


def test_main_partial_result_of_a_multi_keyword_run_is_saved(tmp_path):
    class BlockOnB(KeywordSite):
        def post_json(self, url, body):
            if body["search"].get("keyword") == "b":
                return 403, "{}"
            return super().post_json(url, body)

    assert run_main(tmp_path, BlockOnB({"a": ["1"], "b": ["2"]}), "--all") == 1
    assert [r["job_id"] for r in read_rows(tmp_path / "jobs.jsonl")] == ["1"]


def test_main_rejects_too_many_jobs_for_one_keyword(tmp_path, capsys):
    assert run_main(tmp_path, FakeSite([]), "--max-jobs", str(MAX_PER_KEYWORD + 1)) == 1
    assert str(MAX_PER_KEYWORD) in capsys.readouterr().err


def test_main_rejects_a_total_above_the_hard_cap(tmp_path, capsys):
    assert run_main(tmp_path, KeywordSite({}), "--all", "--total-max", str(MAX_TOTAL_JOBS + 1)) == 1
    assert str(MAX_TOTAL_JOBS) in capsys.readouterr().err
