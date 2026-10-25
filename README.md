# ResumeMatcher：简历 × 岗位匹配分析器

输入一份简历和一个（或一批）岗位描述，输出匹配分数、技能缺口、简历修改建议和可能被问到的面试题。

## 设计思路

- 模型负责理解：把简历、JD 抽取成结构化数据，并逐项判断技能是否满足（附依据）
- 代码负责计算：总分、学历和学校检查都由纯代码完成，结果确定、可测试
- 岗位库用向量检索粗筛，再对少量候选岗位做详细分析

## 目录结构

| 路径 | 职责 |
|---|---|
| `resume_matcher/config.py` | 读取环境变量，集中管理配置 |
| `resume_matcher/schemas.py` | 数据结构（Pydantic） |
| `resume_matcher/llm.py` | 创建模型与 embedding |
| `resume_matcher/extractors.py` | 抽取链与对比链 |
| `resume_matcher/scoring.py` | 评分、学历/学校检查（不调用模型） |
| `resume_matcher/library.py` | 岗位库索引与检索 |
| `resume_matcher/cli.py` | 命令行入口 |
| `data/` | 岗位库、样例简历、院校名单 |
| `tests/` | 测试 |

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # 然后在 .env 中填入 SILICONFLOW_API_KEY
```

## 开发进度

- [x] 第 1 步：项目骨架
- [x] 第 2 步：数据结构与评分（纯代码，先写测试）
- [ ] 第 3 步：模型接入与抽取链
- [ ] 第 4 步：命令行 `match`
- [ ] 第 5 步：岗位库与 `recommend`
