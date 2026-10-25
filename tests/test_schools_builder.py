import json

from resume_matcher.schools_builder import build_schools, extract_school_names, main


def table(*cells):
    """把若干单元格文字拼成一个最简的 HTML 表格"""
    return "<html><body><table><tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr></table></body></html>"


# ---------- extract_school_names ----------

def test_extracts_names_from_table_cells():
    assert extract_school_names(table("北京大学", "清华大学")) == ["北京大学", "清华大学"]


def test_extracts_names_wrapped_in_nested_tags():
    html = '<table><tr><td><p class="x"><span style="a">北京大学</span></p></td></tr></table>'
    assert extract_school_names(html) == ["北京大学"]


def test_strips_whitespace_and_nbsp():
    assert extract_school_names(table("  北京&nbsp;大学 ", "清华\n大学")) == ["北京大学", "清华大学"]


def test_ignores_cells_that_are_not_school_names():
    html = table("序号", "1", "注：本名单经教育部批准", "北京大学")
    assert extract_school_names(html) == ["北京大学"]


def test_keeps_names_with_parentheses():
    assert extract_school_names(table("中国石油大学（北京）")) == ["中国石油大学（北京）"]


def test_removes_duplicates_and_keeps_order():
    assert extract_school_names(table("清华大学", "北京大学", "清华大学")) == ["清华大学", "北京大学"]


def test_text_outside_tables_is_ignored():
    html = "<p>北京大学</p>" + table("清华大学")
    assert extract_school_names(html) == ["清华大学"]


def test_page_without_tables_gives_empty_list():
    assert extract_school_names("<html><body>没有表格</body></html>") == []


# ---------- build_schools ----------

def test_211_list_excludes_schools_already_in_985():
    data, _ = build_schools(["清华大学", "北京大学"], ["清华大学", "北京大学", "北京邮电大学"])
    assert data["985"] == ["清华大学", "北京大学"]
    assert data["211"] == ["北京邮电大学"]


def test_warns_when_985_school_is_missing_from_211_list():
    _, warnings = build_schools(["清华大学", "某某大学"], ["清华大学"])
    assert any("某某大学" in w for w in warnings)


def test_warns_when_counts_are_not_the_official_ones():
    _, warnings = build_schools(["清华大学"], ["清华大学", "北京邮电大学"])
    assert any("39" in w for w in warnings)
    assert any("112" in w for w in warnings)


def test_no_count_warning_when_counts_match_official_numbers():
    s985 = [f"九八五大学{i}" for i in range(39)]
    s211 = s985 + [f"二一一大学{i}" for i in range(73)]
    _, warnings = build_schools(s985, s211)
    assert warnings == []


# ---------- main ----------

PAGES = {
    "http://example.test/985": table("清华大学", "北京大学"),
    "http://example.test/211": table("清华大学", "北京大学", "北京邮电大学"),
}


def fake_fetch(url):
    return PAGES[url]


def run_main(tmp_path, *extra):
    return main(
        ["--output", str(tmp_path / "schools.json"), *extra],
        fetch=fake_fetch, url_985="http://example.test/985", url_211="http://example.test/211",
        delay=0,
    )


def test_main_without_write_flag_does_not_touch_the_file(tmp_path, capsys):
    out = tmp_path / "schools.json"
    out.write_text('{"985": [], "211": []}', encoding="utf-8")
    assert run_main(tmp_path) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"985": [], "211": []}
    assert "北京邮电大学" in capsys.readouterr().out  # 会显示将要新增的内容


def test_main_with_write_flag_writes_schools_and_sources(tmp_path):
    assert run_main(tmp_path, "--write") == 0
    data = json.loads((tmp_path / "schools.json").read_text(encoding="utf-8"))
    assert data["985"] == ["清华大学", "北京大学"]
    assert data["211"] == ["北京邮电大学"]
    assert "example.test/985" in json.dumps(data["来源"], ensure_ascii=False)


def test_main_fails_cleanly_when_a_page_has_no_schools(tmp_path, capsys):
    pages = {"http://example.test/985": "<html></html>", "http://example.test/211": table("清华大学")}
    code = main(["--output", str(tmp_path / "s.json"), "--write"], fetch=pages.__getitem__,
                url_985="http://example.test/985", url_211="http://example.test/211", delay=0)
    assert code == 1
    assert not (tmp_path / "s.json").exists()  # 抓到空结果时绝不能覆盖现有名单
