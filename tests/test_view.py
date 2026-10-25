from types import SimpleNamespace

from resume_matcher.grounding import SUSPECT_PREFIX
from resume_matcher.schemas import SkillCheck
from resume_matcher.view import education_rows, rate_rows, ranking_rows, skill_rows


def check(skill, matched, evidence):
    return SkillCheck(skill=skill, matched=matched, evidence=evidence)


# ---------- skill_rows ----------

def test_matched_skill_shows_its_evidence():
    row = skill_rows([check("Python", True, "技能：Python")])[0]
    assert row == {"状态": "✓ 满足", "技能": "Python", "依据": "技能：Python"}


def test_unmatched_skill_shows_a_dash_instead_of_the_none_marker():
    row = skill_rows([check("Redis", False, "无")])[0]
    assert row["状态"] == "✗ 未体现"
    assert row["依据"] == "—"


def test_unmatched_skill_with_a_real_note_keeps_it():
    row = skill_rows([check("MySQL", False, "模型未给出判断")])[0]
    assert row["依据"] == "模型未给出判断"


def test_suspect_skill_is_marked_apart_from_a_plain_miss():
    row = skill_rows([check("Docker", False, f"{SUSPECT_PREFIX}用 Docker 部署了服务")])[0]
    assert row["状态"] == "⚠ 依据存疑"
    assert "用 Docker 部署了服务" in row["依据"]
    assert SUSPECT_PREFIX not in row["依据"]  # 前缀只是内部标记，不展示给用户
    assert "找不到" in row["依据"]


def test_rows_keep_the_input_order():
    rows = skill_rows([check("B", True, "x"), check("A", False, "无")])
    assert [r["技能"] for r in rows] == ["B", "A"]


def test_no_checks_gives_no_rows():
    assert skill_rows([]) == []


# ---------- education_rows ----------

def test_education_rows_cover_degree_and_school_with_icons():
    education = {
        "degree": {"status": "满足", "detail": "要求本科，简历为本科"},
        "school": {"status": "无法判断", "detail": "某某学院不在院校名单中"},
    }
    rows = education_rows(education)
    assert rows[0] == {"项目": "学历", "结果": "✓ 满足", "说明": "要求本科，简历为本科"}
    assert rows[1]["项目"] == "学校"
    assert rows[1]["结果"] == "？ 无法判断"


def test_education_icons_for_every_status():
    def result(status):
        return education_rows({"degree": {"status": status, "detail": ""},
                               "school": {"status": "未要求", "detail": ""}})[0]["结果"]

    assert result("不满足") == "✗ 不满足"
    assert result("未要求") == "— 未要求"


# ---------- ranking_rows ----------

def rec(title, score, source, distance):
    return SimpleNamespace(source=source, distance=distance,
                           result=SimpleNamespace(score=score, job=SimpleNamespace(title=title)))


def test_ranking_rows_number_the_recommendations_in_order():
    rows = ranking_rows([rec("岗位甲", 82, "a.txt", 0.86012), rec("岗位乙", 24, "b.txt", 0.9634)])
    assert rows == [
        {"排名": 1, "岗位": "岗位甲", "总分": 82, "文件": "a.txt", "检索距离": 0.86},
        {"排名": 2, "岗位": "岗位乙", "总分": 24, "文件": "b.txt", "检索距离": 0.963},
    ]


def test_ranking_rows_put_the_score_before_the_wide_columns():
    # 窄屏下后面的列会被挤出去，最重要的总分必须排在前面
    row = ranking_rows([rec("岗位甲", 82, "a.txt", 0.86)])[0]
    assert list(row)[:3] == ["排名", "总分", "岗位"]


def test_ranking_rows_for_no_recommendations_is_empty():
    assert ranking_rows([]) == []


# ---------- rate_rows ----------

def test_rate_rows_use_chinese_labels_and_a_fixed_order():
    rows = rate_rows({"preferred": 0.5, "required": 1.0, "years": 0.25})
    assert rows == [("必备技能", 1.0), ("年限", 0.25), ("加分项", 0.5)]


def test_rate_rows_skip_missing_dimensions():
    assert rate_rows({"required": 0.5}) == [("必备技能", 0.5)]


def test_rate_rows_for_no_dimensions_is_empty():
    assert rate_rows({}) == []
