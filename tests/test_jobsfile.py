import json

import pytest

from resume_matcher.jobsfile import append_new, read_rows


def row(job_id, text="岗位正文", **extra):
    return {"job_id": job_id, "text": text, "title": f"岗位{job_id}", **extra}


def test_append_new_writes_one_json_line_per_job(tmp_path):
    path = tmp_path / "jobs.jsonl"
    assert append_new([row("1"), row("2")], path) == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["job_id"] for line in lines] == ["1", "2"]


def test_append_new_keeps_chinese_readable(tmp_path):
    path = tmp_path / "jobs.jsonl"
    append_new([row("1", text="岗位职责：数据分析")], path)
    assert "岗位职责：数据分析" in path.read_text(encoding="utf-8")


def test_append_new_creates_missing_folders(tmp_path):
    path = tmp_path / "a" / "b" / "jobs.jsonl"
    assert append_new([row("1")], path) == 1
    assert path.exists()


def test_append_new_skips_jobs_that_are_already_in_the_file(tmp_path):
    path = tmp_path / "jobs.jsonl"
    append_new([row("1"), row("2")], path)
    assert append_new([row("2"), row("3")], path) == 1
    assert [r["job_id"] for r in read_rows(path)] == ["1", "2", "3"]


def test_append_new_skips_duplicates_inside_one_batch(tmp_path):
    path = tmp_path / "jobs.jsonl"
    assert append_new([row("1"), row("1")], path) == 1


def test_append_new_never_overwrites_an_existing_job(tmp_path):
    path = tmp_path / "jobs.jsonl"
    append_new([row("1", text="旧内容")], path)
    append_new([row("1", text="新内容")], path)
    assert read_rows(path)[0]["text"] == "旧内容"


def test_append_new_with_nothing_new_does_not_create_the_file(tmp_path):
    path = tmp_path / "jobs.jsonl"
    assert append_new([], path) == 0
    assert not path.exists()


@pytest.mark.parametrize("bad_id", ["", "   ", None, 123])
def test_append_new_rejects_a_missing_or_non_string_job_id(tmp_path, bad_id):
    with pytest.raises(ValueError):
        append_new([row(bad_id)], tmp_path / "jobs.jsonl")


def test_a_rejected_batch_writes_nothing(tmp_path):
    path = tmp_path / "jobs.jsonl"
    with pytest.raises(ValueError):
        append_new([row("1"), row("")], path)
    assert not path.exists()


def test_read_rows_of_a_missing_file_is_empty(tmp_path):
    assert read_rows(tmp_path / "nope.jsonl") == []


def test_read_rows_skips_blank_and_corrupt_lines(tmp_path):
    path = tmp_path / "jobs.jsonl"
    good = json.dumps(row("1"), ensure_ascii=False)
    path.write_text(f"{good}\n\n这不是 JSON\n{{\"job_id\": \"2\"}}\n", encoding="utf-8")
    # 第 4 行缺少 text，不能用于检索，也跳过
    assert [r["job_id"] for r in read_rows(path)] == ["1"]
