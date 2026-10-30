from pathlib import Path

from app.batch import load_tickets, run_batch
from app.evaluate import (EvalRow, accuracy, compute, confusion, load_rows,
                          serious_errors, to_markdown)
from app.llm.fake import FakeLLM
from app.store import SQLiteTicketStore

DATASET = Path(__file__).parent.parent / "data" / "sample_tickets.jsonl"


def row(exp_cat="bug", exp_urg="medium", cat="bug", llm_urg="medium", final_urg="medium",
        confidence=0.9, rules=None):
    return EvalRow(id="T1", subject="s", expected_category=exp_cat, expected_urgency=exp_urg,
                   category=cat, llm_urgency=llm_urg, final_urgency=final_urg,
                   confidence=confidence, rules_applied=rules or [], needs_human_review=False)


def test_accuracy():
    assert accuracy([("a", "a"), ("a", "b"), ("b", "b"), ("c", "c")]) == 0.75
    assert accuracy([]) == 0.0


def test_confusion_matrix_counts_expected_vs_predicted():
    m = confusion([("bug", "bug"), ("bug", "billing"), ("billing", "billing")], ["bug", "billing"])
    assert m["bug"] == {"bug": 1, "billing": 1}
    assert m["billing"] == {"bug": 0, "billing": 1}


def test_only_high_low_swaps_are_serious():
    assert serious_errors([("high", "low"), ("low", "high"), ("high", "medium"), ("low", "low")]) == 2


def test_rules_fixed_and_broke_are_counted_separately():
    rows = [
        row(exp_urg="high", llm_urg="medium", final_urg="high"),    # rule fixed the LLM
        row(exp_urg="low", llm_urg="low", final_urg="medium"),      # rule broke a correct answer
        row(exp_urg="low", llm_urg="low", final_urg="low"),         # untouched
    ]
    m = compute(rows)
    assert m["rules_changed_urgency"] == 2
    assert m["rules_fixed"] == 1
    assert m["rules_broke"] == 1
    assert round(m["llm_urgency_accuracy"], 2) == 0.67
    assert round(m["final_urgency_accuracy"], 2) == 0.67


def test_confident_vs_unsure_accuracy():
    rows = [row(confidence=0.95), row(cat="other", confidence=0.4)]
    m = compute(rows)
    assert (m["confident_n"], m["confident_accuracy"]) == (1, 1.0)
    assert (m["unsure_n"], m["unsure_accuracy"]) == (1, 0.0)


def test_end_to_end_batch_then_evaluate(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    run_batch(load_tickets(DATASET)[:20], store, FakeLLM(), log=lambda *a: None)

    rows, missing = load_rows(DATASET, store)
    assert len(rows) == 20
    assert len(missing) == 30                        # not triaged yet: reported, not crashed

    m = compute(rows)
    report = to_markdown(m, rows, missing, "fake")
    assert "# Evaluation report" in report
    assert "Category confusion matrix" in report
    assert 0 <= m["category_accuracy"] <= 1