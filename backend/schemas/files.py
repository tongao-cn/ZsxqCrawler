from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FileDownloadRequest(BaseModel):
    max_files: Optional[int] = Field(default=None, description="最大下载文件数")
    sort_by: str = Field(default="download_count", description="排序方式: download_count 或 time")
    start_time: Optional[str] = Field(default=None, description="下载时间范围开始时间 YYYY-MM-DD 或 ISO 时间")
    end_time: Optional[str] = Field(default=None, description="下载时间范围结束时间 YYYY-MM-DD 或 ISO 时间")
    last_days: Optional[int] = Field(default=None, ge=1, le=3650, description="下载最近多少天的文件")
    download_interval: float = Field(default=1.0, ge=0.1, le=300.0, description="单次下载间隔（秒）")
    long_sleep_interval: float = Field(default=60.0, ge=10.0, le=3600.0, description="长休眠间隔（秒）")
    files_per_batch: int = Field(default=10, ge=1, le=100, description="下载多少文件后触发长休眠")
    download_interval_min: Optional[float] = Field(default=None, ge=1.0, le=300.0, description="随机下载间隔最小值（秒）")
    download_interval_max: Optional[float] = Field(default=None, ge=1.0, le=300.0, description="随机下载间隔最大值（秒）")
    long_sleep_interval_min: Optional[float] = Field(default=None, ge=10.0, le=3600.0, description="随机长休眠间隔最小值（秒）")
    long_sleep_interval_max: Optional[float] = Field(default=None, ge=10.0, le=3600.0, description="随机长休眠间隔最大值（秒）")


class FileCollectRequest(BaseModel):
    start_time: Optional[str] = Field(default=None, description="收集时间范围开始日期 YYYY-MM-DD")
    end_time: Optional[str] = Field(default=None, description="收集时间范围结束日期 YYYY-MM-DD")
    last_days: Optional[int] = Field(default=None, ge=1, le=3650, description="收集最近多少天的文件")


class FileAIAnalysisRequest(BaseModel):
    force: bool = Field(default=False, description="是否强制重新分析")


class FileIdListRequest(BaseModel):
    file_ids: list[int] = Field(..., min_length=1, max_length=200, description="文件 ID 列表")


class FileAIAnalysisBatchRequest(FileIdListRequest):
    force: bool = Field(default=False, description="是否强制重新分析")


class FileFilteredDownloadRequest(BaseModel):
    status: Optional[str] = Field(default=None, description="文件下载状态筛选")
    search: Optional[str] = Field(default=None, description="文件搜索关键词")
    max_files: Optional[int] = Field(default=None, ge=1, le=5000, description="最多下载多少个匹配文件")
