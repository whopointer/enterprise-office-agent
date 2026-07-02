"""Activation 阶段：skill 匹配与红线校验。"""

from __future__ import annotations

from typing import Any
import logging
import re

from .models import MatchResult, NoSkillMatched, RedLineRule, RedLineViolation, SkillDefinition, SkillIndex
from .utils import extract_match_terms, keyword_matches_query, normalize_string_list, term_matches_query

logger = logging.getLogger(__name__)


class SkillActivator:
    """Activation 阶段：根据 query 匹配 skill，并执行红线校验。"""

    def __init__(self, index: SkillIndex, *, min_confidence: float = 0.2):
        self.index = index
        self.min_confidence = min_confidence

    def activate(
        self,
        user_query: str,
        *,
        fields: dict[str, Any] | None = None,
    ) -> MatchResult | NoSkillMatched | RedLineViolation:
        """匹配最合适的 skill，若命中红线则拒绝激活。"""
        fields = fields or {}
        scored = [self._score_skill(skill, user_query) for skill in self.index.list_skills()]
        scored = [item for item in scored if item[0] >= self.min_confidence]
        if not scored:
            return NoSkillMatched()

        scored.sort(key=lambda item: item[0], reverse=True)
        confidence, skill, keywords, patterns = scored[0]
        violations = self._check_red_lines(skill, fields)
        if violations:
            reason = "；".join(rule.message for rule in violations)
            return RedLineViolation(
                skill=skill,
                violated_rules=tuple(violations),
                reason=reason,
                confidence=confidence,
            )

        return MatchResult(
            skill=skill,
            confidence=confidence,
            redline_pass=True,
            reason="匹配成功，红线校验通过",
            matched_keywords=tuple(keywords),
            matched_patterns=tuple(patterns),
        )

    def _score_skill(self, skill: SkillDefinition, user_query: str) -> tuple[float, SkillDefinition, list[str], list[str]]:
        """基于关键词、正则和描述做轻量匹配评分。"""
        query = user_query.lower()
        query_terms = extract_match_terms(user_query)
        keywords = normalize_string_list(skill.triggers.get("keywords"))
        patterns = normalize_string_list(skill.triggers.get("patterns"))

        matched_keywords = [keyword for keyword in keywords if keyword_matches_query(keyword, query, query_terms)]
        matched_patterns = []
        for pattern in patterns:
            try:
                if re.search(pattern, user_query, re.IGNORECASE):
                    matched_patterns.append(pattern)
            except re.error:
                logger.warning("忽略非法正则 pattern: %s", pattern)

        description_terms = extract_match_terms(skill.description)
        description_hits = sum(1 for term in description_terms if term_matches_query(term, query_terms))
        name_hit = 1 if keyword_matches_query(skill.name, query, query_terms) else 0

        score = 0.0
        score += min(0.6, len(matched_keywords) * 0.2)
        score += min(0.3, len(matched_patterns) * 0.3)
        score += min(0.2, description_hits * 0.05)
        score += 0.2 * name_hit

        return min(1.0, score), skill, matched_keywords, matched_patterns

    def _check_red_lines(self, skill: SkillDefinition, fields: dict[str, Any]) -> list[RedLineRule]:
        """检查必填字段是否满足红线规则。"""
        violations: list[RedLineRule] = []
        for rule in skill.red_lines:
            value = fields.get(rule.field)
            if value is None or value == "" or value == [] or value == {}:
                violations.append(rule)
        return violations
