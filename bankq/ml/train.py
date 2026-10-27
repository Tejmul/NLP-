"""Training job: tune and compare models, evaluate, run the quality gate, and register a new version.

    python -m bankq.ml.train                     # train, and promote if the gate passes
    python -m bankq.ml.train --include-feedback  # also learn from agent corrections
    python -m bankq.ml.train --no-promote        # register only (challenger)
"""

import argparse
import hashlib
import json
import logging
import platform
import time
from datetime import UTC, datetime

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import sklearn
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    top_k_accuracy_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold

from ..config import get_settings
from ..data.loaders import load_dataset
from ..logging_setup import setup_logging
from ..taxonomy import CATEGORIES, CATEGORY_ORDER
from .pipeline import CANDIDATES, SEED, build_pipeline
from .registry import ModelRegistry

log = logging.getLogger("bankq.train")

# A model must clear these on the held-out test set before it can serve traffic.
QUALITY_GATE = {
    "min_macro_f1": 0.93,
    "min_fraud_recall": 0.90,
    "min_intent_accuracy": 0.80,
    "max_regression_vs_production": 0.01,
}

PALETTE = {"payments": "#0F7B6C", "cards": "#2B4FD8", "loans": "#B7791F", "account": "#7A3E9D", "fraud": "#D7263D"}


# ---------- Model selection ----------

def tune_and_compare(X, y, cv):
    """Grid-search each candidate family; return a results table and the fitted searches."""
    results, searches = [], {}
    for key, spec in CANDIDATES.items():
        start = time.time()
        search = GridSearchCV(build_pipeline(spec["estimator"]()), spec["grid"] or {}, cv=cv,
                              scoring="f1_macro", n_jobs=-1, refit=True)
        search.fit(X, y)
        i = search.best_index_
        row = {
            "key": key,
            "model": spec["label"],
            "best_params": {k.split("__")[-1]: v for k, v in search.best_params_.items()},
            "cv_macro_f1": round(float(search.cv_results_["mean_test_score"][i]), 4),
            "cv_macro_f1_std": round(float(search.cv_results_["std_test_score"][i]), 4),
            "configs_tried": len(search.cv_results_["params"]),
            "seconds": round(time.time() - start, 1),
        }
        log.info("model tuned", extra=row)
        results.append(row)
        searches[key] = search
    return results, searches


def evaluate_category(model, X, y):
    pred = model.predict(X)
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=CATEGORY_ORDER, zero_division=0)
    return pred, {
        "accuracy": round(accuracy_score(y, pred), 4),
        "macro_f1": round(f1_score(y, pred, average="macro"), 4),
        "weighted_f1": round(f1_score(y, pred, average="weighted"), 4),
        "labels": CATEGORY_ORDER,
        "confusion_matrix": confusion_matrix(y, pred, labels=CATEGORY_ORDER).tolist(),
        "per_class": {c: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
                          "f1": round(float(f[i]), 4), "support": int(s[i])}
                      for i, c in enumerate(CATEGORY_ORDER)},
    }


def evaluate_intent(model, X, y):
    pred = model.predict(X)
    proba = model.predict_proba(X)
    return {
        "accuracy": round(accuracy_score(y, pred), 4),
        "macro_f1": round(f1_score(y, pred, average="macro"), 4),
        "top3_accuracy": round(top_k_accuracy_score(y, proba, k=3, labels=model.classes_), 4),
        "n_intents": len(model.classes_),
    }


def quality_gate(cat_metrics, intent_metrics, production_card):
    checks = [
        ("macro_f1", cat_metrics["macro_f1"], ">=", QUALITY_GATE["min_macro_f1"]),
        ("fraud_recall", cat_metrics["per_class"]["fraud"]["recall"], ">=", QUALITY_GATE["min_fraud_recall"]),
        ("intent_accuracy", intent_metrics["accuracy"], ">=", QUALITY_GATE["min_intent_accuracy"]),
    ]
    if production_card:
        floor = production_card["metrics"]["category"]["macro_f1"] - QUALITY_GATE["max_regression_vs_production"]
        checks.append(("macro_f1_vs_production", cat_metrics["macro_f1"], ">=", round(floor, 4)))
    rows = [{"check": n, "value": v, "op": op, "threshold": t, "passed": bool(v >= t)} for n, v, op, t in checks]
    return {"passed": all(r["passed"] for r in rows), "checks": rows}


# ---------- Figures ----------

