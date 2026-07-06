"""QA 输出质量的确定性评估工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import yaml


def normalize_case(case: dict[str, Any]) -> dict[str, Any]:
    """兼容旧 QA 数据格式，并补齐新格式默认值。"""
    normalized = dict(case)
    if "turns" not in normalized and "query" in normalized:
        normalized["turns"] = [normalized["query"]]
    if "query" not in normalized and normalized.get("turns"):
        normalized["query"] = normalized["turns"][-1]
    if "must_include" not in normalized:
        normalized["must_include"] = list(normalized.get("expected_elements", []))
    normalized.setdefault("should_include", [])
    normalized.setdefault("forbidden", [])
    normalized.setdefault("ordered_steps", [])
    normalized.setdefault("technical_checks", [])
    normalized.setdefault("config_checks", [])
    normalized.setdefault("document_standard", {})
    normalized.setdefault("artifact_expectation", {"required": False})
    normalized.setdefault("quality_thresholds", {})
    return normalized


def evaluate_answer_locally(output: str, case: dict[str, Any], *, skill_dir: str | None = None) -> dict[str, Any]:
    """对答案做本地确定性检查。"""
    normalized = normalize_case(case)
    must = _check_terms(output, normalized.get("must_include", []))
    should = _check_terms(output, normalized.get("should_include", []))
    forbidden = _check_forbidden(output, normalized.get("forbidden", []))
    ordered = _check_ordered_steps(output, normalized.get("ordered_steps", []))
    technical = _check_technical_assertions(output, normalized.get("technical_checks", []))
    config = _check_config(output, normalized.get("config_checks", []))
    document = _check_document_standard(output, normalized.get("document_standard", {}))
    hallucination = _check_reference_hallucination(output, skill_dir)
    artifact = _check_artifact_expectation(normalized.get("artifact_expectation", {}))

    components = {
        "must_include": must["score"],
        "should_include": should["score"],
        "forbidden": forbidden["score"],
        "ordered_steps": ordered["score"],
        "technical_checks": technical["score"],
        "config_checks": config["score"],
        "document_standard": document["score"],
        "hallucination_free": hallucination["score"],
        "artifact_standard": artifact["score"],
    }
    active = {key: value for key, value in components.items() if value is not None}
    score = sum(active.values()) / len(active) if active else 1.0

    return {
        "score": round(score, 4),
        "components": components,
        "must_include": must,
        "should_include": should,
        "forbidden": forbidden,
        "ordered_steps": ordered,
        "technical_checks": technical,
        "config_checks": config,
        "document_standard": document,
        "hallucination": hallucination,
        "artifact": artifact,
        "pass": _passes_thresholds(score, components, normalized.get("quality_thresholds", {})),
    }


def _passes_thresholds(score: float, components: dict[str, float | None], thresholds: dict[str, Any]) -> bool:
    min_local = float(thresholds.get("local_score", 0.65))
    if score < min_local:
        return False
    for key, threshold in thresholds.get("components", {}).items():
        value = components.get(key)
        if value is not None and value < float(threshold):
            return False
    return True


def _check_terms(output: str, terms: list[Any]) -> dict[str, Any]:
    """检查关键词/要点命中。支持字符串或 {"any": [...]}。"""
    if not terms:
        return {"hits": 0, "total": 0, "missed": [], "score": None}
    hits = 0
    missed = []
    for item in terms:
        if _term_hit(output, item):
            hits += 1
        else:
            missed.append(item)
    return {"hits": hits, "total": len(terms), "missed": missed, "score": hits / len(terms)}


def _term_hit(output: str, item: Any) -> bool:
    if isinstance(item, dict):
        if "any" in item:
            return any(_contains(output, term) for term in item["any"])
        if "all" in item:
            return all(_contains(output, term) for term in item["all"])
        if "regex" in item:
            return re.search(str(item["regex"]), output, flags=re.I | re.M) is not None
    return _contains(output, str(item))


def _contains(output: str, term: str) -> bool:
    return term.lower() in output.lower()


def _check_forbidden(output: str, forbidden: list[Any]) -> dict[str, Any]:
    if not forbidden:
        return {"violations": [], "score": 1.0}
    violations = []
    for item in forbidden:
        if _term_hit(output, item):
            violations.append(item)
    return {"violations": violations, "score": 0.0 if violations else 1.0}


def _check_ordered_steps(output: str, ordered_steps: list[Any]) -> dict[str, Any]:
    if not ordered_steps:
        return {"matched": [], "missing_or_out_of_order": [], "score": None}

    position = -1
    matched = []
    failed = []
    lower = output.lower()
    for step in ordered_steps:
        terms = step.get("any") if isinstance(step, dict) else [str(step)]
        found = _find_next_position(lower, [str(term).lower() for term in terms], position + 1)
        if found is None:
            failed.append(step)
            continue
        matched.append(step)
        position = found

    return {
        "matched": matched,
        "missing_or_out_of_order": failed,
        "score": len(matched) / len(ordered_steps),
    }


def _find_next_position(text: str, terms: list[str], start: int) -> int | None:
    positions = [text.find(term, start) for term in terms if text.find(term, start) >= 0]
    return min(positions) if positions else None


def _check_technical_assertions(output: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not checks:
        return {"passed": 0, "total": 0, "failed": [], "score": None}
    passed = 0
    failed = []
    for check in checks:
        include_ok = all(_term_hit(output, item) for item in check.get("must_include", []))
        include_any = check.get("must_include_any")
        include_any_ok = True if not include_any else any(_term_hit(output, item) for item in include_any)
        forbid_ok = not _check_forbidden(output, check.get("must_not_include", [])).get("violations")
        regex_ok = all(re.search(pattern, output, flags=re.I | re.M) for pattern in check.get("must_match_regex", []))
        if include_ok and include_any_ok and forbid_ok and regex_ok:
            passed += 1
        else:
            failed.append(check.get("id") or check.get("description") or check)
    return {"passed": passed, "total": len(checks), "failed": failed, "score": passed / len(checks)}


def _check_config(output: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not checks:
        return {"passed": 0, "total": 0, "failed": [], "score": None}
    documents = _extract_yaml_documents(output)
    passed = 0
    failed = []
    for check in checks:
        if check.get("type") == "render_yaml":
            ok, issues = _validate_render_yaml(output, documents, check)
        else:
            ok, issues = False, [f"未知配置检查类型: {check.get('type')}"]
        if ok:
            passed += 1
        else:
            failed.append({"id": check.get("id"), "issues": issues})
    return {"passed": passed, "total": len(checks), "failed": failed, "score": passed / len(checks)}


def _extract_yaml_documents(output: str) -> list[Any]:
    blocks = re.findall(r"```(?:yaml|yml)\s*\n(.*?)```", output, flags=re.I | re.S)
    docs = []
    for block in blocks:
        try:
            docs.append(yaml.safe_load(block))
        except yaml.YAMLError:
            docs.append({"__parse_error__": True})
    return docs


def _validate_render_yaml(output: str, documents: list[Any], check: dict[str, Any]) -> tuple[bool, list[str]]:
    issues = []
    if not documents:
        if check.get("required", True):
            return False, ["未找到 yaml/yml 代码块"]
        return True, []

    candidates = [doc for doc in documents if isinstance(doc, dict) and "services" in doc]
    if not candidates:
        return False, ["未找到包含 services 的 render.yaml"]

    config = candidates[0]
    services = config.get("services")
    if not isinstance(services, list) or not services:
        issues.append("services 必须是非空列表")
    else:
        required_service_fields = check.get("required_service_fields", ["type", "name"])
        for idx, service in enumerate(services):
            if not isinstance(service, dict):
                issues.append(f"services[{idx}] 必须是对象")
                continue
            for field in required_service_fields:
                if field not in service:
                    issues.append(f"services[{idx}] 缺少 {field}")

    for term in check.get("must_include", []):
        if not _contains(output, str(term)):
            issues.append(f"缺少配置要素 {term}")
    for term in check.get("must_not_include", []):
        if _contains(output, str(term)):
            issues.append(f"包含禁止配置内容 {term}")
    return not issues, issues


def _check_document_standard(output: str, standard: dict[str, Any]) -> dict[str, Any]:
    if not standard:
        return {"issues": [], "score": None}
    issues = []
    min_sections = int(standard.get("min_sections", 0))
    if min_sections:
        section_count = len(re.findall(r"^\s*(?:#{1,6}\s+|\d+[.、)]\s+|[-*]\s+)", output, flags=re.M))
        if section_count < min_sections:
            issues.append(f"结构段落数不足: {section_count} < {min_sections}")
    for item in standard.get("required_sections_any", []):
        if not _term_hit(output, {"any": item}):
            issues.append(f"缺少章节: {item}")
    min_chars = int(standard.get("min_chars", 0))
    if min_chars and len(output) < min_chars:
        issues.append(f"输出过短: {len(output)} < {min_chars}")
    return {"issues": issues, "score": 0.0 if issues else 1.0}


def _check_reference_hallucination(output: str, skill_dir: str | None) -> dict[str, Any]:
    if not skill_dir:
        return {"hallucinations": [], "score": 1.0}
    skill_path = Path(skill_dir)
    hallucinations = []
    refs = re.findall(r"(?:scripts|references|assets)/[\w./-]+", output)
    for ref in refs:
        if not (skill_path / ref).exists():
            hallucinations.append(ref)
    return {"hallucinations": hallucinations, "score": 0.0 if hallucinations else 1.0}


def _check_artifact_expectation(expectation: dict[str, Any]) -> dict[str, Any]:
    """当前 QA 主要评文本；产物存在性由专门工具测试覆盖。"""
    if not expectation or not expectation.get("required"):
        return {"issues": [], "score": None}
    return {"issues": ["当前 QA 脚本未接入真实产物生成工具"], "score": 0.0}
