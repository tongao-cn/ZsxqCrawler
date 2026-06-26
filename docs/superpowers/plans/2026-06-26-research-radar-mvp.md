# Research Radar MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0 Research Radar MVP: a group-scoped, evidence-backed pre-market radar generated from already-ingested content and displayed in a new group workbench tab.

**Architecture:** Add a separate Research Radar workflow with deterministic signal candidates, evidence binding, optional evidence-constrained AI wording, PostgreSQL persistence, task-runtime generation, read routes, and a frontend tab. The MVP reads existing topic material and stock extraction outputs only; it does not crawl or run other workflows as a side effect.

**Tech Stack:** FastAPI, Pydantic, Python unittest, PostgreSQL via `backend.storage.db_compat`, existing task runtime, Next.js 15, React 18, TypeScript, Tailwind, shadcn-style local UI components.

---

## Scope Check

The approved spec includes P0, P1, and P2. This plan implements P0 only because it is the first independently testable product slice:

- New Research Radar tab.
- Manual generation task.
- Latest run and date-specific read APIs.
- Three to five main research logic items when enough evidence exists.
- Direction board, key stock list, evidence cards, confidence tiers, and weak-signal separation.
- No crawling during radar generation.

P1 stock drilldown and P2 post-market review will use the persisted run/evidence model created here, but they are not implemented in this plan.

## File Structure

Backend files:

- Create `backend/services/research_radar_signal.py`: pure candidate generation and evidence binding from topic material plus existing stock extraction rows.
- Create `backend/services/research_radar_ai.py`: evidence-constrained AI summarization helpers with deterministic fallback wording for tests and empty AI output.
- Create `backend/services/research_radar_store.py`: PostgreSQL persistence and read models for runs, logic items, evidence, and entities.
- Create `backend/services/research_radar_workflow.py`: task request dataclass, generation orchestration, source loading, and task-runtime wrapper.
- Create `backend/routes/research_radar_routes.py`: HTTP adapter for creating generation tasks and reading latest/date-specific radar output.
- Modify `backend/storage/postgres_core_schema.py`: add `research_radar_runs`, `research_radar_logic_items`, `research_radar_evidence`, and `research_radar_entities` tables and indexes.
- Modify `backend/services/workflow_registry.py`: register `research_radar`.
- Modify `backend/main.py`: include the new router.

Backend tests:

- Create `tests/test_research_radar_signal.py`.
- Create `tests/test_research_radar_ai.py`.
- Create `tests/test_research_radar_store.py`.
- Create `tests/test_research_radar_workflow.py`.
- Create `tests/test_research_radar_routes_helpers.py`.
- Modify `tests/test_postgres_core_schema.py`.
- Modify `tests/test_workflow_registry.py`.
- Modify `tests/test_app_factory.py`.

Frontend files:

- Modify `frontend/src/lib/api/analysisTypes.ts`: add Research Radar request and response types.
- Modify `frontend/src/lib/api/analysis.ts`: add create/read Research Radar API client methods.
- Create `frontend/src/components/ResearchRadarPanel.tsx`: panel UI, generation controls, logic cards, direction board, key stocks, and evidence feed.
- Modify `frontend/src/components/GroupWorkbenchTabList.tsx`: add the new tab trigger.
- Modify `frontend/src/app/groups/[groupId]/page.tsx`: dynamic import and render the new panel.

Frontend verification:

- Use `npm --prefix frontend run build`.

## Task 1: Schema And Workflow Registration

**Files:**
- Modify: `backend/storage/postgres_core_schema.py`
- Modify: `backend/services/workflow_registry.py`
- Modify: `tests/test_postgres_core_schema.py`
- Modify: `tests/test_workflow_registry.py`

- [ ] **Step 1: Write failing schema assertions**

Add these assertions to `PostgresCoreSchemaTests.test_core_schema_sql_contains_schema_tables_and_indexes` in `tests/test_postgres_core_schema.py`:

```python
self.assertIn(f'CREATE TABLE IF NOT EXISTS "{CORE_SCHEMA}"."research_radar_runs"', sql)
self.assertIn(f'CREATE TABLE IF NOT EXISTS "{CORE_SCHEMA}"."research_radar_logic_items"', sql)
self.assertIn(f'CREATE TABLE IF NOT EXISTS "{CORE_SCHEMA}"."research_radar_evidence"', sql)
self.assertIn(f'CREATE TABLE IF NOT EXISTS "{CORE_SCHEMA}"."research_radar_entities"', sql)
self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS "research_radar_runs_group_id_report_date_key"', sql)
self.assertIn('CREATE INDEX IF NOT EXISTS "idx_research_radar_runs_group_id_report_date"', sql)
self.assertIn('CREATE INDEX IF NOT EXISTS "idx_research_radar_logic_items_run_id_rank"', sql)
self.assertIn('CREATE INDEX IF NOT EXISTS "idx_research_radar_evidence_logic_id"', sql)
self.assertIn('CREATE INDEX IF NOT EXISTS "idx_research_radar_entities_run_id_entity_type_name"', sql)
```

Add this assertion to `PostgresCoreSchemaTests.test_no_indexes_keeps_unique_constraints_but_skips_performance_indexes`:

```python
self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS "research_radar_runs_group_id_report_date_key"', sql)
```

- [ ] **Step 2: Write failing workflow registry assertion**

Add this test to `tests/test_workflow_registry.py`:

```python
def test_research_radar_workflow_is_registered_as_group_runtime_task(self):
    from backend.services.workflow_registry import get_workflow_spec

    spec = get_workflow_spec("research_radar")

    self.assertIsNotNone(spec)
    self.assertEqual("研究雷达", spec.display_name)
    self.assertEqual("group", spec.scope)
    self.assertIsNone(spec.lock_category)
    self.assertTrue(spec.cancellable)
```

- [ ] **Step 3: Run the failing tests**

Run:

```powershell
uv run python -m unittest tests.test_postgres_core_schema tests.test_workflow_registry -v
```

Expected: failures mention missing `research_radar_*` schema strings and missing `research_radar` workflow registration.

- [ ] **Step 4: Add schema specs**

In `backend/storage/postgres_core_schema.py`, add these `CoreTableSpec` entries after `daily_stock_concepts`:

```python
CoreTableSpec("research_radar_runs", ("id BIGINT GENERATED BY DEFAULT AS IDENTITY", "group_id TEXT", "report_date TEXT", "window_days BIGINT DEFAULT 1", "status TEXT DEFAULT 'completed'", "model TEXT", "summary_json TEXT", "task_id TEXT", "error TEXT", "created_at TEXT", "updated_at TEXT"), ("id",), (("group_id", "report_date"),)),
CoreTableSpec("research_radar_logic_items", ("id BIGINT GENERATED BY DEFAULT AS IDENTITY", "run_id BIGINT", "rank BIGINT", "tier TEXT", "title TEXT", "summary TEXT", "direction TEXT", "concepts_json TEXT", "stocks_json TEXT", "catalysts_json TEXT", "risks_json TEXT", "evidence_count BIGINT DEFAULT 0", "confidence DOUBLE PRECISION DEFAULT 0", "created_at TEXT"), ("id",)),
CoreTableSpec("research_radar_evidence", ("id BIGINT GENERATED BY DEFAULT AS IDENTITY", "logic_id BIGINT", "source_type TEXT", "source_id TEXT", "topic_id TEXT", "source_time TEXT", "excerpt TEXT", "matched_entities_json TEXT", "support_reason TEXT", "navigation_json TEXT", "created_at TEXT"), ("id",)),
CoreTableSpec("research_radar_entities", ("id BIGINT GENERATED BY DEFAULT AS IDENTITY", "run_id BIGINT", "logic_id BIGINT", "entity_type TEXT", "name TEXT", "code TEXT", "market TEXT", "weight DOUBLE PRECISION DEFAULT 0", "evidence_count BIGINT DEFAULT 0", "created_at TEXT"), ("id",)),
```

Add these index specs to `CORE_INDEX_SPECS` near the analysis indexes:

```python
("research_radar_runs", ("group_id", "report_date")),
("research_radar_logic_items", ("run_id", "rank")),
("research_radar_evidence", ("logic_id",)),
("research_radar_entities", ("run_id", "entity_type", "name")),
```

- [ ] **Step 5: Register workflow**

In `backend/services/workflow_registry.py`, add the spec near other analysis tasks:

```python
_spec("research_radar", "研究雷达"),
```

If there are existing staged retention changes in this file, keep them and insert the new spec without moving unrelated entries.

- [ ] **Step 6: Run tests and commit**

Run:

```powershell
uv run python -m unittest tests.test_postgres_core_schema tests.test_workflow_registry -v
```

