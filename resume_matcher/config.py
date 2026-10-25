"""配置：整个项目唯一读取环境变量的地方，其他模块从这里导入"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
SCHOOLS_FILE = DATA_DIR / "schools.json"
VECTOR_DB_DIR = ROOT_DIR / ".job_db"

load_dotenv(ROOT_DIR / ".env")

API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# 评分权重：必备技能 / 年限 / 加分项
WEIGHTS = {"required": 70, "years": 15, "preferred": 15}