def save_figures(fig_dir, train, test, results, cm, model_label, lr_terms):
    counts = pd.DataFrame({"Train": train["category"].value_counts(), "Test": test["category"].value_counts()})
    ax = counts.reindex(CATEGORY_ORDER).plot.bar(color=["#14213D", "#8FA3B5"], figsize=(8, 4.5), rot=0)
    ax.set_xticklabels([CATEGORIES[c]["label"] for c in CATEGORY_ORDER])
    ax.set_title("Queries per category")
    ax.set_ylabel("Number of queries")
    plt.tight_layout(); plt.savefig(fig_dir / "class_distribution.png", dpi=150); plt.close()

    lengths = train.assign(words=train["text"].str.split().str.len())
    plt.figure(figsize=(8, 4.5))
    sns.boxplot(data=lengths, x="category", y="words", order=CATEGORY_ORDER, hue="category",
                palette=PALETTE, legend=False)
    plt.title("Query length by category (words)"); plt.xlabel("")
    plt.tight_layout(); plt.savefig(fig_dir / "query_length.png", dpi=150); plt.close()

    df = pd.DataFrame(results).set_index("model")[["cv_macro_f1"]]
    ax = df.plot.barh(figsize=(8, 4), color="#14213D", legend=False)
    ax.set_xlim(0, 1); ax.set_title("Cross-validated macro F1 (tuned)")
    plt.tight_layout(); plt.savefig(fig_dir / "model_comparison.png", dpi=150); plt.close()

    labels = [CATEGORIES[c]["label"] for c in CATEGORY_ORDER]
    cm = np.array(cm)
    plt.figure(figsize=(7, 6))
    sns.heatmap(cm / cm.sum(axis=1, keepdims=True), annot=cm, fmt="d", cmap="Blues",
                xticklabels=labels, yticklabels=labels, cbar=False)
    plt.xlabel("Predicted"); plt.ylabel("Actual"); plt.title(f"Confusion matrix - {model_label} (test set)")
    plt.tight_layout(); plt.savefig(fig_dir / "confusion_matrix.png", dpi=150); plt.close()

    fig, axes = plt.subplots(1, len(CATEGORY_ORDER), figsize=(18, 4.5))
    for ax, cls in zip(axes, CATEGORY_ORDER):
        rows = lr_terms[cls][::-1]
        ax.barh([r["term"] for r in rows], [r["weight"] for r in rows], color=PALETTE[cls])
        ax.set_title(CATEGORIES[cls]["label"])
    fig.suptitle("Strongest indicator words per category (Logistic Regression)")
    plt.tight_layout(); plt.savefig(fig_dir / "top_terms.png", dpi=150); plt.close()


def top_terms(pipeline, n=12):
    word_vec = pipeline.named_steps["features"].transformer_list[0][1]
    n_word = len(word_vec.vocabulary_)
    names = word_vec.get_feature_names_out()
    clf = pipeline.named_steps["clf"]
    out = {}
    for i, cls in enumerate(clf.classes_):
        coefs = clf.coef_[i][:n_word]
        idx = np.argsort(coefs)[::-1][:n]
        out[cls] = [{"term": names[j], "weight": round(float(coefs[j]), 3)} for j in idx]
    return out


def data_fingerprint(df):
    h = hashlib.sha256()
    for text, cat in sorted(zip(df["text"], df["category"])):
        h.update(f"{text}\t{cat}\n".encode())
    return h.hexdigest()[:16]


# ---------- Job ----------

