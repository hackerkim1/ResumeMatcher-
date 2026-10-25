"""专业方向与搜索关键词的对照表

这是我们自己定的分类，用来决定“抓哪些关键词”和“检索时按哪个方向过滤”。
国聘接口返回的“专业要求”字段不统一（有具体专业类，有“详见职位描述”），不适合直接做过滤。

关键词总数决定平均每个关键词能分到多少名额（总量上限 ÷ 关键词个数），所以不要随意加太多。
"""

TRACKS: dict[str, list[str]] = {
    "计算机/软件": ["后端开发", "前端开发", "算法工程师"],
    "数据": ["数据分析", "数据开发", "大数据"],
    "电子/通信/电气": ["嵌入式", "电气工程师", "通信工程师"],
    "机械/自动化": ["机械设计", "自动化", "机电工程师"],
    "土木/建筑": ["土建工程师", "造价工程师", "施工员"],
    "财会/金融": ["会计", "审计", "金融"],
    "经管/综合": ["人力资源", "市场营销", "综合管理"],
    "化工/材料/能源": ["化工工程师", "材料", "电力"],
    "医药/法学/语言": ["药品", "法务", "翻译"],
}


def all_keywords(tracks: dict | None = None) -> list[str]:
    tracks = TRACKS if tracks is None else tracks
    return [keyword for keywords in tracks.values() for keyword in keywords]


def track_of(keyword, tracks: dict | None = None):
    tracks = TRACKS if tracks is None else tracks
    for track, keywords in tracks.items():
        if keyword in keywords:
            return track
    return None


def keywords_for(track: str, tracks: dict | None = None) -> list[str]:
    tracks = TRACKS if tracks is None else tracks
    if track not in tracks:
        raise ValueError(f"没有“{track}”这个方向，可选：{'、'.join(tracks)}")
    return tracks[track]