Expected: PASS.

Commit only the files from this task:

```powershell
git add -- backend/storage/postgres_core_schema.py backend/services/workflow_registry.py tests/test_postgres_core_schema.py tests/test_workflow_registry.py
git commit -m "Add research radar schema contract"
```

If unrelated staged files exist, use:

```powershell
git commit --only backend/storage/postgres_core_schema.py backend/services/workflow_registry.py tests/test_postgres_core_schema.py tests/test_workflow_registry.py -m "Add research radar schema contract"
```

## Task 2: Deterministic Signal Candidates And Evidence Binding

**Files:**
- Create: `backend/services/research_radar_signal.py`
- Create: `tests/test_research_radar_signal.py`

- [ ] **Step 1: Write failing signal tests**

Create `tests/test_research_radar_signal.py`:

```python
import unittest


class ResearchRadarSignalTests(unittest.TestCase):
    def test_build_candidates_groups_by_concept_and_binds_topic_evidence(self):
        from backend.services.research_radar_signal import build_research_radar_candidates

        topics = [
            {
                "topic_id": "101",
                "title": "PCB涨价继续发酵",
                "create_time": "2026-06-26T08:30:00.000+0800",
                "talk_text": "AI服务器需求拉动PCB和铜箔涨价，沪电股份被多次提到。",
                "comments": [{"text": "胜宏科技也受益于高端PCB订单。"}],
            },
            {
                "topic_id": "102",
                "title": "机器人订单",
                "create_time": "2026-06-26T09:10:00.000+0800",
                "talk_text": "机器人方向有新订单催化。",
                "comments": [],
            },
        ]
        current_rows = [
            {
                "topic_id": "101",
                "stock_name": "沪电股份",
                "stock_code": "002463",
                "market": "SZ",
                "concepts": ["PCB", "涨价/供需"],
                "reason": "PCB涨价和AI服务器需求。",
                "confidence": 0.8,
            },
            {
                "topic_id": "101",
                "stock_name": "胜宏科技",
                "stock_code": "300476",
                "market": "SZ",
                "concepts": ["PCB"],
                "reason": "高端PCB订单。",
                "confidence": 0.75,
            },
        ]
        baseline_rows = [
            {
                "topic_id": "90",
                "stock_name": "旧股票",
                "concepts": ["机器人"],
                "reason": "历史机器人讨论。",
                "confidence": 0.6,
            }
        ]

        candidates = build_research_radar_candidates(
            topics=topics,
            current_stock_rows=current_rows,
            baseline_stock_rows=baseline_rows,
            max_candidates=5,
        )

        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertEqual("PCB", candidate["direction"])
        self.assertEqual("strong", candidate["tier"])
        self.assertGreaterEqual(candidate["confidence"], 0.75)
        self.assertEqual(["涨价/供需"], candidate["catalysts"])
        self.assertEqual(["PCB"], candidate["concepts"])
        self.assertEqual(["沪电股份", "胜宏科技"], [stock["name"] for stock in candidate["stocks"]])
        self.assertEqual(1, len(candidate["evidence"]))
        self.assertEqual("topic", candidate["evidence"][0]["source_type"])
        self.assertEqual("101", candidate["evidence"][0]["topic_id"])
        self.assertIn("AI服务器需求", candidate["evidence"][0]["excerpt"])

    def test_build_candidates_marks_single_evidence_as_weak_signal(self):
        from backend.services.research_radar_signal import build_research_radar_candidates

        candidates = build_research_radar_candidates(
            topics=[
                {
                    "topic_id": "201",
                    "title": "新材料线索",
                    "create_time": "2026-06-26T10:00:00.000+0800",
                    "talk_text": "新材料方向出现国产替代讨论。",
                    "comments": [],
                }
            ],
            current_stock_rows=[
                {
                    "topic_id": "201",
                    "stock_name": "材料公司",
                    "concepts": ["新材料", "国产替代/自主可控"],
                    "reason": "国产替代讨论刚出现。",
                    "confidence": 0.45,
                }
            ],
            baseline_stock_rows=[],
            max_candidates=5,
        )

        self.assertEqual(1, len(candidates))
        self.assertEqual("weak", candidates[0]["tier"])
        self.assertEqual(["国产替代/自主可控"], candidates[0]["catalysts"])

    def test_build_candidates_returns_empty_without_stock_rows(self):
        from backend.services.research_radar_signal import build_research_radar_candidates

        self.assertEqual(
            [],
            build_research_radar_candidates(
                topics=[{"topic_id": "1", "title": "只有话题", "talk_text": "没有股票抽取"}],
                current_stock_rows=[],
                baseline_stock_rows=[],
            ),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing signal tests**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_signal -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.research_radar_signal'`.

- [ ] **Step 3: Implement signal module**

Create `backend/services/research_radar_signal.py`:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List


CATALYST_TERMS = {
    "涨价/供需",
    "国产替代/自主可控",
    "出海/出口",
    "订单/扩产",
    "政策",
    "业绩",
    "并购",
    "供需紧张",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _topic_key(value: Any) -> str:
    return _text(value)


def _topic_text(topic: Dict[str, Any]) -> str:
    parts = [
        _text(topic.get("title")),
        _text(topic.get("talk_text")),
        _text(topic.get("question_text")),
        _text(topic.get("answer_text")),
    ]
    for comment in topic.get("comments") or []:
        if isinstance(comment, dict):
            parts.append(_text(comment.get("text")))
    return "\n".join(part for part in parts if part)


def _clip(value: str, limit: int = 260) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _row_concepts(row: Dict[str, Any]) -> List[str]:
    return _text_list(row.get("concepts"))


def _row_catalysts(row: Dict[str, Any]) -> List[str]:
    concepts = _row_concepts(row)
    reason = _text(row.get("reason"))
    catalysts = [concept for concept in concepts if concept in CATALYST_TERMS]
    for term in CATALYST_TERMS:
        if term not in catalysts and term.replace("/", "") in reason.replace("/", ""):
            catalysts.append(term)
    return catalysts


def _row_directions(row: Dict[str, Any]) -> List[str]:
    return [concept for concept in _row_concepts(row) if concept not in CATALYST_TERMS]


def _stock_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": _text(row.get("stock_name")),
        "code": _text(row.get("stock_code")),
        "market": _text(row.get("market")),
        "confidence": float(row.get("confidence") or 0),
    }


def _baseline_directions(rows: Iterable[Dict[str, Any]]) -> set[str]:
    directions: set[str] = set()
    for row in rows:
        directions.update(_row_directions(row))
    return directions


def _evidence_for_topic(topic: Dict[str, Any], row: Dict[str, Any], direction: str) -> Dict[str, Any]:
    topic_id = _topic_key(topic.get("topic_id") or row.get("topic_id"))
    return {
        "source_type": "topic",
        "source_id": topic_id,
        "topic_id": topic_id,
        "source_time": _text(topic.get("create_time")),
        "excerpt": _clip(_topic_text(topic) or _text(row.get("excerpt")) or _text(row.get("reason"))),
        "matched_entities": {
            "direction": direction,
            "concepts": _row_concepts(row),
            "stock_name": _text(row.get("stock_name")),
        },
        "support_reason": _text(row.get("reason")) or f"话题提到{direction}相关股票。",
        "navigation": {"type": "topic", "topic_id": topic_id},
    }


def _confidence(topic_count: int, stock_count: int, catalyst_count: int, is_new: bool, row_confidence: float) -> float:
    score = 0.35 + min(topic_count, 4) * 0.1 + min(stock_count, 4) * 0.08 + min(catalyst_count, 3) * 0.08
    if is_new:
        score += 0.08
    score += min(max(row_confidence, 0), 1) * 0.2
    return round(min(score, 0.99), 3)


def _tier(confidence: float, evidence_count: int, stock_count: int) -> str:
    if confidence >= 0.75 and (evidence_count >= 2 or stock_count >= 2):
        return "strong"
    if confidence >= 0.58 and evidence_count >= 1:
        return "medium"
    return "weak"


