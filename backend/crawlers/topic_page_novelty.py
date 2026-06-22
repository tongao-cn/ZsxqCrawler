from __future__ import annotations

from typing import Any, Callable, NamedTuple


TopicExists = Callable[[Any], bool]


class TopicPageNovelty(NamedTuple):
    existing_count: int
    new_topics: list[dict[str, Any]]

    @property
    def new_count(self) -> int:
        return len(self.new_topics)


def analyze_topic_page_novelty(
    topics: list[dict[str, Any]],
    topic_exists: TopicExists,
) -> TopicPageNovelty:
    existing_count = 0
    new_topics = []
    for topic in topics:
        topic_id = topic.get("topic_id")
        if topic_exists(topic_id):
            existing_count += 1
        else:
            new_topics.append(topic)
    return TopicPageNovelty(existing_count, new_topics)
