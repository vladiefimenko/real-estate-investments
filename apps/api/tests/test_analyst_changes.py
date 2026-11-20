"""The analyst explains what changed between document versions and recent assumption edits."""

from conftest import register
from test_documents_reports import upload
from test_novice_tools import _ask

from app.services import ai

T12_MAY = b"Line Item,Total\nReal Estate Taxes,250000\nInsurance,90000\nUtilities,40000\n"
T12_JUNE = b"Line Item,Total\nReal Estate Taxes,262500\nInsurance,90000\nPayroll,120000\n"


def test_rule_based_answer_lists_document_and_assumption_changes(owner, prop):
    pid = prop["id"]
    none_yet = _ask(owner, pid, "What changed between the latest document versions?", learning=False)
    assert "nothing to compare yet" in none_yet
    upload(owner, pid, "t12-may.csv", T12_MAY, "text/csv", "t12")
    upload(owner, pid, "t12-june.csv", T12_JUNE, "text/csv", "t12")
    sc = next(s for s in owner.get(f"/api/properties/{pid}/scenarios").json() if s["is_base"])
    owner.patch(f"/api/scenarios/{sc['id']}", json={"assumptions": {**sc["assumptions"], "vacancy_rate": 0.07}})
    text = _ask(owner, pid, "What changed in the new T12?", learning=False)
    assert "T12 operating statement: what changed" in text
    assert "t12-may.csv" in text and "t12-june.csv" in text
    assert "Real estate taxes: $250,000 → $262,500 (+$12,500, +5.0%)" in text
    assert "Payroll: new, $120,000" in text and "Utilities: no longer in the newer version" in text
    assert "Recent assumption changes" in text and "vacancy rate" in text and "7.00%" in text


def test_ai_context_includes_changes(owner, prop, monkeypatch):
    captured = {}

    def fake_stream(context, history, question, learning=False, preferences=None):
        captured["context"] = context
        yield "ok"

    monkeypatch.setattr(ai, "ai_available", lambda: True)
    monkeypatch.setattr(ai, "stream_analyst", fake_stream)
    monkeypatch.setattr(ai, "model_name", lambda: "test-model")
    pid = prop["id"]
    upload(owner, pid, "a.csv", T12_MAY, "text/csv", "t12")
    upload(owner, pid, "b.csv", T12_JUNE, "text/csv", "t12")
    _ask(owner, pid, "Summarize", learning=False)
    dc = captured["context"]["document_changes"]
    assert len(dc) == 1 and dc[0]["counts"]["changed"] >= 1
    assert "recent_assumption_changes" in captured["context"]


def test_changes_are_tenant_scoped(client, owner, prop):
    upload(owner, prop["id"], "a.csv", T12_MAY, "text/csv", "t12")
    upload(owner, prop["id"], "b.csv", T12_JUNE, "text/csv", "t12")
    other = register(client)
    pid2 = other.post("/api/properties", json={"name": "Elsewhere", "property_type": "multifamily",
                                               "purchase_price": 5_000_000, "units": 40}).json()["id"]
    assert "nothing to compare yet" in _ask(other, pid2, "What changed?", learning=False)