def build_research_radar_candidates(
    *,
    topics: List[Dict[str, Any]],
    current_stock_rows: List[Dict[str, Any]],
    baseline_stock_rows: List[Dict[str, Any]],
    max_candidates: int = 8,
) -> List[Dict[str, Any]]:
    if not current_stock_rows:
        return []

    topics_by_id = {_topic_key(topic.get("topic_id")): topic for topic in topics}
    baseline = _baseline_directions(baseline_stock_rows)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in current_stock_rows:
        for direction in _row_directions(row):
            grouped[direction].append(row)

    candidates: List[Dict[str, Any]] = []
    for direction, rows in grouped.items():
        topic_ids = sorted({_topic_key(row.get("topic_id")) for row in rows if _topic_key(row.get("topic_id"))})
        stocks_by_name: Dict[str, Dict[str, Any]] = {}
        catalysts: List[str] = []
        evidence: List[Dict[str, Any]] = []
        max_row_confidence = 0.0
        for row in rows:
            stock = _stock_payload(row)
            if stock["name"] and stock["name"] not in stocks_by_name:
                stocks_by_name[stock["name"]] = stock
            for catalyst in _row_catalysts(row):
                if catalyst not in catalysts:
                    catalysts.append(catalyst)
            max_row_confidence = max(max_row_confidence, float(row.get("confidence") or 0))
            topic_id = _topic_key(row.get("topic_id"))
            topic = topics_by_id.get(topic_id)
            if topic and topic_id not in {item["topic_id"] for item in evidence}:
                evidence.append(_evidence_for_topic(topic, row, direction))

        confidence = _confidence(
            len(topic_ids),
            len(stocks_by_name),
            len(catalysts),
            direction not in baseline,
            max_row_confidence,
        )
        candidates.append(
            {
                "candidate_id": f"direction:{direction}",
                "direction": direction,
                "title": f"{direction}研究信号升温",
                "summary": f"{direction}在当前窗口出现研究信号，关联{len(stocks_by_name)}只股票和{len(evidence)}条证据。",
                "tier": _tier(confidence, len(evidence), len(stocks_by_name)),
                "confidence": confidence,
                "concepts": [direction],
                "stocks": list(stocks_by_name.values()),
                "catalysts": catalysts,
                "risks": [],
                "evidence": evidence,
                "evidence_count": len(evidence),
            }
        )

    tier_order = {"strong": 0, "medium": 1, "weak": 2}
    return sorted(
        candidates,
        key=lambda item: (tier_order.get(str(item["tier"]), 9), -float(item["confidence"]), str(item["direction"])),
    )[:max_candidates]
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_signal -v
```

Expected: PASS.

Commit:

```powershell
git add backend/services/research_radar_signal.py tests/test_research_radar_signal.py
git commit -m "Add research radar signal candidates"
```

## Task 3: Research Radar Store

**Files:**
- Create: `backend/services/research_radar_store.py`
- Create: `tests/test_research_radar_store.py`

- [ ] **Step 1: Write failing store tests**

Create `tests/test_research_radar_store.py`:

```python
import unittest
from unittest.mock import Mock


