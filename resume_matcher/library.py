"""岗位库：建立向量索引、按简历检索最相似的岗位

每个岗位的 ID 是内容哈希：同步时只给新增的岗位计算 embedding，
改过的岗位等于“删旧加新”，没变的跳过，文件被删除的从库里移除。
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document


@dataclass
class JobHit:
    source: str      # 岗位文件名
    text: str        # 岗位描述原文
    distance: float  # 检索距离，越小越相似


def _doc_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class JobLibrary:
    def __init__(self, embedding, persist_dir, collection_name: str = "jobs"):
        self._db = Chroma(
            collection_name=collection_name,
            embedding_function=embedding,
            persist_directory=str(persist_dir),
        )

    def count(self) -> int:
        return len(self._db.get()["ids"])

    def sync(self, jobs_dir) -> dict:
        """让索引与 jobs_dir 里的 .txt 文件保持一致，返回 {added, removed, kept}"""
        wanted: dict[str, Document] = {}
        for path in sorted(Path(jobs_dir).glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            wanted[_doc_id(text)] = Document(page_content=text, metadata={"source": path.name})

        existing = set(self._db.get()["ids"])
        stale = sorted(existing - wanted.keys())
        new_ids = [i for i in wanted if i not in existing]

        if stale:
            self._db.delete(ids=stale)
        if new_ids:
            self._db.add_documents([wanted[i] for i in new_ids], ids=new_ids)
        return {"added": len(new_ids), "removed": len(stale), "kept": len(wanted) - len(new_ids)}

    def search(self, query: str, k: int = 3) -> list[JobHit]:
        if self.count() == 0:
            return []
        return [
            JobHit(source=doc.metadata["source"], text=doc.page_content, distance=float(score))
            for doc, score in self._db.similarity_search_with_score(query, k=k)
        ]
