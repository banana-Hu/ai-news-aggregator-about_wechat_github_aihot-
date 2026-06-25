"""
连接器基类。
所有外部数据源连接器继承此类，确保统一接口。
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """数据源连接器基类。"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._setup_logger()

    def _setup_logger(self):
        """配置日志。"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def fetch(self, **kwargs) -> list:
        """抓取数据，返回 NormalizedItem 列表。

        Returns:
            list[NormalizedItem]: 标准化数据条目列表。
        """
        pass

    def safe_fetch(self, **kwargs) -> list:
        """安全抓取封装：捕获异常，不影响主流程。"""
        try:
            result = self.fetch(**kwargs)
            self.logger.info(f"抓取成功: {len(result)} 条")
            return result
        except Exception as e:
            self.logger.error(f"抓取失败 [{self.__class__.__name__}]: {e}", exc_info=True)
            return []

    @staticmethod
    def rate_limit_sleep(seconds: float = 1.0):
        """速率限制等待。"""
        time.sleep(seconds)