class ResearchRadarStoreTests(unittest.TestCase):
    def test_save_research_radar_run_replaces_existing_date_and_serializes_children(self):
        from backend.services.research_radar_store import save_research_radar_run

        conn = Mock()
        existing_cursor = Mock()
        existing_cursor.fetchall.return_value = [{"id": 7}]
        insert_cursor = Mock()
        insert_cursor.fetchone.return_value = {"id": 8}
        conn.execute.side_effect = [
            existing_cursor,
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            insert_cursor,
            Mock(),
            Mock(),
            Mock(),
            Mock(),
        ]

        run_id = save_research_radar_run(
            conn,
            group_id="303",
            report_date="2026-06-26",
            task_id="task-1",
            status="completed",
            model="model-a",
            logic_items=[
                {
                    "title": "PCB研究信号升温",
                    "summary": "PCB方向由涨价和AI服务器需求驱动。",
                    "tier": "strong",
                    "direction": "PCB",
                    "concepts": ["PCB"],
                    "stocks": [{"name": "沪电股份", "code": "002463", "market": "SZ"}],
                    "catalysts": ["涨价/供需"],
                    "risks": [],
                    "confidence": 0.82,
                    "evidence": [
                        {
                            "source_type": "topic",
                            "source_id": "101",
                            "topic_id": "101",
                            "source_time": "2026-06-26T08:30:00.000+0800",
                            "excerpt": "AI服务器需求拉动PCB。",
                            "matched_entities": {"direction": "PCB"},
                            "support_reason": "话题讨论PCB涨价。",
                            "navigation": {"type": "topic", "topic_id": "101"},
                        }
                    ],
                }
            ],
            summary={"direction_count": 1},
        )

        self.assertEqual(8, run_id)
        self.assertIn("SELECT id FROM research_radar_runs", conn.execute.call_args_list[0].args[0])
        self.assertIn("DELETE FROM research_radar_evidence", conn.execute.call_args_list[1].args[0])
        self.assertIn("INSERT INTO research_radar_runs", conn.execute.call_args_list[5].args[0])
        self.assertIn("INSERT INTO research_radar_logic_items", conn.execute.call_args_list[6].args[0])
        self.assertIn("INSERT INTO research_radar_evidence", conn.execute.call_args_list[7].args[0])
        self.assertIn("INSERT INTO research_radar_entities", conn.execute.call_args_list[8].args[0])
        conn.commit.assert_called_once_with()

    def test_load_research_radar_run_maps_logic_evidence_and_entities(self):
        from backend.services.research_radar_store import load_research_radar_run_by_date

        conn = Mock()
        run_cursor = Mock()
        run_cursor.fetchone.return_value = {
            "id": 8,
            "group_id": "303",
            "report_date": "2026-06-26",
            "window_days": 1,
            "status": "completed",
            "model": "model-a",
            "summary_json": '{"direction_count": 1}',
            "task_id": "task-1",
            "error": "",
            "created_at": "2026-06-26T09:00:00",
            "updated_at": "2026-06-26T09:01:00",
        }
        logic_cursor = Mock()
        logic_cursor.fetchall.return_value = [
            {
                "id": 10,
                "rank": 1,
                "tier": "strong",
                "title": "PCB研究信号升温",
                "summary": "PCB方向由涨价驱动。",
                "direction": "PCB",
                "concepts_json": '["PCB"]',
                "stocks_json": '[{"name": "沪电股份"}]',
                "catalysts_json": '["涨价/供需"]',
                "risks_json": "[]",
                "evidence_count": 1,
                "confidence": 0.82,
            }
        ]
        evidence_cursor = Mock()
        evidence_cursor.fetchall.return_value = [
            {
                "id": 20,
                "logic_id": 10,
                "source_type": "topic",
                "source_id": "101",
                "topic_id": "101",
                "source_time": "2026-06-26T08:30:00.000+0800",
                "excerpt": "AI服务器需求拉动PCB。",
                "matched_entities_json": '{"direction": "PCB"}',
                "support_reason": "话题讨论PCB涨价。",
                "navigation_json": '{"type": "topic", "topic_id": "101"}',
            }
        ]
        entity_cursor = Mock()
        entity_cursor.fetchall.return_value = [
            {
                "logic_id": 10,
                "entity_type": "stock",
                "name": "沪电股份",
                "code": "002463",
                "market": "SZ",
                "weight": 0.82,
                "evidence_count": 1,
            }
        ]
        conn.execute.side_effect = [run_cursor, logic_cursor, evidence_cursor, entity_cursor]

        result = load_research_radar_run_by_date(conn, group_id="303", report_date="2026-06-26")

        self.assertEqual("303", result["group_id"])
        self.assertEqual("PCB研究信号升温", result["logic_items"][0]["title"])
        self.assertEqual("101", result["logic_items"][0]["evidence"][0]["topic_id"])
        self.assertEqual("沪电股份", result["logic_items"][0]["entities"][0]["name"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing store tests**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_store -v
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement store module**

Create `backend/services/research_radar_store.py` with these public functions:

```python
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _json_obj(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False)


def _parse_json(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _existing_run_ids(conn: Any, group_id: str, report_date: str) -> List[int]:
    rows = conn.execute(
        "SELECT id FROM research_radar_runs WHERE group_id = ? AND report_date = ?",
        (group_id, report_date),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _delete_existing_runs(conn: Any, run_ids: List[int]) -> None:
    for run_id in run_ids:
        conn.execute(
            """
            DELETE FROM research_radar_evidence
            WHERE logic_id IN (SELECT id FROM research_radar_logic_items WHERE run_id = ?)
            """,
            (run_id,),
        )
        conn.execute("DELETE FROM research_radar_entities WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM research_radar_logic_items WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM research_radar_runs WHERE id = ?", (run_id,))


def _insert_run(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    task_id: str,
    status: str,
    model: str,
    summary: Dict[str, Any],
    error: str,
) -> int:
    now = _now()
    row = conn.execute(
        """
        INSERT INTO research_radar_runs (
            group_id, report_date, window_days, status, model,
            summary_json, task_id, error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (group_id, report_date, 1, status, model, _json_obj(summary), task_id, error, now, now),
    ).fetchone()
    return int(row["id"])


def _insert_logic_item(conn: Any, *, run_id: int, rank: int, item: Dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO research_radar_logic_items (
            run_id, rank, tier, title, summary, direction, concepts_json,
            stocks_json, catalysts_json, risks_json, evidence_count,
            confidence, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            run_id,
            rank,
            str(item.get("tier") or "weak"),
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
            str(item.get("direction") or ""),
            _json(item.get("concepts") or []),
            _json(item.get("stocks") or []),
            _json(item.get("catalysts") or []),
            _json(item.get("risks") or []),
            int(item.get("evidence_count") or len(item.get("evidence") or [])),
            float(item.get("confidence") or 0),
            _now(),
        ),
    ).fetchone()
    return int(row["id"])


def _insert_evidence(conn: Any, *, logic_id: int, evidence: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO research_radar_evidence (
            logic_id, source_type, source_id, topic_id, source_time,
            excerpt, matched_entities_json, support_reason,
            navigation_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            logic_id,
            str(evidence.get("source_type") or ""),
            str(evidence.get("source_id") or ""),
            str(evidence.get("topic_id") or ""),
            str(evidence.get("source_time") or ""),
            str(evidence.get("excerpt") or ""),
            _json_obj(evidence.get("matched_entities")),
            str(evidence.get("support_reason") or ""),
            _json_obj(evidence.get("navigation")),
            _now(),
        ),
    )


def _insert_entities(conn: Any, *, run_id: int, logic_id: int, item: Dict[str, Any]) -> None:
    for concept in item.get("concepts") or []:
        conn.execute(
            """
            INSERT INTO research_radar_entities (
                run_id, logic_id, entity_type, name, code, market,
                weight, evidence_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, logic_id, "concept", str(concept), "", "", float(item.get("confidence") or 0), int(item.get("evidence_count") or 0), _now()),
        )
    for stock in item.get("stocks") or []:
        if not isinstance(stock, dict):
            continue
        conn.execute(
            """
            INSERT INTO research_radar_entities (
                run_id, logic_id, entity_type, name, code, market,
                weight, evidence_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                logic_id,
                "stock",
                str(stock.get("name") or ""),
                str(stock.get("code") or ""),
                str(stock.get("market") or ""),
                float(stock.get("confidence") or item.get("confidence") or 0),
                int(item.get("evidence_count") or 0),
                _now(),
            ),
        )


def save_research_radar_run(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    task_id: str,
    status: str,
    model: str,
    logic_items: List[Dict[str, Any]],
    summary: Dict[str, Any],
    error: str = "",
) -> int:
    _delete_existing_runs(conn, _existing_run_ids(conn, group_id, report_date))
    run_id = _insert_run(
        conn,
        group_id=group_id,
        report_date=report_date,
        task_id=task_id,
        status=status,
        model=model,
        summary=summary,
        error=error,
    )
    for rank, item in enumerate(logic_items, start=1):
        logic_id = _insert_logic_item(conn, run_id=run_id, rank=rank, item=item)
        for evidence in item.get("evidence") or []:
            if isinstance(evidence, dict):
                _insert_evidence(conn, logic_id=logic_id, evidence=evidence)
        _insert_entities(conn, run_id=run_id, logic_id=logic_id, item=item)
    conn.commit()
    return run_id


def _load_run_row(conn: Any, *, group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if report_date:
        return conn.execute(
            """
            SELECT id, group_id, report_date, window_days, status, model, summary_json,
                   task_id, error, created_at, updated_at
            FROM research_radar_runs
            WHERE group_id = ? AND report_date = ?
            """,
            (group_id, report_date),
        ).fetchone()
    return conn.execute(
        """
        SELECT id, group_id, report_date, window_days, status, model, summary_json,
               task_id, error, created_at, updated_at
        FROM research_radar_runs
        WHERE group_id = ?
        ORDER BY report_date DESC, id DESC
        LIMIT 1
        """,
        (group_id,),
    ).fetchone()


def _load_logic_rows(conn: Any, run_id: int) -> List[Any]:
    return conn.execute(
        """
        SELECT id, rank, tier, title, summary, direction, concepts_json, stocks_json,
               catalysts_json, risks_json, evidence_count, confidence
        FROM research_radar_logic_items
        WHERE run_id = ?
        ORDER BY rank ASC, id ASC
        """,
        (run_id,),
    ).fetchall()


def _load_evidence_rows(conn: Any, logic_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    evidence_by_logic: Dict[int, List[Dict[str, Any]]] = {logic_id: [] for logic_id in logic_ids}
    for logic_id in logic_ids:
        rows = conn.execute(
            """
            SELECT id, logic_id, source_type, source_id, topic_id, source_time,
                   excerpt, matched_entities_json, support_reason, navigation_json
            FROM research_radar_evidence
            WHERE logic_id = ?
            ORDER BY id ASC
            """,
            (logic_id,),
        ).fetchall()
        evidence_by_logic[logic_id] = [
            {
                "id": row["id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "topic_id": row["topic_id"],
                "source_time": row["source_time"],
                "excerpt": row["excerpt"],
                "matched_entities": _parse_json(row["matched_entities_json"], {}),
                "support_reason": row["support_reason"],
                "navigation": _parse_json(row["navigation_json"], {}),
            }
            for row in rows
        ]
    return evidence_by_logic


def _load_entity_rows(conn: Any, logic_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    entities_by_logic: Dict[int, List[Dict[str, Any]]] = {logic_id: [] for logic_id in logic_ids}
    for logic_id in logic_ids:
        rows = conn.execute(
            """
            SELECT logic_id, entity_type, name, code, market, weight, evidence_count
            FROM research_radar_entities
            WHERE logic_id = ?
            ORDER BY entity_type ASC, weight DESC, name ASC
            """,
            (logic_id,),
        ).fetchall()
        entities_by_logic[logic_id] = [
            {
                "entity_type": row["entity_type"],
                "name": row["name"],
                "code": row["code"],
                "market": row["market"],
                "weight": float(row["weight"] or 0),
                "evidence_count": int(row["evidence_count"] or 0),
            }
            for row in rows
        ]
    return entities_by_logic


def _map_run(conn: Any, run_row: Any) -> Dict[str, Any]:
    run_id = int(run_row["id"])
    logic_rows = _load_logic_rows(conn, run_id)
    logic_ids = [int(row["id"]) for row in logic_rows]
    evidence_by_logic = _load_evidence_rows(conn, logic_ids)
    entities_by_logic = _load_entity_rows(conn, logic_ids)
    return {
        "id": run_id,
        "group_id": run_row["group_id"],
        "report_date": run_row["report_date"],
        "window_days": int(run_row["window_days"] or 1),
        "status": run_row["status"],
        "model": run_row["model"],
        "summary": _parse_json(run_row["summary_json"], {}),
        "task_id": run_row["task_id"],
        "error": run_row["error"],
        "created_at": run_row["created_at"],
        "updated_at": run_row["updated_at"],
        "logic_items": [
            {
                "id": int(row["id"]),
                "rank": int(row["rank"] or 0),
                "tier": row["tier"],
                "title": row["title"],
                "summary": row["summary"],
                "direction": row["direction"],
                "concepts": _parse_json(row["concepts_json"], []),
                "stocks": _parse_json(row["stocks_json"], []),
                "catalysts": _parse_json(row["catalysts_json"], []),
                "risks": _parse_json(row["risks_json"], []),
                "evidence_count": int(row["evidence_count"] or 0),
                "confidence": float(row["confidence"] or 0),
                "evidence": evidence_by_logic.get(int(row["id"]), []),
                "entities": entities_by_logic.get(int(row["id"]), []),
            }
            for row in logic_rows
        ],
    }


def load_latest_research_radar_run(conn: Any, *, group_id: str) -> Optional[Dict[str, Any]]:
    row = _load_run_row(conn, group_id=group_id)
    return _map_run(conn, row) if row else None


def load_research_radar_run_by_date(conn: Any, *, group_id: str, report_date: str) -> Optional[Dict[str, Any]]:
    row = _load_run_row(conn, group_id=group_id, report_date=report_date)
    return _map_run(conn, row) if row else None
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_store -v
```

Expected: PASS.

Commit:

```powershell
git add backend/services/research_radar_store.py tests/test_research_radar_store.py
git commit -m "Add research radar persistence"
```

## Task 4: Evidence-Constrained AI Wording

**Files:**
- Create: `backend/services/research_radar_ai.py`
- Create: `tests/test_research_radar_ai.py`

- [ ] **Step 1: Write failing AI helper tests**

Create `tests/test_research_radar_ai.py`:

```python
import unittest
from unittest.mock import patch


class ResearchRadarAITests(unittest.TestCase):
    def test_apply_ai_logic_summaries_keeps_candidate_evidence_and_updates_wording(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [
            {
                "candidate_id": "direction:PCB",
                "direction": "PCB",
                "title": "PCB研究信号升温",
                "summary": "old",
                "tier": "strong",
                "confidence": 0.82,
                "concepts": ["PCB"],
                "stocks": [{"name": "沪电股份"}],
                "catalysts": ["涨价/供需"],
                "risks": [],
                "evidence": [{"topic_id": "101", "excerpt": "PCB涨价"}],
                "evidence_count": 1,
            }
        ]
        payload = {
            "logic_items": [
                {
                    "candidate_id": "direction:PCB",
                    "title": "PCB涨价逻辑升温",
                    "summary": "多条讨论把PCB关注度归因于涨价和AI服务器需求。",
                }
            ]
        }

        result = apply_ai_logic_summaries(candidates, payload)

        self.assertEqual("PCB涨价逻辑升温", result[0]["title"])
        self.assertEqual("多条讨论把PCB关注度归因于涨价和AI服务器需求。", result[0]["summary"])
        self.assertEqual([{"topic_id": "101", "excerpt": "PCB涨价"}], result[0]["evidence"])

    def test_apply_ai_logic_summaries_ignores_unknown_candidate_ids(self):
        from backend.services.research_radar_ai import apply_ai_logic_summaries

        candidates = [{"candidate_id": "direction:PCB", "title": "old", "summary": "old"}]
        payload = {"logic_items": [{"candidate_id": "direction:机器人", "title": "bad", "summary": "bad"}]}

        result = apply_ai_logic_summaries(candidates, payload)

        self.assertEqual("old", result[0]["title"])
        self.assertEqual("old", result[0]["summary"])

    def test_summarize_radar_candidates_calls_structured_ai_object(self):
        from backend.services import research_radar_ai as ai

        candidates = [
            {
                "candidate_id": "direction:PCB",
                "direction": "PCB",
                "title": "PCB研究信号升温",
                "summary": "old",
                "evidence": [{"topic_id": "101", "excerpt": "PCB涨价"}],
            }
        ]

        with patch.object(
            ai,
            "call_structured_ai_object",
            return_value=type("Result", (), {
                "payload": {
                    "logic_items": [
                        {
                            "candidate_id": "direction:PCB",
                            "title": "PCB涨价逻辑升温",
                            "summary": "证据显示PCB涨价逻辑被集中讨论。",
                        }
                    ]
                },
                "model": "model-a",
            })(),
        ) as call_ai:
            items, model = ai.summarize_radar_candidates(candidates, report_date="2026-06-26")

        self.assertEqual("model-a", model)
        self.assertEqual("PCB涨价逻辑升温", items[0]["title"])
        call_ai.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing AI tests**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_ai -v
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement AI helper**

Create `backend/services/research_radar_ai.py`:

```python
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from backend.core.ai_provider_config import get_openai_compatible_config, get_summary_reasoning_effort
from backend.services.ai_runtime_request import call_structured_ai_object


RESEARCH_RADAR_AI_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "logic_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["candidate_id", "title", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["logic_items"],
    "additionalProperties": False,
}


def _text(value: Any, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _candidate_prompt_payload(candidates: List[Dict[str, Any]]) -> str:
    safe_candidates = []
    for candidate in candidates:
        safe_candidates.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "direction": candidate.get("direction"),
                "tier": candidate.get("tier"),
                "confidence": candidate.get("confidence"),
                "concepts": candidate.get("concepts") or [],
                "stocks": candidate.get("stocks") or [],
                "catalysts": candidate.get("catalysts") or [],
                "evidence": [
                    {
                        "topic_id": evidence.get("topic_id"),
                        "excerpt": evidence.get("excerpt"),
                        "support_reason": evidence.get("support_reason"),
                    }
                    for evidence in candidate.get("evidence") or []
                    if isinstance(evidence, dict)
                ],
            }
        )
    return json.dumps(safe_candidates, ensure_ascii=False)


