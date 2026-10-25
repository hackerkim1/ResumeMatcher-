import pymupdf
import pytest

from resume_matcher.documents import DocumentError, read_document, read_document_bytes, resolve_input


def make_pdf_bytes(text):
    doc = pymupdf.open()
    if text:
        doc.new_page().insert_text((72, 72), text)
    else:
        doc.new_page()  # 一页空白，模拟扫描件里没有文字层
    data = doc.tobytes()
    doc.close()
    return data


# ---------- read_document_bytes ----------

def test_reads_utf8_text():
    assert read_document_bytes("r.txt", "你好，简历".encode("utf-8")) == "你好，简历"


def test_reads_utf8_text_with_bom():
    assert read_document_bytes("r.txt", "你好".encode("utf-8-sig")) == "你好"


def test_reads_gbk_text():
    # Windows 记事本默认保存的就是 GBK，不能只认 UTF-8
    assert read_document_bytes("r.txt", "你好，简历".encode("gbk")) == "你好，简历"


def test_reads_pdf_text():
    assert "Hello Resume" in read_document_bytes("r.pdf", make_pdf_bytes("Hello Resume"))


def test_extension_check_ignores_case():
    assert "Hello" in read_document_bytes("R.PDF", make_pdf_bytes("Hello"))


def test_empty_text_file_raises():
    with pytest.raises(DocumentError):
        read_document_bytes("r.txt", b"   \n  ")


def test_pdf_without_text_layer_raises_with_a_hint():
    with pytest.raises(DocumentError) as e:
        read_document_bytes("scan.pdf", make_pdf_bytes(""))
    assert "扫描" in str(e.value)


def test_broken_pdf_raises_document_error():
    with pytest.raises(DocumentError):
        read_document_bytes("bad.pdf", b"not a pdf at all")


# ---------- resolve_input（网页上“上传或粘贴”二选一） ----------

def test_uploaded_file_wins_over_pasted_text():
    assert resolve_input("简历", "r.txt", "来自文件".encode("utf-8"), "来自粘贴") == "来自文件"


def test_pasted_text_is_used_when_nothing_is_uploaded():
    assert resolve_input("简历", None, None, "来自粘贴") == "来自粘贴"


def test_neither_upload_nor_paste_raises_with_the_label():
    with pytest.raises(DocumentError) as e:
        resolve_input("岗位描述", None, None, "")
    assert "岗位描述" in str(e.value)


def test_whitespace_only_paste_counts_as_nothing():
    with pytest.raises(DocumentError):
        resolve_input("简历", None, None, "  \n  ")


def test_bad_upload_raises_even_if_text_was_pasted():
    # 用户明确上传了文件，文件有问题就应该告诉他，不能悄悄改用粘贴的内容
    with pytest.raises(DocumentError):
        resolve_input("简历", "r.txt", b"  ", "来自粘贴")


# ---------- read_document (按路径) ----------

def test_read_document_by_path_reads_gbk(tmp_path):
    f = tmp_path / "r.txt"
    f.write_bytes("你好，简历".encode("gbk"))
    assert read_document(f) == "你好，简历"


def test_read_document_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_document(tmp_path / "nope.txt")
