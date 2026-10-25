import json

from resume_matcher.cli import build_parser, main


def test_recommend_accepts_a_jobs_file_and_a_track():
    args = build_parser().parse_args(
        ["recommend", "--resume", "r.txt", "--jobs-file", "jobs.jsonl", "--track", "数据"])
    assert args.jobs_file == "jobs.jsonl"
    assert args.track == "数据"


def test_jobs_file_and_track_default_to_none():
    args = build_parser().parse_args(["recommend", "--resume", "r.txt"])
    assert args.jobs_file is None and args.track is None


def write_resume(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("简历", encoding="utf-8")
    return str(f)


def test_a_missing_jobs_file_is_reported_without_touching_the_model(tmp_path, capsys):
    code = main(["recommend", "--resume", write_resume(tmp_path), "--jobs-file", str(tmp_path / "nope.jsonl")])
    assert code == 1
    assert "没有找到抓取的岗位" in capsys.readouterr().err


def test_an_empty_jobs_file_is_reported_the_same_way(tmp_path, capsys):
    empty = tmp_path / "jobs.jsonl"
    empty.write_text("", encoding="utf-8")
    code = main(["recommend", "--resume", write_resume(tmp_path), "--jobs-file", str(empty)])
    assert code == 1
    assert "没有找到抓取的岗位" in capsys.readouterr().err


def test_a_track_without_a_jobs_file_is_rejected(tmp_path, capsys):
    code = main(["recommend", "--resume", write_resume(tmp_path), "--track", "数据"])
    assert code == 1
    assert "--jobs-file" in capsys.readouterr().err


def test_an_unknown_track_lists_the_tracks_that_exist(tmp_path, capsys):
    rows = tmp_path / "jobs.jsonl"
    rows.write_text(json.dumps({"job_id": "1", "text": "岗位正文", "track": "数据"}, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    code = main(["recommend", "--resume", write_resume(tmp_path), "--jobs-file", str(rows), "--track", "不存在"])
    assert code == 1
    assert "数据" in capsys.readouterr().err
