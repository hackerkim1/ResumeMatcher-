from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from resume_matcher.library import JobLibrary


class CountingEmbedding(Embeddings):
    def __init__(self):
        self._inner = DeterministicFakeEmbedding(size=32)
        self.embedded_documents = []

    def embed_documents(self, texts):
        self.embedded_documents.extend(texts)
        return self._inner.embed_documents(texts)

    def embed_query(self, text):
        return self._inner.embed_query(text)


def make_row(job_id, track, text=None):
    return {
        "job_id": job_id, "title": f"岗位{job_id}", "company": "示例企业", "category": "类别",
        "track": track, "source": "iguopin", "text": text or f"岗位{job_id}：{track}方向，需要相关技能",
    }


ROWS = [
    make_row("1", "计算机/软件"),
    make_row("2", "计算机/软件"),
    make_row("3", "数据"),
    make_row("4", "财会/金融"),
]


def make_library(tmp_path, collection="jobs_crawled"):
    emb = CountingEmbedding()
    return JobLibrary(emb, tmp_path / "db", collection_name=collection), emb


def test_sync_rows_adds_every_row(tmp_path):
    lib, _ = make_library(tmp_path)
    assert lib.sync_rows(ROWS) == {"added": 4, "removed": 0, "kept": 0}
    assert lib.count() == 4


def test_sync_rows_again_does_not_embed_unchanged_rows(tmp_path):
    lib, emb = make_library(tmp_path)
    lib.sync_rows(ROWS)
    before = len(emb.embedded_documents)
    assert lib.sync_rows(ROWS) == {"added": 0, "removed": 0, "kept": 4}
    assert len(emb.embedded_documents) == before


def test_sync_rows_replaces_a_changed_row_and_removes_a_missing_one(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows(ROWS)
    changed = [make_row("1", "计算机/软件", text="岗位1：内容已经改了")] + ROWS[1:3]  # 去掉了第 4 个
    assert lib.sync_rows(changed) == {"added": 1, "removed": 2, "kept": 2}
    assert lib.count() == 3


def test_a_hit_carries_source_track_and_the_full_text(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows(ROWS)
    hit = lib.search(ROWS[2]["text"], k=1)[0]
    assert hit.source == "iguopin:3"
    assert hit.track == "数据"
    assert hit.text == ROWS[2]["text"]


def test_search_without_a_track_looks_through_every_row(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows(ROWS)
    assert len(lib.search("任意查询", k=10)) == 4


def test_search_with_a_track_only_returns_rows_of_that_track(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows(ROWS)
    hits = lib.search("任意查询", k=10, track="计算机/软件")
    assert sorted(h.source for h in hits) == ["iguopin:1", "iguopin:2"]
    assert {h.track for h in hits} == {"计算机/软件"}


def test_search_with_a_track_that_has_no_rows_returns_nothing(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows(ROWS)
    assert lib.search("任意查询", k=5, track="医药/法学/语言") == []


def test_tracks_lists_the_distinct_tracks_in_the_library(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows(ROWS)
    assert lib.tracks() == sorted({"计算机/软件", "数据", "财会/金融"})


def test_tracks_ignores_rows_without_a_track(tmp_path):
    lib, _ = make_library(tmp_path)
    lib.sync_rows([make_row("1", ""), make_row("2", "数据")])
    assert lib.tracks() == ["数据"]


def test_two_collections_in_one_folder_do_not_overwrite_each_other(tmp_path):
    crawled, _ = make_library(tmp_path, collection="jobs_crawled")
    samples, _ = make_library(tmp_path, collection="jobs")
    crawled.sync_rows(ROWS)
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "a.txt").write_text("样例岗位：需要 Python。", encoding="utf-8")
    samples.sync(jobs_dir)

    assert crawled.count() == 4 and samples.count() == 1
    samples.sync(jobs_dir)  # 再同步样例岗位，不能把抓取的岗位删掉
    assert crawled.count() == 4
