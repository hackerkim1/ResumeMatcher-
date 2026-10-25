import json
from datetime import date

import pytest

from resume_matcher.crawler import (
    HARD_MAX_JOBS,
    CrawlStopped,
    Crawler,
    build_body,
    check_response,
    html_to_text,
    main,
    parse_job,
    render_job_text,
    robots_allows,
    save_records,
)

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


# ---------- render_job_text ----------

def test_rendered_text_has_the_key_lines_and_the_description():
    text = render_job_text(parse_job(make_item(), TODAY))
    for expected in ["岗位：数据分析师", "单位：示例企业有限公司", "专业要求：统计学类、计算机类",
                     "学历要求：本科", "经验要求：1-3年", "薪资：10000-15000元/月", "熟悉 SQL 和 Python"]:
        assert expected in text


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


# ---------- Crawler ----------

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


def make_crawler(site, sleeps):
    return Crawler(post_json=site.post_json, get_text=site.get_text, sleep=sleeps.append, today=TODAY)


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


def test_crawl_passes_the_keyword_to_every_request():
    site = FakeSite([items("1"), items("2")], total=2)
    make_crawler(site, []).crawl(max_jobs=2, delay=1.0, page_size=1, keyword="数据分析")
    assert all(b["search"]["keyword"] == "数据分析" for b in site.posts)


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


def test_crawl_rejects_more_than_the_hard_limit():
    with pytest.raises(ValueError):
        make_crawler(FakeSite([]), []).crawl(max_jobs=HARD_MAX_JOBS + 1, delay=1.0)


def test_crawl_rejects_a_non_positive_max_jobs():
    with pytest.raises(ValueError):
        make_crawler(FakeSite([]), []).crawl(max_jobs=0, delay=1.0)


# ---------- save_records ----------

def records(*ids):
    return [parse_job(make_item(job_id=i, job_name=f"岗位{i}"), TODAY) for i in ids]


def test_save_writes_one_file_per_job_and_an_index(tmp_path):
    assert save_records(records("1", "2"), tmp_path, fetched_on=TODAY) == 2
    assert (tmp_path / "1.txt").read_text(encoding="utf-8").startswith("岗位：岗位1")
    lines = (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["job_id"] for l in lines] == ["1", "2"]
    assert json.loads(lines[0])["majors"] == ["统计学类", "计算机类"]
    assert json.loads(lines[0])["fetched_on"] == "2026-10-25"


def test_save_is_idempotent(tmp_path):
    save_records(records("1", "2"), tmp_path, fetched_on=TODAY)
    assert save_records(records("2", "3"), tmp_path, fetched_on=TODAY) == 1
    assert sorted(p.name for p in tmp_path.glob("*.txt")) == ["1.txt", "2.txt", "3.txt"]
    assert len((tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_save_never_writes_contact_details(tmp_path):
    save_records(records("1"), tmp_path, fetched_on=TODAY)
    everything = "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    assert "联系人张某" not in everything and "im-secret-123" not in everything


def test_save_rejects_unsafe_job_ids(tmp_path):
    bad = parse_job(make_item(job_id="../evil"), TODAY)
    with pytest.raises(ValueError):
        save_records([bad], tmp_path, fetched_on=TODAY)
    assert list(tmp_path.iterdir()) == []


# ---------- main ----------

def run_main(tmp_path, site, *extra):
    return main(
        ["--output", str(tmp_path / "out"), "--delay", "1", *extra],
        post_json=site.post_json, get_text=site.get_text, sleep=lambda s: None, today=TODAY,
    )


def test_main_saves_jobs_and_reports(tmp_path, capsys):
    site = FakeSite([items("1", "2")], total=2)
    assert run_main(tmp_path, site, "--max-jobs", "2") == 0
    assert (tmp_path / "out" / "1.txt").exists()
    assert "2" in capsys.readouterr().out


def test_main_reports_a_stop_and_exits_with_an_error(tmp_path, capsys):
    site = FakeSite([items("1")], robots=(200, "User-agent: *\nDisallow: /\n"))
    assert run_main(tmp_path, site) == 1
    assert "停止" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_main_saves_the_partial_result_when_stopped_midway(tmp_path, capsys):
    class HalfSite(FakeSite):
        def post_json(self, url, body):
            if body["search"]["page"] == 1:
                return 200, json.dumps(ok_payload(items("1", "2"), total=100))
            return 429, "{}"

    site = HalfSite([])
    assert run_main(tmp_path, site, "--max-jobs", "10") == 1
    assert (tmp_path / "out" / "1.txt").exists()
    assert "停止" in capsys.readouterr().err


def test_main_rejects_too_many_jobs(tmp_path, capsys):
    assert run_main(tmp_path, FakeSite([]), "--max-jobs", str(HARD_MAX_JOBS + 1)) == 1
    assert str(HARD_MAX_JOBS) in capsys.readouterr().err
