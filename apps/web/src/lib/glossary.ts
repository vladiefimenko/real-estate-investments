/**
 * Plain-English definitions of the metrics and terms used across Axiom.
 *
 * Shown in metric tooltips and on the /glossary page. Ranges are rules of thumb for
 * orientation only: they vary by market, property type and point in the cycle, and the
 * engine never uses them in calculations.
 */

export type GlossaryCategory = "Income" | "Valuation" | "Returns" | "Debt" | "Risk & analysis" | "Documents & workflow";

export type GlossaryEntry = {
  id: string;
  term: string;
  /** Other names people use, matched by search. */
  aka?: string[];
  category: GlossaryCategory;
  /** One or two sentences a newly licensed agent can follow. */
  definition: string;
  formula?: string;
  /** Rule-of-thumb guidance, not a rule. */
  typical?: string;
  /** Why it matters when reviewing a deal. */
  why?: string;
};

export const GLOSSARY: GlossaryEntry[] = [
  {
    id: "gpr",
    term: "Gross potential rent",
    aka: ["GPR", "potential gross income"],
    category: "Income",
    definition: "The rent the property would collect in a year if every unit were leased at market or contract rent and every tenant paid.",
    formula: "Sum of (rent per unit × 12) for all units",
    why: "It is the starting point of the income statement; every loss and expense is taken from it.",
  },
  {
    id: "vacancy",
    term: "Vacancy & credit loss",
    aka: ["economic vacancy", "bad debt"],
    category: "Income",
    definition: "Income lost to empty units (vacancy) and to tenants who do not pay (credit loss), usually entered as a percentage of gross potential rent.",
    typical: "Stabilized multifamily often uses about 5–8% combined; check the submarket's actual occupancy.",
    why: "Underwriting too little vacancy is one of the most common ways a deal looks better than it is.",
  },
  {
    id: "egi",
    term: "Effective gross income",
    aka: ["EGI"],
    category: "Income",
    definition: "What the property actually expects to collect: gross potential rent, minus vacancy and credit loss, plus other income such as parking or fees.",
    formula: "GPR − vacancy − credit loss + other income",
  },
  {
    id: "opex",
    term: "Operating expenses",
    aka: ["opex"],
    category: "Income",
    definition: "The yearly costs of running the property: taxes, insurance, utilities, repairs, management, payroll. They exclude loan payments and capital improvements.",
  },
  {
    id: "expense-ratio",
    term: "Expense ratio",
    category: "Income",
    definition: "Operating expenses as a share of effective gross income.",
    formula: "Operating expenses ÷ EGI",
    typical:
      "Owner-paid expenses are high for multifamily and office (often 40–50%) and low for net-leased industrial or retail, where tenants reimburse most costs.",
    why: "A ratio far below similar properties usually means expenses are missing from the seller's numbers. Axiom's risk screen flags it.",
  },
  {
    id: "noi",
    term: "Net operating income",
    aka: ["NOI"],
    category: "Income",
    definition: "The property's yearly profit from operations, before any loan payments, income taxes or capital spending.",
    formula: "EGI − operating expenses",
    why: "NOI drives value (through the cap rate) and the size of loan a lender will give (through DSCR).",
  },
  {
    id: "cap-rate",
    term: "Going-in cap rate",
    aka: ["capitalization rate", "cap rate", "entry cap"],
    category: "Valuation",
    definition: "The unlevered yield on the purchase price in the first year: what you would earn each year if you paid all cash.",
    formula: "Year-1 NOI ÷ purchase price",
    typical: "Lower cap rates mean higher prices relative to income. Ranges differ widely by market, property type and interest rates.",
    why: "Comparing a deal's cap rate with recent sales of similar properties tells you whether the price is in line with the market.",
  },
  {
    id: "exit-cap",
    term: "Exit cap rate",
    aka: ["terminal cap rate", "reversion cap rate"],
    category: "Valuation",
    definition: "The cap rate assumed when the property is sold at the end of the hold. It sets the sale price: next year's NOI divided by the exit cap.",
    formula: "Sale price = forward NOI ÷ exit cap rate",
    typical: "Conservative underwriting sets the exit cap at or above the going-in cap, often by 25–50 basis points.",
    why: "A lower exit cap than going-in cap assumes the market will pay more for the same income later. That is cap compression, and the risk screen flags it.",
  },
  {
    id: "cap-compression",
    term: "Cap rate compression",
    category: "Valuation",
    definition: "When cap rates fall, so buyers pay more for each dollar of NOI. Underwriting it means betting that values rise even if income does not.",
  },
  {
    id: "irr",
    term: "Internal rate of return",
    aka: ["IRR", "levered IRR", "unlevered IRR"],
    category: "Returns",
    definition:
      "The yearly return that accounts for when every dollar goes in and comes out. Levered IRR uses the investor's equity cash flows after loan payments; unlevered IRR assumes an all-cash purchase.",
    formula: "The discount rate at which the net present value of the cash flows equals zero",
    typical: "Targets depend on strategy: core deals accept lower IRRs than value-add or opportunistic deals.",
    why: "It is the most common single number for comparing deals, but it should be read together with the equity multiple.",
  },
  {
    id: "equity-multiple",
    term: "Equity multiple",
    aka: ["EM", "MOIC"],
    category: "Returns",
    definition: "How many dollars come back for every dollar of equity invested, over the whole hold. It ignores timing.",
    formula: "Total equity distributions ÷ total equity invested",
    typical: "2.0x means you doubled your money. Compare it with the hold period: 2.0x in 5 years is far better than in 10.",
  },
  {
    id: "cash-on-cash",
    term: "Cash-on-cash return",
    aka: ["CoC", "cash yield"],
    category: "Returns",
    definition: "The yearly cash an investor receives after loan payments, as a share of the equity they put in.",
    formula: "Annual cash flow to equity ÷ equity invested",
    why: "Shows how much income the deal pays while you own it, separately from the profit at sale.",
  },
  {
    id: "npv",
    term: "Net present value",
    aka: ["NPV"],
    category: "Returns",
    definition:
      "Today's value of all future cash flows, discounted at your required return, minus what you invest. Positive means the deal beats your required return.",
    formula: "Σ cash flowₜ ÷ (1 + discount rate)ᵗ − initial equity",
  },
  {
    id: "dscr",
    term: "Debt service coverage ratio",
    aka: ["DSCR", "coverage"],
    category: "Debt",
    definition: "How many times NOI covers the yearly loan payments. Below 1.0x the property does not earn enough to pay its loan.",
    formula: "NOI ÷ annual debt service",
    typical: "Lenders commonly require about 1.20–1.35x. Axiom's risk screen flags a minimum below 1.25x.",
    why: "It is usually the limit on how much a lender will lend, and a breach can trigger loan covenants.",
  },
  {
    id: "debt-service",
    term: "Debt service",
    category: "Debt",
    definition: "Total yearly loan payments: interest plus any principal repayment (amortization).",
  },
  {
    id: "ltv",
    term: "Loan-to-value",
    aka: ["LTV"],
    category: "Debt",
    definition: "The loan amount as a share of the property's value or price.",
    formula: "Loan amount ÷ property value",
    typical: "Commercial loans are often 55–75% LTV. Axiom's risk screen flags LTV above 70%.",
    why: "More leverage raises returns when things go well and losses when they do not.",
  },
  {
    id: "ltc",
    term: "Loan-to-cost",
    aka: ["LTC"],
    category: "Debt",
    definition: "The loan as a share of total project cost: price plus closing costs and planned improvements. Common for value-add and construction loans.",
    formula: "Loan amount ÷ total project cost",
  },
  {
    id: "amortization",
    term: "Amortization & interest-only",
    aka: ["IO", "interest only"],
    category: "Debt",
    definition:
      "Amortization is paying down the loan principal over time. An interest-only (IO) period means payments cover interest alone, which lowers early payments but leaves the full balance due later.",
  },
  {
    id: "preferred-equity",
    term: "Preferred equity",
    aka: ["pref", "preferred return"],
    category: "Debt",
    definition:
      "Money invested between the loan and the common equity. It is paid a set return before common investors receive anything, and is repaid ahead of them.",
  },
  {
    id: "waterfall",
    term: "Waterfall (profit split)",
    aka: ["distribution waterfall", "LP/GP split"],
    category: "Returns",
    definition:
      "The order in which a deal's cash is paid out to the investors (LP) and the sponsor (GP). Investors first get their money back plus a preferred return; above that, the sponsor earns a bigger share as a reward for performance.",
    typical: "A common structure: 8% preferred return, then 80/20 to a 12% investor IRR, then 70/30.",
  },
  {
    id: "preferred-return",
    term: "Preferred return",
    aka: ["pref", "hurdle"],
    category: "Returns",
    definition:
      "The return investors must receive, on top of getting their money back, before the sponsor earns any extra share of the profits.",
    typical: "Often 6% to 10% a year, commonly 8%.",
  },
  {
    id: "promote",
    term: "Promote",
    aka: ["carried interest", "carry"],
    category: "Returns",
    definition:
      "The extra share of profits the sponsor (GP) earns above its share of the money it invested, once investors have cleared the agreed return hurdles.",
  },
  {
    id: "qsr",
    term: "QSR (quick-service restaurant)",
    aka: ["fast food", "restaurant pad", "single-tenant net lease"],
    category: "Income",
    definition:
      "A fast-food or fast-casual restaurant building, such as a Taco Bell or Chick-fil-A, usually leased to one tenant on a long net lease. Value depends mostly on the tenant's credit, the guarantor (corporate is stronger than a franchisee), the years left on the lease and the rent increases.",
    typical: "Underwritten on the lease's base rent with a small reserve; cap rates depend heavily on the brand and guarantor.",
  },
  {
    id: "nnn",
    term: "Triple-net (NNN) lease",
    aka: ["NNN", "net lease", "absolute net"],
    category: "Income",
    definition:
      "A lease where the tenant pays the property's taxes, insurance and maintenance on top of rent, so the owner's income is close to the rent itself. 'Absolute NNN' means the tenant also covers roof and structure.",
  },
  {
    id: "breakeven-occupancy",
    term: "Breakeven occupancy",
    category: "Risk & analysis",
    definition: "The occupancy at which income just covers operating expenses, loan payments and any preferred equity distributions.",
    formula: "(Operating expenses + debt service + preferred distributions) ÷ (gross potential rent + other income)",
    typical: "Lower is safer. Axiom flags breakeven above 85% as a thin cushion.",
  },
  {
    id: "risk-score",
    term: "Risk screen score",
    category: "Risk & analysis",
    definition:
      "Axiom's 0–100 screening score: the sum of transparent penalty points for things like thin debt coverage, high leverage, aggressive rent growth or cap compression. Under 20 is low, 20–44 moderate, 45+ high.",
    why: "It is a checklist to start the conversation, not a credit rating. Click any flag to see what triggered it.",
  },
  {
    id: "sensitivity",
    term: "Sensitivity analysis",
    category: "Risk & analysis",
    definition: "Re-running the model while changing one or two assumptions across a range, to see which inputs move the returns most.",
  },
  {
    id: "monte-carlo",
    term: "Monte Carlo simulation",
    category: "Risk & analysis",
    definition:
      "Running the model thousands of times with assumptions drawn at random from ranges you set, to see the spread of possible outcomes instead of a single answer.",
  },
  {
    id: "scenario",
    term: "Scenario",
    aka: ["base case", "downside", "upside"],
    category: "Risk & analysis",
    definition:
      "A complete set of assumptions for a deal. The base case is your best estimate; conservative and optimistic cases show what happens if things go worse or better.",
  },
  {
    id: "aum",
    term: "Assets under management",
    aka: ["AUM"],
    category: "Documents & workflow",
    definition: "On the dashboard: the total purchase price of deals marked Closed in this workspace.",
  },
  {
    id: "pipeline",
    term: "Pipeline & deal stages",
    category: "Documents & workflow",
    definition:
      "Deals move through stages: Sourcing (found), Underwriting (being analysed), Investment Committee (IC, awaiting approval), then Closed (bought) or Passed (declined).",
  },
  {
    id: "om",
    term: "Offering memorandum",
    aka: ["OM"],
    category: "Documents & workflow",
    definition: "The marketing package a seller's broker prepares: property description, photos, financial summary and the asking price. Treat its numbers as the seller's view.",
  },
  {
    id: "t12",
    term: "T12 (trailing twelve months)",
    aka: ["T-12", "operating statement"],
    category: "Documents & workflow",
    definition: "The property's actual income and expenses for the last 12 months. It shows what the property really earned, not what the OM projects.",
  },
  {
    id: "rent-roll",
    term: "Rent roll",
    category: "Documents & workflow",
    definition: "A list of every unit or tenant with its rent, lease dates and status. It backs up the income in the T12 and OM.",
  },
  {
    id: "verification",
    term: "Verification",
    category: "Documents & workflow",
    definition:
      "In Axiom, values extracted from documents are only proposals. A person must accept, edit or reject each one; only verified values can be applied to a scenario, and every decision is logged.",
  },
];

export const GLOSSARY_BY_ID: Record<string, GlossaryEntry> = Object.fromEntries(GLOSSARY.map((e) => [e.id, e]));

export const GLOSSARY_CATEGORIES: GlossaryCategory[] = [
  "Income",
  "Valuation",
  "Returns",
  "Debt",
  "Risk & analysis",
  "Documents & workflow",
];

export function searchGlossary(query: string): GlossaryEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return GLOSSARY;
  return GLOSSARY.filter((e) =>
    [e.term, e.definition, e.formula ?? "", ...(e.aka ?? [])].some((s) => s.toLowerCase().includes(q)),
  );
}
