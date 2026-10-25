"""读取简历、岗位描述：支持 txt 和 pdf，可以按路径读，也可以直接读上传的字节

命令行和网页共用这一份，保证两边对同一个文件的处理一致。
"""
from pathlib import Path

import pymupdf


class DocumentError(Exception):
    """文件本身的问题（空文件、扫描件、损坏、编码无法识别），说明文字可直接显示给用户"""


def _decode(data: bytes) -> str:
    # Windows 记事本默认保存为 GBK，所以不能只认 UTF-8
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentError("无法识别文本编码，请另存为 UTF-8 后重试")


def _read_pdf(data: bytes) -> str:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
    except Exception as e:
        raise DocumentError("无法读取这个 PDF 文件，文件可能已损坏") from e
    if not text.strip():
        raise DocumentError("PDF 里没有提取到文字，可能是扫描件（图片），请换成含文字的版本或转成 txt")
    return text


def read_document_bytes(filename: str, data: bytes) -> str:
    if Path(filename).suffix.lower() == ".pdf":
        return _read_pdf(data)
    text = _decode(data)
    if not text.strip():
        raise DocumentError("文件内容为空")
    return text


def resolve_input(label: str, filename: str | None, data: bytes | None, pasted: str) -> str:
    """网页上“上传文件”和“粘贴文字”二选一：上传优先；上传的文件有问题就报错，不悄悄改用粘贴的内容"""
    if data is not None:
        return read_document_bytes(filename or "", data)
    if pasted.strip():
        return pasted
    raise DocumentError(f"请上传{label}文件或粘贴{label}文字")


def read_document(path) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return read_document_bytes(p.name, p.read_bytes())
