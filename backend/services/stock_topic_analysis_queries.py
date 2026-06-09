"""SQL builders for stock topic analysis."""

from __future__ import annotations


def build_topic_search_sql(*, recent_cutoff: str | None = None) -> str:
    cutoff_clause = "AND e.topic_date >= ?" if recent_cutoff else ""
    return """
        SELECT
            e.topic_id,
            COALESCE(t.title, '') AS title,
            COALESCE(t.create_time, e.topic_date::text) AS create_time,
            COALESCE(t.likes_count, 0) AS likes_count,
            COALESCE(t.comments_count, 0) AS comments_count,
            COALESCE(t.reading_count, 0) AS reading_count,
            e.stock_name,
            e.stock_code,
            e.market,
            e.concepts_json,
            e.excerpt,
            e.reason,
            e.confidence,
            e.topic_date::text AS topic_date
        FROM zsxq_a_share_topic_stock_extractions e
        LEFT JOIN topics t
          ON t.group_id::text = e.group_id
         AND t.topic_id::text = e.topic_id
        WHERE e.stock_name ILIKE ?
          AND e.group_id = ?
          AND COALESCE(e.excerpt, '') <> ''
          {cutoff_clause}
        ORDER BY e.topic_date DESC, e.topic_id DESC
        LIMIT ?
    """.format(cutoff_clause=cutoff_clause)


def build_question_topic_search_sql(keyword_count: int, *, recent_cutoff: str | None = None) -> str:
    cutoff_clause = "AND t.create_time >= ?" if recent_cutoff else ""
    conditions = " OR ".join(
        "(t.title ILIKE ? OR tk.text ILIKE ? OR q.text ILIKE ? OR a.text ILIKE ?)"
        for _ in range(keyword_count)
    )
    return f"""
        SELECT
            t.topic_id,
            t.title,
            t.create_time,
            t.likes_count,
            t.comments_count,
            t.reading_count,
            tk.text AS talk_text,
            q.text AS question_text,
            a.text AS answer_text
        FROM topics t
        LEFT JOIN talks tk ON t.topic_id = tk.topic_id
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        WHERE t.group_id::text = ?
          AND ({conditions})
          {cutoff_clause}
        ORDER BY t.create_time DESC
        LIMIT ?
    """.format(conditions=conditions, cutoff_clause=cutoff_clause)
