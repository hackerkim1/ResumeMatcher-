import pymupdf
import pytest

from resume_matcher.cli import build_parser, main, read_document


def test_parser_accepts_match_command():
    args = build_parser().parse_args(["match", "--resume", "r.txt", "--job", "j.txt"])
    assert args.command == "match"
    assert args.resume == "r.txt"
    assert args.job == "j.txt"


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_requires_resume_and_job():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["match", "--resume", "r.txt"])


def test_parser_accepts_recommend_command_with_defaults():
    args = build_parser().parse_args(["recommend", "--resume", "r.txt"])
    assert args.command == "recommend"
    assert args.k == 3
    assert args.brief is False


def test_parser_accepts_recommend_options():
    args = build_parser().parse_args(["recommend", "--resume", "r.txt", "--k", "5", "--brief"])
    assert args.k == 5
    assert args.brief is True


def test_recommend_reports_an_empty_jobs_folder_without_touching_the_model(tmp_path, capsys):
    resume = tmp_path / "r.txt"
    resume.write_text("简历", encoding="utf-8")
    empty = tmp_path / "jobs"
    empty.mkdir()
    code = main(["recommend", "--resume", str(resume), "--jobs-dir", str(empty)])
    assert code == 1
    assert "没有找到岗位文件" in capsys.readouterr().err


def test_read_document_reads_txt(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("你好，简历", encoding="utf-8")
    assert read_document(f) == "你好，简历"


def test_read_document_reads_pdf(tmp_path):
    f = tmp_path / "r.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hello Resume")
    doc.save(f)
    doc.close()
    assert "Hello Resume" in read_document(f)


def test_read_document_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_document(tmp_path / "nope.txt")


def test_main_reports_missing_file_without_touching_the_model(tmp_path, capsys):
    # 文件检查必须发生在创建模型之前：这里没有配置 key 也不应该报 key 的错
    code = main(["match", "--resume", str(tmp_path / "nope.txt"), "--job", str(tmp_path / "nope2.txt")])
    assert code == 1
    assert "找不到文件" in capsys.readouterr().err
