"""Feature extraction and candidate model definitions."""

from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from ..data.preprocessing import clean_text

SEED = 42


def make_features():
    """Word 1-2 grams capture phrases like 'stolen card'; char n-grams handle typos and word forms."""
    return FeatureUnion([
        ("word", TfidfVectorizer(preprocessor=clean_text, ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
        ("char", TfidfVectorizer(preprocessor=clean_text, analyzer="char_wb", ngram_range=(2, 5),
                                 sublinear_tf=True, min_df=2)),
    ])


def build_pipeline(clf):
    return Pipeline([("features", make_features()), ("clf", clf)])


# Each candidate: estimator plus the hyperparameter grid searched with cross-validation.
CANDIDATES = {
    "majority_baseline": {
        "label": "Majority baseline",
        "estimator": lambda: DummyClassifier(strategy="most_frequent"),
        "grid": {},
    },
    "complement_nb": {
        "label": "Complement Naive Bayes",
        "estimator": lambda: ComplementNB(),
        "grid": {"clf__alpha": [0.1, 0.3, 1.0]},
    },
    "logistic_regression": {
        "label": "Logistic Regression",
        "estimator": lambda: LogisticRegression(max_iter=3000, class_weight="balanced"),
        "grid": {"clf__C": [10, 20, 40]},
    },
    "linear_svm": {
        "label": "Linear SVM",
        # Calibration turns SVM margins into probabilities for confidence-based routing.
        "estimator": lambda: CalibratedClassifierCV(
            LinearSVC(class_weight="balanced", random_state=SEED), cv=3),
        "grid": {"clf__estimator__C": [0.25, 0.5, 1.0]},
    },
}
