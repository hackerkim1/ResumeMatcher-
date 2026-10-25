"""模型与 embedding 的创建：只负责造对象，不写业务逻辑"""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from resume_matcher import config


class MissingApiKeyError(RuntimeError):
    """没有配置 API key。单独成类，命令行只对这一种错误显示完整提示"""


def _require_key():
    if not config.API_KEY:
        raise MissingApiKeyError("未读取到 SILICONFLOW_API_KEY，请检查项目根目录下的 .env 文件")


def get_llm(model: str | None = None, temperature: float = 0) -> ChatOpenAI:
    """创建对话模型。抽取、判断类任务用 temperature=0 保持稳定"""
    _require_key()
    return ChatOpenAI(
        api_key=config.API_KEY,
        base_url=config.BASE_URL,
        model=model or config.CHAT_MODEL,
        temperature=temperature,
    )


def get_embedding() -> OpenAIEmbeddings:
    """创建 embedding 模型。非 OpenAI 官方接口必须关闭 ctx 长度检查"""
    _require_key()
    return OpenAIEmbeddings(
        api_key=config.API_KEY,
        base_url=config.BASE_URL,
        model=config.EMBEDDING_MODEL,
        check_embedding_ctx_length=False,
    )
