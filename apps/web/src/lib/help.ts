/**
 * Contextual help shown by the "?" button in the top bar. Matched against the current
 * route; the first matching entry wins, so more specific patterns come first.
 */
export type HelpTopic = {
  title: string;
  summary: string;
  steps: string[];
  /** Glossary ids worth knowing on this page. */
  terms?: string[];
};

const DEAL = "^/deals/[^/]+";

export const HELP: { pattern: RegExp; topic: HelpTopic }[] = [
  {
    pattern: new RegExp(`${DEAL}/documents/[^/]+`),
    topic: {
      title: "Reviewing extracted values",
      summary: "Each value Axiom found in the document is shown next to the page or cells it came from. Nothing enters the model until you decide.",
      steps: [
        "Click a field to highlight where it came from in the document.",
        "Accept it if it matches, edit it if it's slightly off, or reject it if it's wrong.",
        "Keyboard: j / k move between fields, a accepts, r rejects.",
        "Values marked 'unverified citation' couldn't be matched to the text: check those carefully.",
        "When you're done, go back to Documents and apply the verified data to the base case.",
      ],
      terms: ["verification", "om", "t12", "rent-roll"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/documents`),
    topic: {
      title: "Documents",
      summary: "Upload the deal's paperwork. Axiom reads it and proposes values, which you verify before they're used.",
      steps: [
        "Drag in an offering memorandum (OM), T12 or rent roll: PDF or Excel.",
        "Wait for the status to show it's been extracted, then click Review.",
        "Accept, edit or reject each proposed value.",
        "Click 'Apply verified data to base case' to update the model with what you verified.",
      ],
      terms: ["om", "t12", "rent-roll", "verification"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/underwriting`),
    topic: {
      title: "Underwriting",
      summary: "The full set of assumptions behind the base case, with results that recalculate as you type.",
      steps: [
        "Work through the sections: acquisition, revenue, operating expenses, exit and financing.",
        "Results update live as a preview; nothing is stored until you click Save.",
        "Yellow flags mark aggressive assumptions (for example rent growth above 8% or an exit cap below 3.5%).",
        "Open Model to see the year-by-year cash flow.",
      ],
      terms: ["noi", "vacancy", "expense-ratio", "exit-cap", "dscr"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/scenarios`),
    topic: {
      title: "Scenarios & Risk",
      summary: "Test how the deal holds up when assumptions change.",
      steps: [
        "Click 'Create default cases' to add Conservative and Optimistic versions of the base case.",
        "Read 'What changed, and why it matters' to see which assumptions move returns the most.",
        "Use the sensitivity table to vary two assumptions at once.",
        "Run a Monte Carlo simulation to see a range of outcomes instead of one number.",
      ],
      terms: ["scenario", "sensitivity", "monte-carlo", "irr"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/financing`),
    topic: {
      title: "Financing",
      summary: "Compare loan structures side by side and choose the one the model uses.",
      steps: [
        "Add a structure: loan amount or LTV, rate, amortization and any interest-only period.",
        "Optionally add preferred equity and covenants such as a minimum DSCR.",
        "Compare returns, coverage and leverage across structures, then activate one.",
      ],
      terms: ["ltv", "ltc", "dscr", "amortization", "preferred-equity"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/valuation`),
    topic: {
      title: "Valuation",
      summary: "Estimate what the property is worth using more than one approach, then reconcile them.",
      steps: [
        "Enter valuation inputs such as comparable sales and replacement cost.",
        "Compare the value from each approach: direct capitalization, DCF, sales comparison and cost.",
        "Set weights in the reconciliation to arrive at a single value.",
      ],
      terms: ["cap-rate", "noi"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/development`),
    topic: {
      title: "Development (beta)",
      summary: "A basic feasibility check for building or major redevelopment.",
      steps: ["Enter land, construction and soft costs, the timeline and the stabilized income.", "Check the yield on cost against market cap rates."],
      terms: ["cap-rate", "ltc"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/analyst`),
    topic: {
      title: "AI Analyst",
      summary: "Ask questions about this deal. Answers are built on the engine's numbers; the analyst explains, it doesn't calculate.",
      steps: [
        "Start with a suggested question, or ask your own (e.g. 'Why is DSCR low in year 1?').",
        "Every number in an answer comes from the stored underwriting results.",
        "Without an AI key, answers come from rule-based templates.",
      ],
      terms: ["dscr", "irr"],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/reports`),
    topic: {
      title: "Reports",
      summary: "Export the deal to share with your team, lenders or an investment committee.",
      steps: [
        "Excel model: the full model with live formulas you can audit.",
        "One-page summary: key returns, sources & uses and risks.",
        "IC memo: a multi-page memo with scenarios, sensitivity and verified document data.",
        "Demo deals are watermarked 'For Demonstration Purposes Only'.",
      ],
    },
  },
  {
    pattern: new RegExp(`${DEAL}/activity`),
    topic: {
      title: "Activity",
      summary: "Everything that happened on this deal, who did it and when: uploads, verifications, assumption changes and exports.",
      steps: ["Use it to see why a number changed, or to show reviewers how the model was built."],
    },
  },
  {
    pattern: new RegExp(`${DEAL}$`),
    topic: {
      title: "Deal overview",
      summary: "The headline numbers for this deal's base case, its cash flow and its risk screen.",
      steps: [
        "Hover any ⓘ icon to learn what a number means.",
        "Click a flag in the Risk screen to see why it was raised and what to check.",
        "Change the Stage as the deal moves through your pipeline.",
        "Typical order: Documents → Underwriting → Scenarios & Risk → Reports.",
      ],
      terms: ["noi", "cap-rate", "irr", "equity-multiple", "dscr", "risk-score"],
    },
  },
  {
    pattern: /^\/deals$/,
    topic: {
      title: "Deals",
      summary: "Every deal in your workspace, with base-case returns from the latest calculation.",
      steps: [
        "Click New deal to start one with the guided setup.",
        "Search by name or market, and filter by type or stage.",
        "Switch to Pipeline view to see deals by stage.",
      ],
      terms: ["pipeline"],
    },
  },
  {
    pattern: /^\/dashboard/,
    topic: {
      title: "Investment Dashboard",
      summary: "Your whole pipeline at a glance: volume by stage, exposure by type and state, alerts and recent activity.",
      steps: [
        "Follow the Getting Started checklist if you're new.",
        "Filter by property type or stage at the top.",
        "Alerts list deals whose risk screen or covenants need attention.",
      ],
      terms: ["pipeline", "aum", "cap-rate", "irr"],
    },
  },
  {
    pattern: /^\/compare/,
    topic: {
      title: "Compare deals",
      summary: "Put several deals side by side on the same metrics.",
      steps: ["Pick the deals to compare.", "Read across rows to see which deal leads on each metric."],
      terms: ["irr", "equity-multiple", "dscr", "cap-rate"],
    },
  },
  {
    pattern: /^\/glossary/,
    topic: {
      title: "Glossary",
      summary: "Definitions of every number Axiom shows, with formulas and rules of thumb.",
      steps: ["Search by name or abbreviation, such as NOI, DSCR or T12."],
    },
  },
  {
    pattern: /^\/settings/,
    topic: {
      title: "Settings",
      summary: "Manage your workspace: members and roles, features, billing and the audit log.",
      steps: [
        "Invite teammates and give them a role: Owner, Admin, Analyst or Viewer.",
        "Viewers can read everything but can't change deals.",
      ],
    },
  },
];

export function helpFor(pathname: string): HelpTopic | null {
  return HELP.find((h) => h.pattern.test(pathname))?.topic ?? null;
}
