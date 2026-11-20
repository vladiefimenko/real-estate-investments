"""Axiom financial engine: deterministic, audited CRE calculations.

AI layers never compute numbers – they call into this package.
"""

ENGINE_VERSION = "1.0.0"

from .assumptions import (  # noqa: E402
    AssumptionError,
    Assumptions,
    ExpenseLine,
    Loan,
    MezzanineLoan,
    PreferredEquity,
    UnitType,
)
from .underwriting import UnderwritingResult, run_underwriting  # noqa: E402

__all__ = [
    "ENGINE_VERSION",
    "AssumptionError",
    "Assumptions",
    "ExpenseLine",
    "Loan",
    "MezzanineLoan",
    "PreferredEquity",
    "UnitType",
    "UnderwritingResult",
    "run_underwriting",
]
