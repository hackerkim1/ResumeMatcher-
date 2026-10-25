"""单个 jobs.jsonl 文件：一行一个岗位，含完整正文和元数据

爬虫往里追加，岗位库从里面读取。按 job_id 去重，已有的岗位不会被覆盖。
"""
import json
from pathlib import Path


def _valid_id(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def read_rows(path) -> list[dict]:
    """读出所有可用的岗位；文件不存在返回空；空行、损坏的行、缺少 job_id 或正文的行都跳过"""
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and _valid_id(row.get("job_id")) and _valid_id(row.get("text")):
            rows.append(row)
    return rows


def tracks_in(rows) -> list[str]:
    """这些岗位里有哪些专业方向（只读文件，不需要向量化）"""
    return sorted({r["track"] for r in rows if isinstance(r.get("track"), str) and r["track"].strip()})


def append_new(rows, path) -> int:
    """把文件里还没有的岗位追加进去，返回新增数量；有一条的 job_id 不合法就整批拒绝，什么都不写"""
    rows = list(rows)
    if any(not _valid_id(r.get("job_id")) for r in rows):
        raise ValueError("每个岗位都必须有非空的字符串 job_id")

    known = {r["job_id"] for r in read_rows(path)}
    new = []
    for row in rows:
        if row["job_id"] not in known:
            known.add(row["job_id"])
            new.append(row)
    if not new:
        return 0

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = p.exists() and p.stat().st_size > 0 and not p.read_bytes().endswith(b"\n")
    with open(p, "a", encoding="utf-8") as f:
        if needs_newline:  # 上次写到一半被中断时，别让新的一行粘在残缺的行后面
            f.write("\n")
        for row in new:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(new)
