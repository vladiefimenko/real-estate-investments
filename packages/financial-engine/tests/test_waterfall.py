import pytest

from axiom_engine import AssumptionError
from axiom_engine.tvm import irr
from axiom_engine.waterfall import run_waterfall

TIERS = [{"hurdle": 0.12, "gp_share": 0.20}, {"hurdle": None, "gp_share": 0.30}]


def test_low_returns_are_split_pro_rata():
    flows = [-1000, 50, 50, 1000]  # deal IRR 5%, below the 8% pref
    w = run_waterfall(flows, 0.9, 0.08, TIERS)
    assert w["lp"]["distributed"] == pytest.approx(0.9 * 1100)
    assert w["gp"]["distributed"] == pytest.approx(0.1 * 1100)
    assert w["gp"]["promote"] == pytest.approx(0)
    assert w["lp"]["irr"] == pytest.approx(irr(flows)) == pytest.approx(w["deal_irr"])
    assert w["tiers"][1]["lp"] == w["tiers"][2]["lp"] == 0


def test_hurdles_are_met_exactly_and_promote_flows_to_gp():
    flows = [-1000, 80, 80, 1600]
    w = run_waterfall(flows, 0.9, 0.08, TIERS)
    total = w["lp"]["distributed"] + w["gp"]["distributed"]
    assert total == pytest.approx(1760)  # nothing lost or created
    assert w["gp"]["promote"] > 0
    assert w["lp"]["irr"] < w["deal_irr"] < w["gp"]["irr"]
    assert w["lp"]["irr"] > 0.12  # cleared both hurdles, then the residual split applied
    # Tier 1 paid exactly the LP's capital plus an 8% return: LP flows through tier 1 alone give an 8% IRR.
    t1 = [-900] + [y["by_tier"][0] * 0.9 for y in w["years"]]
    assert irr(t1) == pytest.approx(0.08, abs=1e-9)
    t2 = [-900] + [y["by_tier"][0] * 0.9 + y["by_tier"][1] * 0.8 for y in w["years"]]
    assert irr(t2) == pytest.approx(0.12, abs=1e-9)
    assert w["tiers"][2]["gp"] == pytest.approx(w["tiers"][2]["lp"] * 0.3 / 0.7)


def test_capital_calls_are_funded_pro_rata_and_raise_the_hurdle():
    flows = [-1000, -100, 0, 1500]
    w = run_waterfall(flows, 0.8, 0.08, [{"hurdle": None, "gp_share": 0.4}])
    assert w["lp"]["contributed"] == pytest.approx(880)
    assert w["gp"]["contributed"] == pytest.approx(220)
    assert w["years"][0]["lp"] == pytest.approx(-80)
    assert w["years"][1]["by_tier"] == [0.0, 0.0]  # nothing to distribute
    assert w["lp"]["distributed"] + w["gp"]["distributed"] == pytest.approx(1500)


@pytest.mark.parametrize("flows,lp,pref,tiers", [
    ([1000, 50], 0.9, 0.08, TIERS),
    ([-1000], 0.9, 0.08, TIERS),
    ([-1000, 1100], 1.0, 0.08, TIERS),
    ([-1000, 1100], 0.9, 0.6, TIERS),
    ([-1000, 1100], 0.9, 0.08, []),
    ([-1000, 1100], 0.9, 0.08, [{"hurdle": 0.12, "gp_share": 1.0}, {"hurdle": None, "gp_share": 0.3}]),
    ([-1000, 1100], 0.9, 0.08, [{"hurdle": 0.06, "gp_share": 0.2}, {"hurdle": None, "gp_share": 0.3}]),
    ([-1000, 1100], 0.9, 0.08, [{"hurdle": 0.12, "gp_share": 0.2}, {"hurdle": 0.15, "gp_share": 0.3}]),
    ([-1000, 1100], 0.9, 0.08, [{"hurdle": None, "gp_share": "x"}]),
])
def test_invalid_inputs(flows, lp, pref, tiers):
    with pytest.raises(AssumptionError):
        run_waterfall(flows, lp, pref, tiers)
