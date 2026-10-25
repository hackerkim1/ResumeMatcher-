"""网页入口：streamlit run app.py

页面只负责收输入、调用 analyze() / recommend()、展示结果，核心逻辑都在 resume_matcher 包里。
"""
from contextlib import contextmanager

import streamlit as st

from resume_matcher.config import CRAWLED_FILE, JOBS_DIR
from resume_matcher.documents import DocumentError, resolve_input
from resume_matcher.jobsfile import read_rows, tracks_in
from resume_matcher.llm import MissingApiKeyError
from resume_matcher.pipeline import analyze
from resume_matcher.recommend import recommend
from resume_matcher.services import build_crawled_library, build_library, build_services
from resume_matcher.view import ranking_rows, render_result

st.set_page_config(page_title="简历 × 岗位匹配", page_icon="📄", layout="wide")

SOURCE_SAMPLES = "样例岗位"
SOURCE_CRAWLED = "抓取的岗位（国聘）"
ALL_TRACKS = "全部"


@st.cache_resource(show_spinner=False)
def _cached_services():
    """模型和链只创建一次；Streamlit 每次交互都会重跑整个脚本"""
    return build_services()


def get_services():
    # 测试时可以往 session_state 里放一个假的服务对象
    return st.session_state.get("_services") or _cached_services()


def get_crawled_rows():
    """抓取的岗位（jobs.jsonl）。测试时可以往 session_state 里注入，不依赖本机有没有抓取过"""
    if "_crawled_rows" in st.session_state:
        return st.session_state["_crawled_rows"]
    return read_rows(CRAWLED_FILE)


def get_library(source: str):
    """返回 (岗位库, 同步统计)。每次推荐前都同步一次，新放进去或新抓取的岗位会自动加入"""
    factory = st.session_state.get("_library_factory")
    if factory:
        return factory(source)
    return build_crawled_library(CRAWLED_FILE) if source == "crawled" else build_library(JOBS_DIR)


def upload_parts(uploaded):
    return (uploaded.name, uploaded.getvalue()) if uploaded else (None, None)


@contextmanager
def guarded():
    """把可预见的问题显示成友好的提示；意外的错误只显示类型，避免带出 key 的片段"""
    try:
        yield
    except (DocumentError, MissingApiKeyError) as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"分析失败：{type(e).__name__}，请稍后重试或检查网络与模型配置")


st.title("简历 × 岗位匹配分析器")
st.caption("上传简历和岗位描述，查看匹配分数、技能缺口、修改建议和面试题。"
           "简历只在内存中处理，不会保存到磁盘。")

tab_match, tab_recommend = st.tabs(["单岗位匹配", "岗位库推荐"])

# ---------- 单岗位匹配 ----------
with tab_match:
    left, right = st.columns(2)
    with left:
        st.subheader("简历")
        resume_file = st.file_uploader("上传简历（txt 或 pdf）", type=["txt", "pdf"], key="resume_file")
        resume_pasted = st.text_area("或直接粘贴简历文字", height=220, key="resume_text")
    with right:
        st.subheader("岗位描述")
        job_file = st.file_uploader("上传岗位描述（txt）", type=["txt"], key="job_file")
        job_pasted = st.text_area("或直接粘贴岗位描述", height=220, key="job_text")

    if st.button("开始分析", type="primary", key="run_match"):
        st.session_state.pop("match_result", None)  # 这次失败时，不能还显示着上一次的结果
        with guarded():
            resume_text = resolve_input("简历", *upload_parts(resume_file), resume_pasted)
            jd_text = resolve_input("岗位描述", *upload_parts(job_file), job_pasted)
            with st.spinner("正在分析，通常需要十几秒……"):
                s = get_services()
                st.session_state["match_result"] = analyze(
                    resume_text, jd_text, s.resume_chain, s.job_chain, s.match_chain, s.cache, s.schools)

    if st.session_state.get("match_result"):
        st.divider()
        render_result(st.session_state["match_result"])

# ---------- 岗位库推荐 ----------
with tab_recommend:
    crawled_rows = get_crawled_rows()
    left, right = st.columns(2)
    with left:
        st.subheader("简历")
        rec_resume_file = st.file_uploader("上传简历（txt 或 pdf）", type=["txt", "pdf"], key="rec_resume_file")
        rec_resume_pasted = st.text_area("或直接粘贴简历文字", height=220, key="rec_resume_text")
    with right:
        st.subheader("岗位库")
        source = "samples"
        if crawled_rows:
            choice = st.radio("岗位来源", [SOURCE_SAMPLES, SOURCE_CRAWLED], key="rec_source", horizontal=True)
            source = "crawled" if choice == SOURCE_CRAWLED else "samples"

        track = ALL_TRACKS
        if source == "crawled":
            n_jobs = len(crawled_rows)
            st.write(f"抓取的岗位共有 **{n_jobs}** 个，仅供个人学习使用，不要公开或再分发。")
            track = st.selectbox("专业方向", [ALL_TRACKS, *tracks_in(crawled_rows)], key="rec_track")
        else:
            n_jobs = len(list(JOBS_DIR.glob("*.txt")))
            folder = f"{JOBS_DIR.parent.name}/{JOBS_DIR.name}"
            if n_jobs:
                st.write(f"`{folder}` 下共有 **{n_jobs}** 个岗位文件。新放进去的 .txt 岗位文件，下次推荐时会自动加入。")
            else:
                st.warning(f"`{folder}` 下没有岗位文件，请先放入 .txt 格式的岗位描述。")

        k = st.slider("详细评分前几个候选岗位（k）", min_value=1, max_value=10, value=3, key="rec_k")
        st.caption("先按语义相似度检索出 k 个候选岗位，再逐个评分，最后按总分排序。"
                   "检索挑不进来的岗位不会被评分，所以岗位库较大时，k 要取得比想看的名次多得多。")

    if st.button("开始推荐", type="primary", key="run_recommend", disabled=(n_jobs == 0)):
        st.session_state.pop("recommend_results", None)
        with guarded():
            resume_text = resolve_input("简历", *upload_parts(rec_resume_file), rec_resume_pasted)
            with st.spinner("正在检索并评分，每个岗位约需十几秒……"):
                s = get_services()
                library, stats = get_library(source)
                st.session_state["recommend_stats"] = stats
                st.session_state["recommend_results"] = recommend(
                    resume_text, library, k, s.resume_chain, s.job_chain, s.match_chain, s.cache, s.schools,
                    track=None if track == ALL_TRACKS else track)

    recs = st.session_state.get("recommend_results")
    if recs is not None:
        st.divider()
        stats = st.session_state.get("recommend_stats")
        if stats:
            st.caption(f"岗位库已同步：新增 {stats['added']}，移除 {stats['removed']}，沿用 {stats['kept']}")
        if not recs:
            st.info("岗位库里没有检索到岗位。")
        else:
            st.markdown("**推荐排名**")
            st.dataframe(ranking_rows(recs), hide_index=True)
            for i, rec in enumerate(recs, 1):
                with st.expander(f"{i}. {rec.result.job.title}　{rec.result.score} 分", expanded=(i == 1)):
                    render_result(rec.result)