def apply_ai_logic_summaries(
    candidates: List[Dict[str, Any]],
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    updates = {
        str(item.get("candidate_id") or ""): item
        for item in payload.get("logic_items") or []
        if isinstance(item, dict)
    }
    result: List[Dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        update = updates.get(str(candidate.get("candidate_id") or ""))
        if update:
            title = _text(update.get("title"), 120)
            summary = _text(update.get("summary"), 800)
            if title:
                item["title"] = title
            if summary:
                item["summary"] = summary
        result.append(item)
    return result


def summarize_radar_candidates(
    candidates: List[Dict[str, Any]],
    *,
    report_date: str,
) -> Tuple[List[Dict[str, Any]], str]:
    if not candidates:
        return [], ""

    messages = [
        {
            "role": "system",
            "content": (
                "你是A股研究雷达写作助手。"
                "只能改写输入候选线索的标题和摘要，不得新增候选、股票、概念、催化或证据。"
                "摘要必须解释证据支持的研究逻辑，不能给买卖建议。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请把 {report_date} 的候选线索改写成简洁中文研究雷达文案。"
                "只返回 JSON schema 要求的 candidate_id、title、summary。"
                f"\n\n候选线索：\n{_candidate_prompt_payload(candidates)}"
            ),
        },
    ]

    result = call_structured_ai_object(
        messages=messages,
        get_ai_config=get_openai_compatible_config,
        schema_name="research_radar_logic_summaries",
        schema=RESEARCH_RADAR_AI_SCHEMA,
        label="研究雷达 AI 摘要结果",
        reasoning_effort=get_summary_reasoning_effort(),
        timeout=180,
    )
    return apply_ai_logic_summaries(candidates, result.payload), result.model
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_ai -v
```

Expected: PASS.

Commit:

```powershell
git add backend/services/research_radar_ai.py tests/test_research_radar_ai.py
git commit -m "Add research radar AI wording"
```

## Task 5: Workflow, Routes, And App Registration

**Files:**
- Create: `backend/services/research_radar_workflow.py`
- Create: `backend/routes/research_radar_routes.py`
- Create: `tests/test_research_radar_workflow.py`
- Create: `tests/test_research_radar_routes_helpers.py`
- Modify: `backend/main.py`
- Modify: `tests/test_app_factory.py`

- [ ] **Step 1: Write failing workflow tests**

Create `tests/test_research_radar_workflow.py`:

```python
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch


class ResearchRadarWorkflowTests(unittest.TestCase):
    def test_generate_research_radar_uses_existing_sources_and_saves_run(self):
        from backend.services import research_radar_workflow as workflow

        conn = Mock()
        material = SimpleNamespace(
            topics=[{"topic_id": "101", "title": "PCB", "talk_text": "PCB涨价"}],
            topic_count=1,
        )
        current_rows = [{"topic_id": "101", "stock_name": "沪电股份", "concepts": ["PCB"], "confidence": 0.8}]
        baseline_rows = [{"topic_id": "90", "stock_name": "旧股票", "concepts": ["机器人"], "confidence": 0.6}]
        candidates = [{"candidate_id": "direction:PCB", "direction": "PCB", "title": "PCB", "summary": "PCB", "evidence": []}]

        with (
            patch.object(workflow, "connect_topic_material_db", return_value=conn),
            patch.object(workflow, "load_daily_topic_material", return_value=material) as load_material,
            patch.object(workflow, "load_topic_stock_extractions", side_effect=[current_rows, baseline_rows]) as load_rows,
            patch.object(workflow, "build_research_radar_candidates", return_value=candidates) as build_candidates,
            patch.object(workflow, "summarize_radar_candidates", return_value=(candidates, "model-a")) as summarize,
            patch.object(workflow, "save_research_radar_run", return_value=12) as save_run,
        ):
            result = workflow.generate_research_radar("303", "2026-06-26", task_id="task-1")

        load_material.assert_called_once_with("303", report_date=date(2026, 6, 26), comments_per_topic=8)
        self.assertEqual(2, load_rows.call_count)
        build_candidates.assert_called_once()
        summarize.assert_called_once_with(candidates, report_date="2026-06-26")
        save_run.assert_called_once()
        conn.close.assert_called_once_with()
        self.assertEqual(12, result["run_id"])
        self.assertEqual(1, result["logic_count"])

    def test_create_research_radar_task_uses_task_launch_recipe(self):
        from backend.services import research_radar_workflow as workflow

        with patch.object(
            workflow,
            "launch_task_recipe",
            return_value={"task_id": "task-radar", "message": "任务已创建，正在后台执行"},
        ) as launch:
            response = workflow.create_research_radar_task("303", date="2026-06-26", comments_per_topic=5)

        self.assertEqual({"task_id": "task-radar", "message": "任务已创建，正在后台执行"}, response)
        recipe = launch.call_args.args[0]
        self.assertEqual("research_radar", recipe.task_type)
        self.assertEqual("303", recipe.group_id)
        self.assertEqual(("303", recipe.args[1]), recipe.args)
        self.assertEqual("2026-06-26", recipe.metadata["report_date"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Write failing route helper tests**

Create `tests/test_research_radar_routes_helpers.py`:

```python
import unittest
from importlib.util import find_spec
from unittest.mock import patch


HAS_ROUTE_DEPS = find_spec("fastapi") is not None and find_spec("pydantic") is not None


class ResearchRadarRoutesHelperTests(unittest.TestCase):
    @unittest.skipUnless(HAS_ROUTE_DEPS, "research radar route dependencies are not installed")
    def test_create_research_radar_task_response_delegates_to_workflow(self):
        from backend.routes.research_radar_routes import ResearchRadarRequest, _create_research_radar_task_response

        request = ResearchRadarRequest(date="2026-06-26", commentsPerTopic=5)

        with patch(
            "backend.routes.research_radar_routes.create_research_radar_task",
            return_value={"task_id": "task-radar", "message": "任务已创建，正在后台执行"},
        ) as create_task:
            response = _create_research_radar_task_response("303", request)

        create_task.assert_called_once_with("303", date="2026-06-26", comments_per_topic=5)
        self.assertEqual({"task_id": "task-radar", "message": "任务已创建，正在后台执行"}, response)

    @unittest.skipUnless(HAS_ROUTE_DEPS, "research radar route dependencies are not installed")
    def test_read_research_radar_or_404_raises_for_missing_result(self):
        from fastapi import HTTPException
        from backend.routes import research_radar_routes

        with patch.object(research_radar_routes, "get_research_radar", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                research_radar_routes._research_radar_or_404("303", "2026-06-26")

        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("研究雷达结果不存在，请先生成", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Add failing app factory assertion**

In `tests/test_app_factory.py`, add:

```python
self.assertIn("/api/analysis/research-radar/{group_id}", paths)
```

- [ ] **Step 4: Run failing tests**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_workflow tests.test_research_radar_routes_helpers tests.test_app_factory -v
```

Expected: FAIL with missing workflow/route module and missing app path.

- [ ] **Step 5: Implement workflow**

Create `backend/services/research_radar_workflow.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Dict, Optional

from backend.services.a_share_analysis_db_storage import load_topic_stock_extractions
from backend.services.research_radar_ai import summarize_radar_candidates
from backend.services.research_radar_signal import build_research_radar_candidates
from backend.services.research_radar_store import (
    load_latest_research_radar_run,
    load_research_radar_run_by_date,
    save_research_radar_run,
)
from backend.services.task_launch import TaskLaunchRecipe, launch_task_recipe
from backend.services.task_runtime import build_task_log_callback, run_workflow
from backend.services.topic_material import (
    DEFAULT_COMMENTS_PER_TOPIC,
    connect_topic_material_db,
    load_daily_topic_material,
    parse_topic_material_date,
)


LogCallback = Optional[Callable[[str], None]]


@dataclass(frozen=True)
class ResearchRadarTaskRequest:
    date: Optional[str] = None
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC

    def __post_init__(self) -> None:
        normalized = int(self.comments_per_topic)
        if normalized < 0 or normalized > 50:
            raise ValueError("comments_per_topic must be between 0 and 50")
        object.__setattr__(self, "comments_per_topic", normalized)


def _log(log_callback: LogCallback, message: str) -> None:
    if log_callback:
        log_callback(message)


def _baseline_range(report_date) -> tuple[str, str]:
    start_date = report_date - timedelta(days=7)
    end_date = report_date - timedelta(days=1)
    return start_date.isoformat(), end_date.isoformat()


def _summary_payload(logic_items: list[dict[str, Any]]) -> Dict[str, Any]:
    return {
        "logic_count": len(logic_items),
        "strong_count": sum(1 for item in logic_items if item.get("tier") == "strong"),
        "medium_count": sum(1 for item in logic_items if item.get("tier") == "medium"),
        "weak_count": sum(1 for item in logic_items if item.get("tier") == "weak"),
        "direction_count": len({str(item.get("direction") or "") for item in logic_items if item.get("direction")}),
        "stock_count": len(
            {
                str(stock.get("name") or "")
                for item in logic_items
                for stock in (item.get("stocks") or [])
                if isinstance(stock, dict) and stock.get("name")
            }
        ),
    }


def generate_research_radar(
    group_id: str,
    report_date: Optional[str] = None,
    *,
    task_id: str = "",
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
    log_callback: LogCallback = None,
) -> Dict[str, Any]:
    parsed_date = parse_topic_material_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = connect_topic_material_db(group_id)
    try:
        _log(log_callback, f"读取 {report_date_text} 的研究雷达材料...")
        material = load_daily_topic_material(
            group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        baseline_start, baseline_end = _baseline_range(parsed_date)
        current_rows = load_topic_stock_extractions(
            group_id=group_id,
            start_date=report_date_text,
            end_date=report_date_text,
        )
        baseline_rows = load_topic_stock_extractions(
            group_id=group_id,
            start_date=baseline_start,
            end_date=baseline_end,
        )
        _log(log_callback, f"当天话题 {material.topic_count} 条，股票抽取明细 {len(current_rows)} 条")

        candidates = build_research_radar_candidates(
            topics=material.topics,
            current_stock_rows=current_rows,
            baseline_stock_rows=baseline_rows,
            max_candidates=8,
        )
        logic_items, model = summarize_radar_candidates(candidates, report_date=report_date_text)
        run_id = save_research_radar_run(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            task_id=task_id,
            status="completed",
            model=model,
            logic_items=logic_items,
            summary=_summary_payload(logic_items),
        )
        _log(log_callback, f"研究雷达生成完成，共 {len(logic_items)} 条逻辑")
        return {
            "group_id": group_id,
            "report_date": report_date_text,
            "run_id": run_id,
            "logic_count": len(logic_items),
        }
    finally:
        conn.close()


def run_research_radar_task(task_id: str, group_id: str, request: ResearchRadarTaskRequest) -> None:
    def work() -> Dict[str, Any]:
        return generate_research_radar(
            group_id,
            request.date,
            task_id=task_id,
            comments_per_topic=request.comments_per_topic,
            log_callback=build_task_log_callback(task_id),
        )

    run_workflow(
        task_id,
        running_message="开始生成研究雷达...",
        completed_message="研究雷达生成完成",
        failure_label="研究雷达生成",
        work=work,
    )


def create_research_radar_task(
    group_id: str,
    *,
    date: Optional[str] = None,
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
) -> Dict[str, str]:
    request = ResearchRadarTaskRequest(date=date, comments_per_topic=comments_per_topic)
    report_date = parse_topic_material_date(date).isoformat()
    return launch_task_recipe(
        TaskLaunchRecipe(
            task_type="research_radar",
            description=f"生成研究雷达 (群组: {group_id})",
            task_func=run_research_radar_task,
            args=(group_id, request),
            group_id=group_id,
            metadata={"report_date": report_date},
        )
    )


def get_research_radar(group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = connect_topic_material_db(group_id)
    try:
        if report_date:
            parsed_date = parse_topic_material_date(report_date)
            return load_research_radar_run_by_date(conn, group_id=group_id, report_date=parsed_date.isoformat())
        return load_latest_research_radar_run(conn, group_id=group_id)
    finally:
        conn.close()
```

- [ ] **Step 6: Implement route**

Create `backend/routes/research_radar_routes.py`:

```python
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.routes.task_http_errors import task_launch_route_error
from backend.services.research_radar_workflow import create_research_radar_task, get_research_radar


router = APIRouter(prefix="/api/analysis/research-radar", tags=["research-radar"])


class ResearchRadarRequest(BaseModel):
    date: Optional[str] = Field(default=None, description="雷达日期，格式 YYYY-MM-DD；默认今天（东八区）")
    commentsPerTopic: int = Field(default=8, ge=0, le=50, description="每个话题最多纳入的评论数")


def _create_research_radar_task_response(group_id: str, request: ResearchRadarRequest) -> dict[str, str]:
    return create_research_radar_task(
        group_id,
        date=request.date,
        comments_per_topic=request.commentsPerTopic,
    )


def _research_radar_route_error(message: str, error: Exception) -> HTTPException:
    return task_launch_route_error(message, error)


def _research_radar_or_404(group_id: str, date: Optional[str]) -> dict:
    result = get_research_radar(group_id, date)
    if not result:
        raise HTTPException(status_code=404, detail="研究雷达结果不存在，请先生成")
    return result


@router.post("/{group_id}")
async def create_research_radar(group_id: str, request: ResearchRadarRequest):
    try:
        return _create_research_radar_task_response(group_id, request)
    except Exception as exc:
        raise _research_radar_route_error("创建研究雷达任务失败", exc)


@router.get("/{group_id}")
async def read_research_radar(
    group_id: str,
    date: Optional[str] = Query(default=None, description="雷达日期，格式 YYYY-MM-DD；不传则读取最近一次"),
):
    try:
        return _research_radar_or_404(group_id, date)
    except HTTPException:
        raise
    except Exception as exc:
        raise _research_radar_route_error("获取研究雷达失败", exc)
```

- [ ] **Step 7: Register app route**

In `backend/main.py`, add import:

```python
from backend.routes.research_radar_routes import router as research_radar_router
```

Add `research_radar_router` to the router tuple near other analysis routers:

```python
research_radar_router,
```

If retention router changes are present, keep them intact.

- [ ] **Step 8: Run tests and commit**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_workflow tests.test_research_radar_routes_helpers tests.test_app_factory -v
```

Expected: PASS.

Commit:

```powershell
git add backend/services/research_radar_workflow.py backend/routes/research_radar_routes.py tests/test_research_radar_workflow.py tests/test_research_radar_routes_helpers.py backend/main.py tests/test_app_factory.py
git commit -m "Add research radar workflow routes"
```

Use `git commit --only ...` if unrelated staged files exist.

## Task 6: Frontend API And Research Radar Tab

**Files:**
- Modify: `frontend/src/lib/api/analysisTypes.ts`
- Modify: `frontend/src/lib/api/analysis.ts`
- Create: `frontend/src/components/ResearchRadarPanel.tsx`
- Modify: `frontend/src/components/GroupWorkbenchTabList.tsx`
- Modify: `frontend/src/app/groups/[groupId]/page.tsx`

- [ ] **Step 1: Add frontend types**

In `frontend/src/lib/api/analysisTypes.ts`, add these interfaces after `DailyStockConceptResponse`:

```typescript
export interface ResearchRadarRequestPayload {
  date?: string;
  commentsPerTopic?: number;
}

export interface ResearchRadarEvidence {
  id?: number;
  source_type: string;
  source_id: string;
  topic_id: string;
  source_time: string;
  excerpt: string;
  matched_entities: Record<string, unknown>;
  support_reason: string;
  navigation: {
    type?: string;
    topic_id?: string | number;
    [key: string]: unknown;
  };
}

export interface ResearchRadarEntity {
  entity_type: string;
  name: string;
  code?: string;
  market?: string;
  weight: number;
  evidence_count: number;
}

export interface ResearchRadarLogicItem {
  id?: number;
  rank: number;
  tier: 'strong' | 'medium' | 'weak' | string;
  title: string;
  summary: string;
  direction: string;
  concepts: string[];
  stocks: Array<{
    name: string;
    code?: string;
    market?: string;
    confidence?: number;
  }>;
  catalysts: string[];
  risks: string[];
  evidence_count: number;
  confidence: number;
  evidence: ResearchRadarEvidence[];
  entities: ResearchRadarEntity[];
}

export interface ResearchRadarRun {
  id: number;
  group_id: string;
  report_date: string;
  window_days: number;
  status: string;
  model?: string | null;
  summary: {
    logic_count?: number;
    strong_count?: number;
    medium_count?: number;
    weak_count?: number;
    direction_count?: number;
    stock_count?: number;
    [key: string]: unknown;
  };
  task_id?: string | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  logic_items: ResearchRadarLogicItem[];
}
```

- [ ] **Step 2: Add API client methods**

In `frontend/src/lib/api/analysis.ts`, add imports:

```typescript
ResearchRadarRequestPayload,
ResearchRadarRun,
```

Add methods inside `AnalysisApiClient` after daily stock concept methods:

```typescript
async createResearchRadar(
  groupId: number | string,
  payload: ResearchRadarRequestPayload = {}
): Promise<TaskCreateResponse> {
  return this.request(`/api/analysis/research-radar/${groupId}`, {
    method: 'POST',
    body: JSON.stringify({
      commentsPerTopic: payload.commentsPerTopic ?? 8,
      ...(payload.date ? { date: payload.date } : {}),
    }),
  });
}

async getResearchRadar(
  groupId: number | string,
  date?: string,
  options: ApiRequestOptions = {}
): Promise<ResearchRadarRun> {
  const search = new URLSearchParams();
  if (date) {
    search.set('date', date);
  }
  const query = search.toString();
  return this.request(`/api/analysis/research-radar/${groupId}${query ? `?${query}` : ''}`, {
    signal: options.signal,
  });
}
```

- [ ] **Step 3: Create ResearchRadarPanel**

Create `frontend/src/components/ResearchRadarPanel.tsx`:

```tsx
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Radar, RefreshCw, Search, Sparkles } from 'lucide-react';

import { apiClient, ResearchRadarLogicItem, ResearchRadarRun } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePickerButton } from '@/components/ui/date-picker-button';
import { Label } from '@/components/ui/label';
import { useTaskLauncher } from '@/hooks/useTaskLauncher';
import { getTodayText, formatDateTime } from '@/components/DailyTopicAnalysisPanelUtils';

interface ResearchRadarPanelProps {
  groupId: number;
  onTaskCreated?: (taskId: string) => void;
}

function tierLabel(tier: string) {
  if (tier === 'strong') return '强逻辑';
  if (tier === 'medium') return '中等逻辑';
  return '弱线索';
}

function tierClassName(tier: string) {
  if (tier === 'strong') return 'bg-emerald-100 text-emerald-800';
  if (tier === 'medium') return 'bg-blue-100 text-blue-800';
  return 'bg-amber-100 text-amber-800';
}

function LogicCard({ item }: { item: ResearchRadarLogicItem }) {
  return (
    <Card className="border border-gray-200 shadow-none">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="text-base">{item.title}</CardTitle>
          <div className="flex flex-wrap gap-1">
            <Badge className={tierClassName(item.tier)}>{tierLabel(item.tier)}</Badge>
            <Badge variant="outline">{Math.round((item.confidence || 0) * 100)}%</Badge>
          </div>
        </div>
        <CardDescription>{item.summary}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          {item.concepts.map((concept) => (
            <Badge key={`concept-${item.id}-${concept}`} variant="secondary">{concept}</Badge>
          ))}
          {item.catalysts.map((catalyst) => (
            <Badge key={`catalyst-${item.id}-${catalyst}`} className="bg-rose-100 text-rose-800">{catalyst}</Badge>
          ))}
        </div>

        {item.stocks.length > 0 && (
          <div className="rounded-md border border-gray-200 p-3">
            <div className="mb-2 text-sm font-medium">重点个股</div>
            <div className="flex flex-wrap gap-2">
              {item.stocks.map((stock) => (
                <Badge key={`${item.id}-${stock.name}-${stock.code || ''}`} variant="outline">
                  {stock.name}{stock.code ? ` ${stock.code}` : ''}
                </Badge>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <div className="text-sm font-medium">证据卡片</div>
          {item.evidence.length > 0 ? item.evidence.map((evidence) => (
            <div key={`${item.id}-${evidence.source_type}-${evidence.source_id}`} className="rounded-md border border-gray-200 bg-gray-50 p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">{evidence.source_type}</Badge>
                {evidence.topic_id && <span>话题 {evidence.topic_id}</span>}
                {evidence.source_time && <span>{formatDateTime(evidence.source_time)}</span>}
              </div>
              <div className="mt-2 text-sm leading-6 text-gray-800">{evidence.excerpt}</div>
              {evidence.support_reason && (
                <div className="mt-2 text-xs leading-5 text-muted-foreground">{evidence.support_reason}</div>
              )}
            </div>
          )) : (
            <div className="rounded-md border border-dashed border-gray-300 p-3 text-sm text-muted-foreground">
              这条逻辑没有可展示证据，后端不应把它放入主榜
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function ResearchRadarPanel({ groupId, onTaskCreated }: ResearchRadarPanelProps) {
  const [reportDate, setReportDate] = useState(getTodayText);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [radar, setRadar] = useState<ResearchRadarRun | null>(null);
  const { handleTaskCreateError, notifyTaskLaunch } = useTaskLauncher({ onTaskCreated });

  const loadRadar = useCallback(async () => {
    try {
      setLoading(true);
      const result = await apiClient.getResearchRadar(groupId, reportDate);
      setRadar(result);
    } catch {
      setRadar(null);
    } finally {
      setLoading(false);
    }
  }, [groupId, reportDate]);

  useEffect(() => {
    void loadRadar();
  }, [loadRadar]);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      const response = await apiClient.createResearchRadar(groupId, { date: reportDate, commentsPerTopic: 8 });
      notifyTaskLaunch(response, (taskId) => `研究雷达任务已创建: ${taskId}`);
    } catch (error) {
      handleTaskCreateError(error, '创建研究雷达任务失败');
    } finally {
      setGenerating(false);
    }
  };

  const mainItems = useMemo(
    () => (radar?.logic_items || []).filter((item) => item.tier !== 'weak'),
    [radar]
  );
  const weakItems = useMemo(
    () => (radar?.logic_items || []).filter((item) => item.tier === 'weak'),
    [radar]
  );
  const directions = useMemo(
    () => Array.from(new Set((radar?.logic_items || []).map((item) => item.direction).filter(Boolean))),
    [radar]
  );
  const stocks = useMemo(
    () => Array.from(new Set((radar?.logic_items || []).flatMap((item) => item.stocks.map((stock) => stock.name)).filter(Boolean))),
    [radar]
  );

  return (
    <div className="grid gap-4 p-1 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
      <div className="flex min-w-0 flex-col gap-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Radar className="h-5 w-5" />
              研究雷达
            </CardTitle>
            <CardDescription>
              基于当前星球已入库材料生成盘前研究线索，每条主逻辑必须能追溯证据
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">加载中...</div>
            ) : radar ? (
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xs text-muted-foreground">逻辑</div>
                  <div className="mt-1 text-lg font-semibold">{radar.summary.logic_count ?? radar.logic_items.length}</div>
                </div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xs text-muted-foreground">方向</div>
                  <div className="mt-1 text-lg font-semibold">{radar.summary.direction_count ?? directions.length}</div>
                </div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xs text-muted-foreground">个股</div>
                  <div className="mt-1 text-lg font-semibold">{radar.summary.stock_count ?? stocks.length}</div>
                </div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div className="text-xs text-muted-foreground">日期</div>
                  <div className="mt-1 text-sm font-medium">{radar.report_date}</div>
                </div>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center rounded-md border border-dashed border-gray-300 text-sm text-muted-foreground">
                当前日期还没有研究雷达，请先生成
              </div>
            )}
          </CardContent>
        </Card>

        {mainItems.map((item) => (
          <LogicCard key={item.id ?? `${item.rank}-${item.direction}`} item={item} />
        ))}

        {weakItems.length > 0 && (
          <Card className="border border-gray-200 shadow-none">
            <CardHeader>
              <CardTitle className="text-base">弱线索</CardTitle>
              <CardDescription>证据较少但值得保留观察的早期信号</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {weakItems.map((item) => (
                <LogicCard key={item.id ?? `${item.rank}-${item.direction}`} item={item} />
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      <aside className="xl:sticky xl:top-4">
        <Card className="border border-gray-200 shadow-none">
          <CardHeader>
            <CardTitle className="text-base">雷达操作</CardTitle>
            <CardDescription>选择日期，从已入库材料生成研究雷达</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="research-radar-date">雷达日期</Label>
              <DatePickerButton value={reportDate} onChange={(value) => setReportDate(value || getTodayText())} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => void loadRadar()} disabled={loading}>
                <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
                刷新
              </Button>
              <Button onClick={handleGenerate} disabled={generating}>
                {generating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                生成
              </Button>
            </div>

            <div className="rounded-md border border-gray-200 p-3">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Search className="h-4 w-4" />
                今日方向
              </div>
              <div className="flex flex-wrap gap-2">
                {directions.length > 0 ? directions.map((direction) => (
                  <Badge key={direction} variant="secondary">{direction}</Badge>
                )) : <span className="text-xs text-muted-foreground">暂无方向</span>}
              </div>
            </div>

            <div className="rounded-md border border-gray-200 p-3">
              <div className="mb-2 text-sm font-medium">重点个股</div>
              <div className="flex flex-wrap gap-2">
                {stocks.length > 0 ? stocks.map((stock) => (
                  <Badge key={stock} variant="outline">{stock}</Badge>
                )) : <span className="text-xs text-muted-foreground">暂无个股</span>}
              </div>
            </div>

            <div className="rounded-md bg-gray-50 p-3 text-xs leading-5 text-muted-foreground">
              更新时间：{formatDateTime(radar?.updated_at || '')}
              <br />
              模型：{radar?.model || '未生成'}
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
```

- [ ] **Step 4: Add tab trigger**

In `frontend/src/components/GroupWorkbenchTabList.tsx`, import `Radar`:

```typescript
import { BarChart3, File, HelpCircle, MessageSquare, Radar, Search, Sparkles, TrendingUp } from 'lucide-react';
```

Add the tab after topics:

```typescript
{ value: 'research-radar', label: '研究雷达', Icon: Radar },
```

Change `grid-cols-7` to `grid-cols-8`.

- [ ] **Step 5: Render panel in group page**

In `frontend/src/app/groups/[groupId]/page.tsx`, add dynamic import:

```typescript
const ResearchRadarPanel = dynamic(() => import('@/components/ResearchRadarPanel'), {
  loading: LazyPanelFallback,
  ssr: false,
});
```

Add content before the files tab:

```tsx
<GroupScrollableTabContent value="research-radar">
  <ResearchRadarPanel
    groupId={groupId}
    onTaskCreated={handleTaskCreated}
  />
</GroupScrollableTabContent>
```

- [ ] **Step 6: Run frontend build and commit**

Run:

```powershell
npm --prefix frontend run build
```

Expected: PASS.

Commit:

```powershell
git add frontend/src/lib/api/analysisTypes.ts frontend/src/lib/api/analysis.ts frontend/src/components/ResearchRadarPanel.tsx frontend/src/components/GroupWorkbenchTabList.tsx frontend/src/app/groups/[groupId]/page.tsx
git commit -m "Add research radar workbench tab"
```

Use `git commit --only ...` if unrelated staged files exist.

## Task 7: Focused Verification And Completion Review

**Files:**
- Read-only verification across backend and frontend files touched by this plan.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
uv run python -m unittest tests.test_research_radar_signal tests.test_research_radar_ai tests.test_research_radar_store tests.test_research_radar_workflow tests.test_research_radar_routes_helpers tests.test_postgres_core_schema tests.test_workflow_registry tests.test_app_factory -v
```

Expected: PASS.

- [ ] **Step 2: Run PostgreSQL compatibility debt scan**

Run:

```powershell
uv run python scripts\scan_postgres_compat_debt.py
```

Expected: no SQLite compatibility debt reported.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 4: Review own diff**

Run:

```powershell
git status --short
git diff --stat
git diff -- backend/services/research_radar_signal.py backend/services/research_radar_ai.py backend/services/research_radar_store.py backend/services/research_radar_workflow.py backend/routes/research_radar_routes.py frontend/src/components/ResearchRadarPanel.tsx
```

Expected:

- No unexpected schema DDL outside `backend/storage/postgres_core_schema.py`.
- No crawl invocation from `research_radar_workflow.py`.
- No changes to existing daily stock concept or A-share output shapes.
- No unrelated retention files in any Research Radar commit.

- [ ] **Step 5: Final commit only if verification edits were made**

If Task 7 required any fix, commit only the files changed for that fix:

```powershell
git add -- backend/storage/postgres_core_schema.py backend/services/workflow_registry.py backend/services/research_radar_signal.py backend/services/research_radar_ai.py backend/services/research_radar_store.py backend/services/research_radar_workflow.py backend/routes/research_radar_routes.py backend/main.py tests/test_postgres_core_schema.py tests/test_workflow_registry.py tests/test_research_radar_signal.py tests/test_research_radar_ai.py tests/test_research_radar_store.py tests/test_research_radar_workflow.py tests/test_research_radar_routes_helpers.py tests/test_app_factory.py frontend/src/lib/api/analysisTypes.ts frontend/src/lib/api/analysis.ts frontend/src/components/ResearchRadarPanel.tsx frontend/src/components/GroupWorkbenchTabList.tsx frontend/src/app/groups/[groupId]/page.tsx
git commit -m "Verify research radar MVP"
```

If no fixes were needed, do not create an empty commit.

## Implementation Notes

- Work directly on `main`; do not create a feature branch.
- The current worktree may contain unrelated staged retention changes. Before each commit, inspect `git status --short`; if unrelated files are staged, use the `git commit --only ... -m "..."` commands shown in each task.
- Do not run schema DDL from runtime code.
- Do not crawl or sync topics during Research Radar generation.
- If `OPENAI_API_KEY` is missing, the generation task will fail at the AI wording step through existing AI runtime behavior. That is preferable to silently presenting a fake AI report.
- If there are no current stock extraction rows, persist a completed radar run with zero logic items so the UI can show an empty state for that date.
