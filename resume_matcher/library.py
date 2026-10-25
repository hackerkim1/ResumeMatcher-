"""岗位库：建立向量索引、按简历检索最相似的岗位

两种数据来源，各用一个独立的集合（同一个文件夹里互不影响）：
  - sync(jobs_dir)：读一个目录下的 .txt，每个文件一个岗位（样例岗位）
  - sync_rows(rows)：读 jobs.jsonl 里的行（抓取的岗位），元数据里带专业方向，检索时可以按方向过滤

每个岗位的 ID 是内容哈希：同步时只给新增的岗位计算 embedding，
改过的岗位等于“删旧加新”，没变的跳过，被删除的从库里移除。
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document


@dataclass
class JobHit:
    source: str          # 岗位文件名，或 “来源:岗位编号”
    text: str            # 岗位描述原文
    distance: float      # 检索距离，越小越相似
    track: str = ""      # 专业方向（样例岗位没有）


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

    def _sync(self, wanted: dict) -> dict:
        existing = set(self._db.get()["ids"])
        stale = sorted(existing - wanted.keys())
        new_ids = [i for i in wanted if i not in existing]

        if stale:
            self._db.delete(ids=stale)
        if new_ids:
            self._db.add_documents([wanted[i] for i in new_ids], ids=new_ids)
        return {"added": len(new_ids), "removed": len(stale), "kept": len(wanted) - len(new_ids)}

    def sync(self, jobs_dir) -> dict:
        """让索引与 jobs_dir 里的 .txt 文件保持一致，返回 {added, removed, kept}"""
        wanted: dict[str, Document] = {}
        for path in sorted(Path(jobs_dir).glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            wanted[_doc_id(text)] = Document(page_content=text, metadata={"source": path.name, "track": ""})
        return self._sync(wanted)

    def sync_rows(self, rows) -> dict:
        """让索引与 jobs.jsonl 的行保持一致。元数据里带专业方向，Chroma 的元数据不能是 None，缺的用空字符串"""
        wanted: dict[str, Document] = {}
        for row in rows:
            metadata = {
                "source": f"{row.get('source') or 'iguopin'}:{row['job_id']}",
                "track": row.get("track") or "",
                "title": row.get("title") or "",
                "company": row.get("company") or "",
                "category": row.get("category") or "",
            }
            wanted[_doc_id(f"{row['job_id']}\n{row['text']}")] = Document(page_content=row["text"], metadata=metadata)
        return self._sync(wanted)

    def tracks(self) -> list[str]:
        """库里有哪些专业方向"""
        metadatas = self._db.get()["metadatas"] or []
        return sorted({m["track"] for m in metadatas if m and m.get("track")})

    def search(self, query: str, k: int = 3, track=None) -> list[JobHit]:
        """检索最相似的 k 个岗位；给了 track 就只在这个专业方向里检索（元数据过滤）"""
        if self.count() == 0:
            return []
        where = {"track": track} if track else None
        return [
            JobHit(source=doc.metadata["source"], text=doc.page_content, distance=float(score),
                   track=doc.metadata.get("track") or "")
            for doc, score in self._db.similarity_search_with_score(query, k=k, filter=where)
        ]
