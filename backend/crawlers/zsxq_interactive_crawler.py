from __future__ import annotations

from backend.core.app_config import load_config
from backend.crawlers.topic_crawler import ZSXQTopicCrawler


ZSXQInteractiveCrawler = ZSXQTopicCrawler

__all__ = ["ZSXQInteractiveCrawler", "ZSXQTopicCrawler", "load_config"]
