import pytest

from axiom_engine import AssumptionError, MezzanineLoan, run_underwriting
from axiom_engine.assumptions import Assumptions

MEZZ = {"amount": 1_000_000, "interest_rate": 0.11, "origination_fee_pct": 0.01}


def test_mezzanine_loan_flows_through_sources_cash_flow_and_exit(levered_mf):
    base = run_underwriting(levered_mf)
    with_mezz = run_underwriting({**levered_mf, "mezzanine": MEZZ})
    su0, su1 = base.sources_and_uses, with_mezz.sources_and_uses
    assert su1.mezzanine_loan == 1_000_000
    assert su1.loan_fees == pytest.approx(su0.loan_fees + 10_000)
    # Equity shrinks by the mezz amount, net of its fee.
    assert su1.common_equity == pytest.approx(su0.common_equity - 1_000_000 + 10_000)
    assert su1.total_sources == pytest.approx(su1.total_uses)
    y0, y1 = base.annual[0], with_mezz.annual[0]
    assert y1.debt_service == pytest.approx(y0.debt_service + 110_000)  # interest-only
    assert y1.interest == pytest.approx(y0.interest + 110_000)
    assert y1.principal == pytest.approx(y0.principal)
    assert y1.loan_balance == pytest.approx(y0.loan_balance + 1_000_000)
    assert y1.dscr == pytest.approx(y1.noi / y1.debt_service)  # combined DSCR
    ex = with_mezz.exit
    assert ex.mezzanine_payoff == 1_000_000
    assert ex.net_proceeds_to_equity == pytest.approx(base.exit.net_proceeds_to_equity - 1_000_000)
    m = with_mezz.metrics
    assert m.loan_amount == base.metrics.loan_amount  # senior only
    assert m.ltv == pytest.approx((m.loan_amount + 1_000_000) / 10_000_000)  # combined


def test_mezzanine_only_and_senior_covenant_ignores_mezz(simple_mf, levered_mf):
    r = run_underwriting({**simple_mf, "mezzanine": MEZZ})
    assert r.annual[0].debt_service == pytest.approx(110_000)
    assert r.debt_schedule == [] and r.metrics.loan_amount == 0
    assert r.metrics.ltv == pytest.approx(0.1) and r.annual[0].debt_yield is not None
    # The senior lender's DSCR covenant is tested on senior debt service only.
    loan = {**levered_mf["loan"], "min_dscr_covenant": 1.0}
    senior_only = run_underwriting({**levered_mf, "loan": loan})
    stacked = run_underwriting({**levered_mf, "loan": loan, "mezzanine": {"amount": 2_500_000, "interest_rate": 0.12}})
    assert not senior_only.covenant_breaches and not stacked.covenant_breaches
    assert stacked.annual[0].dscr < senior_only.annual[0].dscr


def test_prepayment_penalty_only_before_term(levered_mf):
    loan = {**levered_mf["loan"], "prepayment_penalty_pct": 0.02}
    early = run_underwriting({**levered_mf, "loan": loan})  # 5-year hold, 10-year term
    assert early.exit.prepayment_penalty == pytest.approx(early.exit.loan_payoff * 0.02)
    base = run_underwriting(levered_mf)
    assert early.exit.net_proceeds_to_equity == pytest.approx(base.exit.net_proceeds_to_equity - early.exit.prepayment_penalty)
    at_term = run_underwriting({**levered_mf, "loan": {**loan, "term_years": 5}})
    assert at_term.exit.prepayment_penalty == 0


def test_from_dict_accepts_a_built_mezzanine_object(simple_mf):
    a = Assumptions.from_dict({**simple_mf, "mezzanine": MezzanineLoan(amount=500_000, interest_rate=0.1)})
    assert a.mezzanine.amount == 500_000


@pytest.mark.parametrize("mezz", [
    {"amount": -1, "interest_rate": 0.1},
    {"amount": 1, "interest_rate": 0.6},
    {"amount": 1, "interest_rate": 0.1, "origination_fee_pct": 0.2},
])
def test_invalid_mezzanine(simple_mf, mezz):
    with pytest.raises(AssumptionError):
        run_underwriting({**simple_mf, "mezzanine": mezz})


def test_invalid_prepayment_penalty(levered_mf):
    with pytest.raises(AssumptionError):
        run_underwriting({**levered_mf, "loan": {**levered_mf["loan"], "prepayment_penalty_pct": 0.5}})


def test_too_much_debt_is_rejected(levered_mf):
    with pytest.raises(AssumptionError):
        run_underwriting({**levered_mf, "mezzanine": {"amount": 4_000_000, "interest_rate": 0.1}})
