from __future__ import annotations

from typing import Callable, NamedTuple, Optional


class DownloadUrlResponseDecision(NamedTuple):
    download_url: Optional[str]
    should_retry: bool
    should_stop: bool


class DownloadUrlAttemptTarget(NamedTuple):
    url: str
    file_id: int
    attempt: int
    max_retries: int


class DownloadUrlRetryLoopTarget(NamedTuple):
    url: str
    file_id: int
    max_retries: int


class DownloadUrlRetryLoopStepDecision(NamedTuple):
    result: Optional[str]
    should_continue: bool


RunDownloadUrlAttempt = Callable[[DownloadUrlAttemptTarget], DownloadUrlResponseDecision]
FinishDownloadUrlRetryExhausted = Callable[[DownloadUrlRetryLoopTarget], None]


def download_url_retry_loop_step_decision(
    decision: DownloadUrlResponseDecision,
) -> DownloadUrlRetryLoopStepDecision:
    if decision.download_url:
        return DownloadUrlRetryLoopStepDecision(decision.download_url, False)
    if decision.should_retry:
        return DownloadUrlRetryLoopStepDecision(None, True)
    if decision.should_stop:
        return DownloadUrlRetryLoopStepDecision(None, False)
    return DownloadUrlRetryLoopStepDecision(None, True)


def run_download_url_retry_loop(
    target: DownloadUrlRetryLoopTarget,
    *,
    run_attempt: RunDownloadUrlAttempt,
    finish_exhausted: FinishDownloadUrlRetryExhausted,
) -> Optional[str]:
    for attempt in range(target.max_retries):
        decision = run_attempt(
            DownloadUrlAttemptTarget(target.url, target.file_id, attempt, target.max_retries),
        )
        step_decision = download_url_retry_loop_step_decision(decision)
        if step_decision.should_continue:
            continue
        return step_decision.result

    finish_exhausted(target)
    return None
