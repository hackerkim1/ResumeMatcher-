"""从教育部公布的页面生成院校名单 data/schools.json

运行方式：
  python -m resume_matcher.schools_builder           # 只预览，不写文件
  python -m resume_matcher.schools_builder --write   # 确认无误后写入

只抓取两个公开页面，请求之间留出间隔。抓到空结果时不会覆盖现有名单。
"""
import argparse
import datetime
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from resume_matcher.config import SCHOOLS_FILE

URL_985 = "http://www.moe.gov.cn/srcsite/A22/s7065/200612/t20061206_128833.html"
URL_211 = "http://www.moe.gov.cn/srcsite/A22/s7065/200512/t20051223_82762.html"
USER_AGENT = "ResumeMatcher-student-project (reads two public MOE pages, low request rate)"
OFFICIAL_COUNTS = {"985": 39, "211": 112}  # 教育部公布的数量，211 含 985

_NAME = re.compile(r"[一-龥（）·]+")


class _CellCollector(HTMLParser):
    """收集所有 <td> 单元格里的文字"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._current = []

    def handle_endtag(self, tag):
        if tag == "td" and self._current is not None:
            self.cells.append("".join(self._current))
            self._current = None

    def handle_data(self, data):
        if self._current is not None:
            self._current.append(data)


def extract_school_names(html: str) -> list[str]:
    """从页面的表格单元格里取出校名：去空白，括号统一为全角，只留纯中文且含“大学/学院”的，去重保序"""
    collector = _CellCollector()
    collector.feed(html)

    names: list[str] = []
    for cell in collector.cells:
        text = re.sub(r"\s+", "", cell).replace("(", "（").replace(")", "）")
        if _NAME.fullmatch(text) and re.search("大学|学院", text) and text not in names:
            names.append(text)
    return names


def build_schools(names_985: list[str], names_211: list[str]):
    """合并成名单，并检查是否自洽。返回 (名单, 警告列表)

    约定：211 里不重复写 985 的学校。
    """
    in_985, in_211 = set(names_985), set(names_211)
    data = {"985": list(names_985), "211": [s for s in names_211 if s not in in_985]}

    warnings = [f"985 名单里的 {s} 不在 211 名单中，请核对" for s in names_985 if s not in in_211]
    if len(names_985) != OFFICIAL_COUNTS["985"]:
        warnings.append(f"985 名单数量是 {len(names_985)}，教育部公布的是 {OFFICIAL_COUNTS['985']} 所")
    if len(names_211) != OFFICIAL_COUNTS["211"]:
        warnings.append(f"211 名单数量是 {len(names_211)}，教育部公布的是 {OFFICIAL_COUNTS['211']} 所")
    return data, warnings


def fetch_page(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _all_names(data: dict) -> set[str]:
    return set(data.get("985", [])) | set(data.get("211", []))


def main(argv=None, fetch=fetch_page, url_985=URL_985, url_211=URL_211, delay: float = 3.0) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="从教育部页面生成院校名单")
    parser.add_argument("--output", default=str(SCHOOLS_FILE), help="名单文件路径")
    parser.add_argument("--write", action="store_true", help="写入文件；不加则只预览")
    args = parser.parse_args(argv)

    try:
        html_985 = fetch(url_985)
        time.sleep(delay)
        html_211 = fetch(url_211)
    except Exception as e:
        print(f"抓取失败：{type(e).__name__}", file=sys.stderr)
        return 1

    names_985, names_211 = extract_school_names(html_985), extract_school_names(html_211)
    if not names_985 or not names_211:
        print(f"没有从页面里解析到校名（985：{len(names_985)}，211：{len(names_211)}），"
              "可能是页面改版或网络异常，没有修改任何文件", file=sys.stderr)
        return 1

    data, warnings = build_schools(names_985, names_211)
    output = Path(args.output)
    old = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    added = sorted(_all_names(data) - _all_names(old))
    removed = sorted(_all_names(old) - _all_names(data))

    print(f"985：{len(data['985'])} 所；211（不含 985）：{len(data['211'])} 所")
    print(f"相比现有文件：新增 {len(added)} 所，移除 {len(removed)} 所")
    if added:
        print("新增：" + "、".join(added))
    if removed:
        print("移除：" + "、".join(removed))
    for w in warnings:
        print(f"警告：{w}")

    if not args.write:
        print("\n未写入文件。确认无误后加 --write 再运行一次。")
        return 0

    result = {
        "说明": "由 resume_matcher.schools_builder 根据教育部公布的页面生成；211 里不重复写 985 的学校。",
        "来源": {"985": url_985, "211": url_211, "抓取日期": datetime.date.today().isoformat()},
        **data,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写入 {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
