def test_health_ready_and_metrics(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready").json()
    assert r["status"] == "ready" and r["model_version"]
    assert "bankq_http_requests_total" in client.get("/metrics").text


def test_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_classify_creates_a_ticket_with_redacted_text(client):
    r = client.post("/api/v1/classify", json={
        "text": "Someone used my card 4539 1488 0343 6467 without my permission", "channel": "app"})
    assert r.status_code == 200
    d = r.json()
    assert d["category"] == "fraud" and d["priority"] == "urgent"
    assert d["pii_redacted"] == ["CARD"]
    assert d["ticket_ref"].startswith("TKT-")

    t = client.get(f"/api/v1/tickets/{d['ticket_ref']}").json()
    assert "4539" not in t["text"]
    assert t["channel"] == "app" and t["status"] == "open"
    assert [e["type"] for e in t["events"]] == ["created"]


def test_classify_without_ticket(client):
    d = client.post("/api/v1/classify", json={"text": "my card is not working", "create_ticket": False}).json()
    assert d["ticket_ref"] is None


def test_blank_and_oversized_queries_are_rejected(client):
    assert client.post("/api/v1/classify", json={"text": "   "}).status_code == 422
    assert client.post("/api/v1/classify", json={"text": "x" * 2001}).status_code == 422


def test_agent_reroute_is_audited_and_becomes_feedback(client):
    from bankq.db.repository import TicketRepository
    from bankq.db.session import session_scope

    ref = client.post("/api/v1/classify", json={"text": "what is the exchange rate for euros"}).json()["ticket_ref"]
    r = client.patch(f"/api/v1/tickets/{ref}", json={
        "category": "cards", "status": "in_progress", "note": "customer meant card fees", "actor": "asha"})
    t = r.json()
    assert t["category"] == "cards" and t["model_category"] == "payments" and t["rerouted"]
    assert t["department"] == "Card Services"
    assert [e["type"] for e in t["events"]] == ["created", "rerouted", "status", "note"]

    with session_scope() as s:
        assert ("what is the exchange rate for euros", "cards") in TicketRepository(s).feedback_examples()


def test_ticket_list_filters(client):
    client.post("/api/v1/classify", json={"text": "my card was stolen"})
    body = client.get("/api/v1/tickets", params={"department": "Fraud & Security Team", "status": "open"}).json()
    assert body["total"] >= 1
    assert all(i["department"] == "Fraud & Security Team" for i in body["items"])
    assert client.get("/api/v1/tickets/TKT-999999").status_code == 404


def test_batch_and_csv(client):
    r = client.post("/api/v1/classify/batch", json={"texts": ["my card was stolen", "", "apply for a loan"]})
    assert r.status_code == 200
    assert r.json()["summary"]["total"] == 2

    csv_bytes = b"id,text\n1,I forgot my passcode\n2,exchange rate for dollars\n"
    r = client.post("/api/v1/classify/csv", files={"file": ("q.csv", csv_bytes, "text/csv")})
    assert [x["category"] for x in r.json()["results"]] == ["account", "payments"]


def test_batch_size_limit(client, settings):
    settings.max_batch_size = 2
    try:
        r = client.post("/api/v1/classify/batch", json={"texts": ["a b", "c d", "e f"]})
        assert r.status_code == 413
    finally:
        settings.max_batch_size = 1000


def test_api_key_required_when_configured(client, settings):
    settings.api_keys = "secret-1,secret-2"
    assert client.post("/api/v1/classify", json={"text": "card lost"}).status_code == 401
    ok = client.post("/api/v1/classify", json={"text": "card lost"}, headers={"X-API-Key": "secret-2"})
    assert ok.status_code == 200
    assert client.get("/api/v1/tickets").status_code == 401


def test_rate_limit(client, settings):
    from bankq.api.deps import limiter
    limiter.hits.clear()
    settings.rate_limit_per_minute = 3
    codes = [client.post("/api/v1/classify", json={"text": "hi there", "create_ticket": False}).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    limiter.hits.clear()


def test_analytics_and_model_endpoints(client):
    a = client.get("/api/v1/analytics/summary", params={"days": 7}).json()
    assert a["kpis"]["tickets"] >= 1 and len(a["by_day"]) == 7
    card = client.get("/api/v1/model").json()
    assert card["quality_gate"]["passed"]
    assert any(v["production"] for v in client.get("/api/v1/model/versions").json()["versions"])
