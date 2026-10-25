from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from resume_matcher.library import JobLibrary


class CountingEmbedding(Embeddings):
    """记录被计算过 embedding 的文本，用来证明没变的岗位不会被重复计算"""

    def __init__(self):
        self._inner = DeterministicFakeEmbedding(size=32)
        self.embedded_documents = []

    def embed_documents(self, texts):
        self.embedded_documents.extend(texts)
        return self._inner.embed_documents(texts)

    def embed_query(self, text):
        return self._inner.embed_query(text)


JOBS = {
    "a.txt": "岗位：大模型应用开发。必备：Python、LangChain、向量数据库。",
    "b.txt": "岗位：Java 后端开发。必备：Java、Spring Boot、MySQL、Redis。",
    "c.txt": "岗位：数据分析师。必备：SQL、pandas、可视化。",
}


def write_jobs(directory, jobs=JOBS):
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in jobs.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def make_library(tmp_path):
    emb = CountingEmbedding()
    return JobLibrary(emb, tmp_path / "db"), emb


def test_first_sync_adds_every_job(tmp_path):
    lib, _ = make_library(tmp_path)
    stats = lib.sync(write_jobs(tmp_path / "jobs"))
    assert stats == {"added": 3, "removed": 0, "kept": 0}
    assert lib.count() == 3


def test_second_sync_does_not_embed_unchanged_jobs_again(tmp_path):
    lib, emb = make_library(tmp_path)
    jobs_dir = write_jobs(tmp_path / "jobs")
    lib.sync(jobs_dir)
    embedded_before = len(emb.embedded_documents)

    stats = lib.sync(jobs_dir)
    assert stats == {"added": 0, "removed": 0, "kept": 3}
    assert len(emb.embedded_documents) == embedded_before


def test_changed_job_is_replaced(tmp_path):
    lib, emb = make_library(tmp_path)
    jobs_dir = write_jobs(tmp_path / "jobs")
    lib.sync(jobs_dir)

    (jobs_dir / "a.txt").write_text("岗位：大模型应用开发（更新版）。必备：Python。", encoding="utf-8")
    stats = lib.sync(jobs_dir)
    assert stats == {"added": 1, "removed": 1, "kept": 2}
    assert lib.count() == 3
    assert len(emb.embedded_documents) == 4  # 3 个初始 + 1 个改过的


def test_deleted_job_is_removed(tmp_path):
    lib, _ = make_library(tmp_path)
    jobs_dir = write_jobs(tmp_path / "jobs")
    lib.sync(jobs_dir)

    (jobs_dir / "c.txt").unlink()
    assert lib.sync(jobs_dir) == {"added": 0, "removed": 1, "kept": 2}
    assert lib.count() == 2


def test_non_txt_files_are_ignored(tmp_path):
    lib, _ = make_library(tmp_path)
    jobs_dir = write_jobs(tmp_path / "jobs")
    (jobs_dir / "notes.md").write_text("不是岗位", encoding="utf-8")
    lib.sync(jobs_dir)
    assert lib.count() == 3


def test_search_returns_the_closest_job_first(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync(write_jobs(tmp_path / "jobs"))
    hits = lib.search(JOBS["b.txt"], k=3)  # 查询文本和 b 完全相同，距离应最小
    assert hits[0].source == "b.txt"
    assert hits[0].text == JOBS["b.txt"]
    assert hits[0].distance <= hits[1].distance <= hits[2].distance


def test_search_with_k_larger_than_library_returns_all(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync(write_jobs(tmp_path / "jobs"))
    assert len(lib.search("任意查询", k=10)) == 3


def test_search_on_empty_library_returns_empty_list(tmp_path):
    lib, _ = make_library(tmp_path)
    assert lib.search("任意查询", k=3) == []
