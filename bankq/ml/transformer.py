"""TASK 1 (yours): a fine-tuned transformer challenger model. See TASKS.md #1.

Goal: fine-tune DistilBERT (or similar) on the same data and register it in the
model registry, so it can compete with the TF-IDF model through the same quality
gate. The serving code only needs `predict_proba(list[str]) -> np.ndarray` and
`classes_`, which is the scikit-learn interface the Predictor already uses.
"""

import numpy as np


class TransformerClassifier:
    """Wraps a Hugging Face sequence classifier behind the scikit-learn interface."""

    def __init__(self, model_name: str = "distilbert-base-uncased", max_length: int = 64):
        self.model_name = model_name
        self.max_length = max_length
        self.classes_: np.ndarray | None = None

    def fit(self, texts, labels):
        # TODO: tokenise with AutoTokenizer, fine-tune AutoModelForSequenceClassification
        # for 2-3 epochs (lr 5e-5, batch 32), and keep self.classes_ = np.array(sorted(set(labels))).
        raise NotImplementedError("TASKS.md #1: fine-tune the transformer here")

    def predict_proba(self, texts) -> np.ndarray:
        # TODO: batch-tokenise, run the model in eval mode with torch.no_grad(), softmax the logits.
        raise NotImplementedError("TASKS.md #1")

    def predict(self, texts):
        return self.classes_[self.predict_proba(texts).argmax(axis=1)]
