/**
 * Plain-language explanations for the risk screen's flags. Keys match the `factor`
 * values produced by axiom_engine.risk.risk_assessment, and thresholds mirror that
 * module; update both together.
 */
export type RiskGuide = {
  title: string;
  meaning: string;
  threshold: string;
  action: string;
  /** Glossary id for "learn more". */
  term?: string;
};

export const RISK_GUIDE: Record<string, RiskGuide> = {
  dscr: {
    title: "Thin debt coverage",
    meaning: "In at least one year, NOI covers the loan payments by only a small margin, or not at all.",
    threshold: "+15 points if the minimum DSCR is below 1.25x; +30 if it is below 1.0x (NOI does not cover debt service).",
    action: "Check whether the loan is too large for the income. Try a lower loan amount, a longer amortization, or an interest-only period, and re-run.",
    term: "dscr",
  },
  leverage: {
    title: "High leverage",
    meaning: "The loan is a large share of the price, so a small drop in value hurts equity a lot.",
    threshold: "LTV above 70%: 2 points per percentage point above 70%, up to 20.",
    action: "Confirm the lender will actually offer this LTV, and compare returns with a lower-leverage financing structure.",
    term: "ltv",
  },
  cap_compression: {
    title: "Exit cap below going-in cap",
    meaning: "The model assumes buyers will pay more for each dollar of income when you sell than you are paying today.",
    threshold: "+10 points whenever the exit cap rate is lower than the going-in cap rate.",
    action: "Set the exit cap at or above the going-in cap (many underwriters add 25–50 bps) and see how much of the return depended on it.",
    term: "exit-cap",
  },
  rent_growth: {
    title: "Aggressive rent growth",
    meaning: "Projected rent increases are higher than what most markets sustain over time.",
    threshold: "Any year above 4% growth: 5 points per percentage point above 4%, up to 15.",
    action: "Compare with the submarket's recent rent history, or run the conservative scenario to see returns at lower growth.",
    term: "gpr",
  },
  expense_ratio: {
    title: "Expenses look too low",
    meaning: "Operating expenses are well below what similar properties usually spend, which often means costs are missing.",
    threshold: "+10 points if the year-1 expense ratio is more than 10 points below the property-type benchmark.",
    action: "Check the T12 for taxes after sale (reassessment), insurance, management fees and repairs before trusting the NOI.",
    term: "expense-ratio",
  },
  breakeven: {
    title: "Little room for vacancy",
    meaning: "The property needs high occupancy just to pay its expenses and loan, so a few move-outs could mean losses.",
    threshold: "+10 points if breakeven occupancy is above 85%.",
    action: "Look at the market's occupancy history and stress-test vacancy in a scenario.",
    term: "breakeven-occupancy",
  },
  covenants: {
    title: "Projected covenant breach",
    meaning: "In some years the projection falls below a limit set in the loan terms (such as a minimum DSCR), which can let the lender take action.",
    threshold: "+15 points when any covenant set on the active financing structure is breached in the projection.",
    action: "Open the Financing tab to see which covenant and year, then adjust the loan or the business plan.",
    term: "dscr",
  },
  refinance: {
    title: "Loan matures before sale",
    meaning: "The loan comes due before the planned sale, so you would need to refinance, possibly at worse rates.",
    threshold: "+8 points when the loan term is shorter than the hold period.",
    action: "Match the loan term to the hold, or model the refinance explicitly.",
    term: "debt-service",
  },
  returns: {
    title: "Negative or undefined returns",
    meaning: "With these assumptions, equity investors would lose money or the IRR cannot be calculated.",
    threshold: "+20 points if levered IRR is negative or undefined.",
    action: "Review the price, rents and loan terms. If the assumptions are right, this deal may be one to pass on.",
    term: "irr",
  },
};
