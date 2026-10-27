"""A file-based model registry: versioned artifacts, model cards and a production pointer.

Layout:
    models/registry/
        production.json              {"version": "...", "promoted_at": "..."}
        v20261027-153000/
            category.joblib          category classifier pipeline
            intent.joblib            sub-intent classifier pipeline
            model_card.json          data, parameters, metrics and quality gate result
            figures/*.png
            misclassified.csv

Run `python -m bankq.ml.registry list` or `... promote <version>`.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib

from ..config import get_settings


class ModelRegistry:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or get_settings().registry_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def _pointer(self):
        return self.root / "production.json"

    def new_version_dir(self) -> tuple[str, Path]:
        version = datetime.now(UTC).strftime("v%Y%m%d-%H%M%S")
        path = self.root / version
        (path / "figures").mkdir(parents=True)
        return version, path

    def path(self, version: str) -> Path:
        path = self.root / version
        if not (path / "model_card.json").exists():
            raise FileNotFoundError(f"Model version {version!r} not found in {self.root}")
        return path

    def card(self, version: str) -> dict:
        return json.loads((self.path(version) / "model_card.json").read_text())

    def versions(self) -> list[dict]:
        prod = self.production_version()
        out = []
        for d in sorted(self.root.glob("v*"), reverse=True):
            if (d / "model_card.json").exists():
                card = json.loads((d / "model_card.json").read_text())
                out.append({
                    "version": card["version"],
                    "created_at": card["created_at"],
                    "model": card["category_model"]["label"],
                    "macro_f1": card["metrics"]["category"]["macro_f1"],
                    "fraud_recall": card["metrics"]["category"]["per_class"]["fraud"]["recall"],
                    "intent_accuracy": card["metrics"]["intent"]["accuracy"],
                    "gate_passed": card["quality_gate"]["passed"],
                    "production": card["version"] == prod,
                })
        return out

    def production_version(self) -> str | None:
        if not self._pointer.exists():
            return None
        return json.loads(self._pointer.read_text())["version"]

    def promote(self, version: str):
        card = self.card(version)
        if not card["quality_gate"]["passed"]:
            raise ValueError(f"{version} failed its quality gate and cannot be promoted.")
        self._pointer.write_text(json.dumps(
            {"version": version, "promoted_at": datetime.now(UTC).isoformat(timespec="seconds")}, indent=2))

    def load(self, version: str | None = None) -> dict:
        version = version or self.production_version()
        if not version:
            raise FileNotFoundError("No production model. Train one with: python -m bankq.ml.train")
        path = self.path(version)
        return {
            "version": version,
            "category": joblib.load(path / "category.joblib"),
            "intent": joblib.load(path / "intent.joblib"),
            "card": self.card(version),
        }


def main():
    parser = argparse.ArgumentParser(description="Manage model versions.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List model versions")
    promote = sub.add_parser("promote", help="Make a version the production model")
    promote.add_argument("version")
    args = parser.parse_args()

    reg = ModelRegistry()
    if args.cmd == "list":
        rows = reg.versions()
        if not rows:
            print("No models yet. Run: python -m bankq.ml.train")
        for r in rows:
            flag = "* production" if r["production"] else ("" if r["gate_passed"] else "  gate failed")
            print(f"{r['version']}  {r['model']:<22} macroF1={r['macro_f1']:.4f} "
                  f"fraudRecall={r['fraud_recall']:.4f} intentAcc={r['intent_accuracy']:.4f} {flag}")
    elif args.cmd == "promote":
        reg.promote(args.version)
        print(f"Promoted {args.version}. Restart the API or call POST /api/v1/admin/reload-model.")


if __name__ == "__main__":
    main()
