from resume_matcher.grounding import is_grounded, verify_checks
from resume_matcher.schemas import SkillCheck

RESUME = (
    "技能：Python、LangChain、Chroma、Streamlit、SQL、Git\n"
    "实习：使用 Python 和 SQL\n清洗业务数据，编写日报脚本。\n"
    "项目：基于 LangChain 和 Chroma 搭建 RAG 问答，用 scikit-learn 做文本分类。"
)


# ---------- is_grounded ----------

def test_exact_quote_is_grounded():
    assert is_grounded("基于 LangChain 和 Chroma 搭建 RAG 问答", RESUME)


def test_quote_with_added_annotation_is_still_grounded():
    # 模型常给原文加括号注释，这种判断本身是对的，不能误伤
    assert is_grounded("Chroma（属于向量数据库）", RESUME)


def test_quote_across_a_line_break_is_grounded():
    assert is_grounded("使用 Python 和 SQL 清洗业务数据", RESUME)


def test_matching_ignores_case():
    assert is_grounded("langchain", RESUME)


def test_short_ascii_token_counts():
    assert is_grounded("SQL", RESUME)
    assert not is_grounded("Redis", RESUME)


def test_hyphenated_token_is_not_split():
    assert is_grounded("scikit-learn", RESUME)


def test_none_marker_is_not_grounded():
    assert not is_grounded("无", RESUME)


def test_empty_evidence_is_not_grounded():
    assert not is_grounded("", RESUME)
    assert not is_grounded("   ", RESUME)


def test_fabricated_evidence_is_not_grounded():
    assert not is_grounded("使用 Docker 部署微服务", RESUME)


def test_short_common_chinese_fragment_is_not_enough():
    # “使用”只有 2 个字，且很常见，不能单独当作证据
    assert not is_grounded("使用 Kubernetes 编排", RESUME)


# ---------- verify_checks ----------

def check(skill, matched, evidence):
    return SkillCheck(skill=skill, matched=matched, evidence=evidence)


def test_grounded_match_is_kept():
    out = verify_checks([check("SQL", True, "使用 Python 和 SQL")], RESUME)
    assert out[0].matched is True
    assert out[0].evidence == "使用 Python 和 SQL"


def test_ungrounded_match_is_downgraded_and_marked():
    out = verify_checks([check("Docker", True, "使用 Docker 部署微服务")], RESUME)
    assert out[0].matched is False
    assert out[0].evidence.startswith("【依据存疑】")
    assert "使用 Docker 部署微服务" in out[0].evidence  # 保留模型原话，方便人工查看


def test_unmatched_check_is_left_untouched():
    original = check("Redis", False, "无")
    assert verify_checks([original], RESUME) == [original]


def test_verify_does_not_mutate_input():
    original = check("Docker", True, "使用 Docker 部署微服务")
    verify_checks([original], RESUME)
    assert original.matched is True
