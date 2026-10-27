"""Load and apply the business rules in configs/routing_rules.yaml."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..taxonomy import PRIORITY_RANK


def _matcher(keywords):
    if not keywords:
        return None
    parts = sorted((re.escape(k.lower()) for k in keywords), key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(parts) + r")(?!\w)")


def _normalise(text):
    return text.lower().replace("’", "'")


@dataclass
class PriorityOverride:
    name: str
    priority: str
    pattern: re.Pattern


@dataclass
class RuleSet:
    review_threshold: float = 0.6
    secondary_threshold: float = 0.2
    fraud_enabled: bool = True
    fraud_min_probability: float = 0.1
    fraud_pattern: re.Pattern | None = None
    fraud_strong_pattern: re.Pattern | None = None
    overrides: list[PriorityOverride] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> "RuleSet":
        cfg = yaml.safe_load(Path(path).read_text()) or {}
        fraud = cfg.get("fraud_escalation", {})
        overrides = []
        for o in cfg.get("priority_overrides", []):
            if o["priority"] not in PRIORITY_RANK:
                raise ValueError(f"Rule {o['name']!r} has unknown priority {o['priority']!r}")
            overrides.append(PriorityOverride(o["name"], o["priority"], _matcher(o["keywords"])))
        return cls(
            review_threshold=float(cfg.get("review_threshold", 0.6)),
            secondary_threshold=float(cfg.get("secondary_threshold", 0.2)),
            fraud_enabled=bool(fraud.get("enabled", True)),
            fraud_min_probability=float(fraud.get("min_fraud_probability", 0.1)),
            fraud_pattern=_matcher(fraud.get("keywords", [])),
            fraud_strong_pattern=_matcher(fraud.get("strong_keywords", [])),
            overrides=overrides,
        )

    def fraud_keyword(self, text):
        """Return (keyword, is_strong) for the first fraud phrase found, or None."""
        if not self.fraud_enabled:
            return None
        norm = _normalise(text)
        for pattern, strong in ((self.fraud_strong_pattern, True), (self.fraud_pattern, False)):
            m = pattern.search(norm) if pattern else None
            if m:
                return m.group(1), strong
        return None

    def priority_override(self, text):
        """Return (priority, rule_name, keyword) for the most urgent matching override, or None."""
        norm = _normalise(text)
        hits = []
        for o in self.overrides:
            m = o.pattern.search(norm) if o.pattern else None
            if m:
                hits.append((PRIORITY_RANK[o.priority], o.priority, o.name, m.group(1)))
        if not hits:
            return None
        _, priority, name, kw = min(hits)
        return priority, name, kw
