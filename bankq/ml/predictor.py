"""Serve predictions from the production model in the registry."""

import re

import numpy as np

from ..taxonomy import INTENT_TO_CATEGORY, intent_label
from .registry import ModelRegistry

_TOKEN = re.compile(r"\S+")


class Predictor:
    def __init__(self, registry: ModelRegistry | None = None, version: str | None = None):
        bundle = (registry or ModelRegistry()).load(version)
        self.version = bundle["version"]
        self.card = bundle["card"]
        self.category_model = bundle["category"]
        self.intent_model = bundle["intent"]
        self.categories = list(self.category_model.classes_)
        self.intents = list(self.intent_model.classes_)

    @property
    def model_name(self):
        return self.card["category_model"]["label"]

    def _explain(self, text, class_idx, base_prob):
        """Occlusion: drop each word in turn and measure how much the predicted class's probability falls."""
        words = [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(text)]
        if len(words) < 2:
            return []
        variants = [text[:s] + text[e:] for _, s, e in words]
        probs = self.category_model.predict_proba(variants)[:, class_idx]
        out = [{"word": w, "start": s, "end": e, "impact": round(float(base_prob - p), 4)}
               for (w, s, e), p in zip(words, probs) if base_prob - p > 0.03]
        return sorted(out, key=lambda w: -w["impact"])[:4]

    def _intents(self, probs, category, k=3):
        """Top-k sub-intents, preferring those that belong to the predicted category."""
        order = np.argsort(probs)[::-1]
        ranked = [(self.intents[i], float(probs[i])) for i in order]
        in_cat = [r for r in ranked if INTENT_TO_CATEGORY.get(r[0]) == category]
        top = (in_cat or ranked)[:k]
        return [{"intent": i, "label": intent_label(i), "confidence": round(p, 4)} for i, p in top]

    def intents_for(self, text, category, k=3):
        """Top sub-intents within a given category (used when a rule overrides the model's category)."""
        return self._intents(self.intent_model.predict_proba([text])[0], category, k)

    def predict(self, text, explain=True):
        cat_probs = self.category_model.predict_proba([text])[0]
        idx = int(np.argmax(cat_probs))
        category = self.categories[idx]
        intents = self._intents(self.intent_model.predict_proba([text])[0], category)
        return {
            "category": category,
            "confidence": float(cat_probs[idx]),
            "probabilities": {c: round(float(p), 4) for c, p in zip(self.categories, cat_probs)},
            "intents": intents,
            "keywords": self._explain(text, idx, float(cat_probs[idx])) if explain else [],
        }

    def predict_many(self, texts):
        cat = self.category_model.predict_proba(texts)
        intent = self.intent_model.predict_proba(texts)
        out = []
        for cp, ip in zip(cat, intent):
            idx = int(np.argmax(cp))
            category = self.categories[idx]
            out.append({
                "category": category,
                "confidence": float(cp[idx]),
                "probabilities": {c: round(float(p), 4) for c, p in zip(self.categories, cp)},
                "intents": self._intents(ip, category, k=1),
                "keywords": [],
            })
        return out
