"""JD 抽取结果的缓存：同一份 JD 只抽取一次，之后直接读文件

文件名是 JD 原文的哈希，内容里记下提示词版本；提示词变了就视为过期。
缓存是可再生的数据，读不出来（不存在、损坏、字段缺失）一律当作没有缓存。
"""
import hashlib
import json
from pathlib import Path

from resume_matcher.schemas import JobRequirement


class JobCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, text: str) -> Path:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return self.directory / f"{digest}.json"

    def get(self, text: str, prompt_version: str) -> JobRequirement | None:
        path = self._path(text)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["prompt_version"] != prompt_version:
                return None
            return JobRequirement(**payload["data"])
        except (ValueError, KeyError, TypeError):
            # JSON 不合法、缺键、字段校验失败（pydantic 的 ValidationError 也是 ValueError）
            return None

    def put(self, text: str, prompt_version: str, job: JobRequirement) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"prompt_version": prompt_version, "data": job.model_dump()}
        self._path(text).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
