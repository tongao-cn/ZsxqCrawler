from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = PROJECT_ROOT / "frontend" / "src" / "components" / "stockConceptTaxonomy.json"


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower()


@lru_cache(maxsize=1)
def load_stock_concept_taxonomy() -> Dict[str, Any]:
    with TAXONOMY_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    concept_groups = data.get("conceptGroups") if isinstance(data, dict) else []
    signal_tag_groups = data.get("signalTagGroups") if isinstance(data, dict) else []
    return {
        "conceptGroups": concept_groups if isinstance(concept_groups, list) else [],
        "signalTagGroups": signal_tag_groups if isinstance(signal_tag_groups, list) else [],
    }


@lru_cache(maxsize=1)
def get_taxonomy_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    taxonomy = load_stock_concept_taxonomy()
    concept_map: Dict[str, str] = {}
    for group in taxonomy["conceptGroups"]:
        if not isinstance(group, dict):
            continue
        concept = str(group.get("concept") or "").strip()
        if not concept:
            continue
        concept_map[_normalize_key(concept)] = concept
        aliases = group.get("aliases") if isinstance(group.get("aliases"), list) else []
        for alias in aliases:
            alias_text = str(alias or "").strip()
            if alias_text:
                concept_map[_normalize_key(alias_text)] = concept

    signal_map: Dict[str, str] = {}
    for group in taxonomy["signalTagGroups"]:
        if not isinstance(group, dict):
            continue
        tag = str(group.get("tag") or "").strip()
        if not tag:
            continue
        signal_map[_normalize_key(tag)] = tag
        aliases = group.get("aliases") if isinstance(group.get("aliases"), list) else []
        for alias in aliases:
            alias_text = str(alias or "").strip()
            if alias_text:
                signal_map[_normalize_key(alias_text)] = tag

    return concept_map, signal_map


def normalize_stock_concept_term(value: str) -> Tuple[str, str]:
    term = str(value or "").strip()
    if not term:
        return "empty", ""
    concept_map, signal_map = get_taxonomy_maps()
    key = _normalize_key(term)
    if key in signal_map:
        return "signal", signal_map[key]
    if key in concept_map:
        return "concept", concept_map[key]
    return "unmapped", term


def normalize_stock_concept_terms(raw_terms: List[str]) -> Dict[str, List[str]]:
    industry_concepts: List[str] = []
    signal_tags: List[str] = []
    raw_terms_out: List[str] = []
    unmapped_terms: List[str] = []

    def append_unique(target: List[str], item: str) -> None:
        if item and item not in target:
            target.append(item)

    for value in raw_terms:
        term = str(value or "").strip()
        if not term:
            continue
        append_unique(raw_terms_out, term)
        class_name, normalized = normalize_stock_concept_term(term)
        if class_name == "signal":
            append_unique(signal_tags, normalized)
        elif class_name == "concept":
            append_unique(industry_concepts, normalized)
        elif class_name == "unmapped":
            append_unique(industry_concepts, normalized)
            append_unique(unmapped_terms, normalized)

    return {
        "industry_concepts": industry_concepts,
        "signal_tags": signal_tags,
        "raw_terms": raw_terms_out,
        "unmapped_terms": unmapped_terms,
    }


def normalize_concept_name(value: str) -> str:
    class_name, normalized = normalize_stock_concept_term(value)
    return normalized if class_name == "concept" else str(value or "").strip()


def normalize_signal_tag_name(value: str) -> Optional[str]:
    class_name, normalized = normalize_stock_concept_term(value)
    return normalized if class_name == "signal" else None

