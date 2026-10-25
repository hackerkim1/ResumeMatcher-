from langchain_core.embeddings import DeterministicFakeEmbedding

from resume_matcher import services
from resume_matcher.jobsfile import append_new


def test_build_crawled_library_reads_the_file_and_uses_its_own_collection(monkeypatch, tmp_path):
    jobs_file = tmp_path / "jobs.jsonl"
    append_new([
        {"job_id": "1", "text": "岗位一：需要 Python", "track": "数据"},
        {"job_id": "2", "text": "岗位二：需要 Java", "track": "计算机/软件"},
    ], jobs_file)
    monkeypatch.setattr(services, "get_embedding", lambda: DeterministicFakeEmbedding(size=16))
    monkeypatch.setattr(services, "VECTOR_DB_DIR", tmp_path / "db")

    library, stats = services.build_crawled_library(jobs_file)
    assert stats == {"added": 2, "removed": 0, "kept": 0}
    assert library.count() == 2
    assert library.tracks() == ["数据", "计算机/软件"]


def test_the_sample_library_and_the_crawled_library_do_not_share_documents(monkeypatch, tmp_path):
    jobs_file = tmp_path / "jobs.jsonl"
    append_new([{"job_id": "1", "text": "抓取的岗位", "track": "数据"}], jobs_file)
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "a.txt").write_text("样例岗位", encoding="utf-8")
    monkeypatch.setattr(services, "get_embedding", lambda: DeterministicFakeEmbedding(size=16))
    monkeypatch.setattr(services, "VECTOR_DB_DIR", tmp_path / "db")

    samples, _ = services.build_library(jobs_dir)
    crawled, _ = services.build_crawled_library(jobs_file)
    samples, _ = services.build_library(jobs_dir)  # 再同步一次样例岗位
    assert samples.count() == 1 and crawled.count() == 1
