"""Prometheus metrics and request middleware (request IDs, access logs, latency)."""

import logging
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from ..logging_setup import request_id_var

log = logging.getLogger("bankq.http")

HTTP_REQUESTS = Counter("bankq_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("bankq_http_request_seconds", "HTTP request latency", ["route"],
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
ROUTED = Counter("bankq_queries_routed_total", "Queries routed", ["category", "priority", "needs_review"])
RULES = Counter("bankq_rules_applied_total", "Business rules applied", ["rule"])
CONFIDENCE = Histogram("bankq_prediction_confidence", "Top category confidence",
                       buckets=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0))
PII = Counter("bankq_pii_redactions_total", "PII items redacted", ["type"])


def record_decision(d):
    ROUTED.labels(d["category"], d["priority"], str(d["needs_review"]).lower()).inc()
    CONFIDENCE.observe(d["confidence"])
    for r in d["rules_applied"]:
        RULES.labels(r["rule"]).inc()
    for p in d["pii_redacted"]:
        PII.labels(p).inc()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            if not path.startswith("/static"):
                HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
                HTTP_LATENCY.labels(path).observe(elapsed)
                if path.startswith("/api"):
                    log.info("request", extra={"method": request.method, "path": path, "status": status,
                                               "ms": round(elapsed * 1000, 1)})
            request_id_var.reset(token)
