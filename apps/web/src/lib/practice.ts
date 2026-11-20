/**
 * Practice verification exercises: each is a source excerpt, a field Axiom proposed and the value it
 * read. Built from the extraction mistakes that most often slip through on real OMs, T12s and rent rolls.
 */
export type Answer = "accept" | "edit" | "reject";

export interface Exercise {
  id: string;
  doc: string;
  field: string;
  /** Source text; the part the AI cited is wrapped in [[double brackets]]. */
  excerpt: string;
  proposed: string;
  /** The corrected value offered by the Edit option (a distractor when Edit is wrong). */
  editTo: string;
  answer: Answer;
  lesson: string;
  explanation: string;
}

export const EXERCISES: Exercise[] = [
  {
    id: "monthly-annual",
    doc: "T12 operating statement",
    field: "Real estate taxes (annual)",
    excerpt: "Real Estate Taxes ........ Monthly [[$21,500]] ........ Annual $258,000",
    proposed: "$21,500",
    editTo: "$258,000",
    answer: "edit",
    lesson: "Monthly vs annual",
    explanation: "The model needs the annual figure. $21,500 is the monthly amount on the same line; the annual total is $258,000. Always check the column header.",
  },
  {
    id: "clean",
    doc: "T12 operating statement",
    field: "Insurance",
    excerpt: "Insurance (T12 Actual) ........ [[$94,300]]",
    proposed: "$94,300",
    editTo: "$9,430",
    answer: "accept",
    lesson: "Matching values",
    explanation: "The value matches the source exactly, the label is right and it's the trailing-12-month actual. Accept it. Not every proposal needs changing.",
  },
  {
    id: "budget-actual",
    doc: "T12 operating statement",
    field: "Repairs & maintenance (T12 actual)",
    excerpt: "Repairs & Maintenance ...... 2024 Actual $142,800 ...... 2025 Budget [[$118,000]]",
    proposed: "$118,000",
    editTo: "$142,800",
    answer: "edit",
    lesson: "Budget vs actual",
    explanation: "Sellers often put a lower budget next to the actual. Underwrite from what was actually spent: $142,800. Using the budget would overstate NOI.",
  },
  {
    id: "occupancy-vacancy",
    doc: "Offering memorandum",
    field: "Vacancy rate",
    excerpt: "The property is currently [[94.0%]] occupied, with strong leasing momentum.",
    proposed: "94.0%",
    editTo: "6.0%",
    answer: "edit",
    lesson: "Occupancy vs vacancy",
    explanation: "94% is occupancy. Vacancy is the opposite: 100% − 94% = 6%. A 94% vacancy would wipe out almost all income.",
  },
  {
    id: "total-line",
    doc: "T12 operating statement",
    field: "Payroll",
    excerpt: "[[Total Operating Expenses]] ........ $1,284,500",
    proposed: "$1,284,500",
    editTo: "$128,450",
    answer: "reject",
    lesson: "Wrong line item",
    explanation: "This is the total of all expenses, not payroll. Payroll isn't on this line at all, so there is nothing to edit it to. Reject it and enter payroll from the right line.",
  },
  {
    id: "buildings-units",
    doc: "Offering memorandum",
    field: "Total units",
    excerpt: "The community comprises [[12]] three-story buildings containing 240 apartment homes.",
    proposed: "12",
    editTo: "240",
    answer: "edit",
    lesson: "Counting the right thing",
    explanation: "12 is the number of buildings. The unit count is 240. Unit counts drive rent, price per unit and expenses per unit, so this matters.",
  },
  {
    id: "loss-to-lease",
    doc: "T12 operating statement",
    field: "Other income",
    excerpt: "Loss to Lease ........ [[($48,200)]]",
    proposed: "$48,200",
    editTo: "-$48,200",
    answer: "reject",
    lesson: "Deductions aren't income",
    explanation: "Brackets mean a negative number, and loss to lease reduces rent: it isn't other income at all. Reject it; it belongs in revenue adjustments, not other income.",
  },
  {
    id: "price",
    doc: "Offering memorandum",
    field: "Asking / purchase price",
    excerpt: "Offered at [[$58,500,000]] ($243,750 per unit)",
    proposed: "$58,500,000",
    editTo: "$243,750",
    answer: "accept",
    lesson: "Matching values",
    explanation: "The asking price is the total, $58.5M. $243,750 is the price per unit, which Axiom calculates for you.",
  },
  {
    id: "proforma",
    doc: "Offering memorandum",
    field: "Historical NOI (T12)",
    excerpt: "In-place NOI: $3,410,000 · Pro forma NOI (Year 1): [[$3,890,000]]",
    proposed: "$3,890,000",
    editTo: "$3,410,000",
    answer: "edit",
    lesson: "Pro forma vs in-place",
    explanation: "Pro forma is the seller's projection. Historical (T12) NOI is what the property earns today: $3,410,000. Mixing them up makes a deal look better than it is.",
  },
];