def run(include_feedback=False, promote=True):
    started = time.time()
    registry = ModelRegistry()
    prod_version = registry.production_version()
    prod_card = registry.card(prod_version) if prod_version else None

    train, test = load_dataset(include_feedback=include_feedback)
    X_train, y_train = train["text"], train["category"]
    X_test, y_test = test["text"], test["category"]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    # 1. Category model: tune every family, pick by CV (never by test score).
    results, searches = tune_and_compare(X_train, y_train, cv)
    best = max(results, key=lambda r: r["cv_macro_f1"])
    cat_model = searches[best["key"]].best_estimator_
    log.info("selected category model", extra={"model": best["model"], "params": best["best_params"]})

    for r in results:
        pred = searches[r["key"]].best_estimator_.predict(X_test)
        r["test_accuracy"] = round(accuracy_score(y_test, pred), 4)
        r["test_macro_f1"] = round(f1_score(y_test, pred, average="macro"), 4)

    pred, cat_metrics = evaluate_category(cat_model, X_test, y_test)

    # 2. Sub-intent model: same family and settings, trained on rows with a real intent label.
    has_intent = train["source"] != "feedback"
    intent_model = clone(cat_model).fit(X_train[has_intent], train.loc[has_intent, "intent"])
    intent_metrics = evaluate_intent(intent_model, X_test, test["intent"])
    log.info("intent model evaluated", extra=intent_metrics)

    gate = quality_gate(cat_metrics, intent_metrics, prod_card)

    # 3. Register the version with its artifacts and model card.
    version, path = registry.new_version_dir()
    joblib.dump(cat_model, path / "category.joblib")
    joblib.dump(intent_model, path / "intent.joblib")
    lr_terms = top_terms(searches["logistic_regression"].best_estimator_)
    save_figures(path / "figures", train, test, results, cat_metrics["confusion_matrix"], best["model"], lr_terms)
    test.assign(predicted=pred)[pred != y_test][["text", "intent", "category", "predicted"]] \
        .to_csv(path / "misclassified.csv", index=False)
    (path / "classification_report.txt").write_text(
        classification_report(y_test, pred, labels=CATEGORY_ORDER, digits=4))

    card = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "category_model": {"key": best["key"], "label": best["model"], "params": best["best_params"]},
        "intent_model": {"label": best["model"], "n_intents": intent_metrics["n_intents"]},
        "data": {
            "train_rows": len(train),
            "test_rows": len(test),
            "train_counts": train["category"].value_counts().reindex(CATEGORY_ORDER).fillna(0).astype(int).to_dict(),
            "test_counts": test["category"].value_counts().reindex(CATEGORY_ORDER).fillna(0).astype(int).to_dict(),
            "sources": train["source"].value_counts().to_dict(),
            "includes_feedback": include_feedback,
            "fingerprint": data_fingerprint(train),
        },
        "model_selection": {"method": "5-fold stratified CV grid search, scored by macro F1", "candidates": results},
        "metrics": {"category": {**cat_metrics, "misclassified": int((pred != y_test).sum())}, "intent": intent_metrics},
        "quality_gate": {**gate, "thresholds": QUALITY_GATE, "compared_with": prod_version},
        "top_terms": lr_terms,
        "environment": {"python": platform.python_version(), "scikit_learn": sklearn.__version__},
        "intended_use": "Routing English-language retail banking customer messages to a service team. "
                        "Low-confidence predictions go to manual review; it is not a replacement for "
                        "fraud detection on transactions.",
        "limitations": [
            "Loan queries are template-generated; Banking77 contains no loan intents.",
            "English only; trained on short chat-style messages.",
            "One primary category per message; mixed-topic messages expose a secondary category only.",
        ],
        "training_seconds": round(time.time() - started, 1),
    }
    (path / "model_card.json").write_text(json.dumps(card, indent=2))

    print(f"\nRegistered {version}  ({best['model']}, {best['best_params']})")
    print(f"  category: accuracy={cat_metrics['accuracy']} macroF1={cat_metrics['macro_f1']} "
          f"fraudRecall={cat_metrics['per_class']['fraud']['recall']}")
    print(f"  intent:   accuracy={intent_metrics['accuracy']} top3={intent_metrics['top3_accuracy']} "
          f"({intent_metrics['n_intents']} intents)")
    for c in gate["checks"]:
        print(f"  gate {'PASS' if c['passed'] else 'FAIL'}  {c['check']} = {c['value']} (needs {c['op']} {c['threshold']})")

    if promote and gate["passed"]:
        registry.promote(version)
        print(f"Promoted {version} to production.")
    elif promote:
        print("Quality gate failed: production model unchanged.")
    else:
        print(f"Not promoted. To promote: python -m bankq.ml.registry promote {version}")
    return card


def main():
    parser = argparse.ArgumentParser(description="Train, evaluate and register a model version.")
    parser.add_argument("--include-feedback", action="store_true", help="add agent corrections to training data")
    parser.add_argument("--no-promote", action="store_true", help="register without promoting to production")
    args = parser.parse_args()
    s = get_settings()
    setup_logging(s.log_level, json_logs=False)
    card = run(include_feedback=args.include_feedback, promote=not args.no_promote)
    raise SystemExit(0 if card["quality_gate"]["passed"] else 1)


if __name__ == "__main__":
    main()
