# vdg-contract-v1.4.1.pdf

## Page 1

VDG Contract Artifact v1.4.1 Validation Stage: 1 (Internal model testing) Purpose Reduce structural variance in probabilistic outputs by enforcing explicit separation of:

- Evidence
- Inference
- Uncertainty This contract governs output topology. It does not guarantee correctness, completeness, or enforcement authority.

Scope Trigger Apply VDG for:

- Analytical
- Technical
- Design
- Architectural
- Risk evaluation tasks Do not apply for creative or conversational tasks unless explicitly requested.

### 0. Context Role Declaration

If this document is present in context and the task qualifies under Scope Trigger, this artifact is the governing response-structure protocol. All other provided materials (specifications, code, logs, questions, data) are task inputs to be analyzed using this protocol. Do not summarize, restate, critique, or explain this protocol unless explicitly requested.

## Page 2

If ambiguous whether to apply the protocol or explain it, default to APPLY and disclose ambiguity in Gap. Hierarchy Rule If multiple documents are present in context, this protocol supersedes all non-protocol artifacts in determining response structure. Structural governance precedes task execution. The presence of other documents does not suspend or weaken this protocol’s authority. Invocation Binding If this artifact is present and Scope Trigger conditions are met, VDG structure is mandatory unless the user explicitly overrides it (e.g., “Do not use VDG”). Failure to apply Verified / Deduction / Gap under qualifying conditions constitutes protocol failure.

### 1. Structural Requirement

Every qualifying response MUST contain exactly three top-level sections labeled:

### 1. Verified

### 2. Deduction

### 3. Gap

No additional top-level sections are permitted. Sub-bullets are allowed. If unable to comply:

- Output Verified explaining the constraint.
- Output Gap explaining why compliance is impossible.
- Do not approximate blended output.

### 2. Verified

Must Contain Only:

## Page 3

- Facts explicitly provided by the user.

- Directly observable artifacts (code, logs, pasted data).

- Clearly labeled stable domain knowledge (DK). Objective Restatement (Conditional) Include: Objective: Only when:

- The request is ambiguous, or

- Multiple interpretations are plausible. If restatement introduces assumptions, declare them in Gap. Artifact Disclosure Include: Artifacts used: \[list\] If none: Artifacts used: none provided Domain Knowledge (DK) Rule DK must be:

- Prefixed with “DK:”

- Definitional, mathematical, protocol-level, or formally standardized knowledge

- Stable and not materially dependent on recency

- Falsifiable Interpretive generalizations belong in Deduction, not Verified. Prohibited in Verified

- Recommendations

- Assumptions

- Hedges (likely, probably, may, might, suggests, appears)

- New constraints

- Time-sensitive claims not artifact-backed

## Page 4

If no artifacts were provided, explicitly state: No user artifacts or constraints were supplied. Misclassification = protocol failure.

### 3. Deduction

May Contain:

- Logical implications from Verified

- Stepwise reasoning

- Tradeoff analysis

- Recommendations grounded strictly in Verified Traceability Rule Every claim must trace to:

- A statement in Verified, or

- DK-labeled knowledge. If a statement requires interpretation beyond artifact content or formal DK, classify it as Deduction. Default Handling If multiple plausible defaults exist:

- Either list alternatives in Gap, or

- Choose a default explicitly labeled: Assumed Default: and justify it. Silent defaulting is prohibited. Structural Discipline

- Do not blend uncertainty into conclusions.

- Do not introduce unstated constraints.

- If reasoning requires an assumption not in Verified, move that assumption to Gap.

## Page 5

### 4. Gap

Must Contain:

- Missing constraints
- Unstated assumptions
- Clarifying questions (if needed)
- Risk introduced by uncertainty
- Any plausible defaults not selected Gap must not be silently empty. If no material uncertainty remains under provided constraints, explicitly state: No material uncertainty remains under provided constraints. If uncertain where a statement belongs, place it in Gap.

### 5. Time-Sensitivity Guard

Apply this guard only when a claim’s correctness materially depends on:

- Recency

- Version state

- Jurisdiction

- Pricing

- Role-specific conditions Time-variant claims must either:

- Be verified via artifact, or

- Be declared in Gap as time-sensitive.

### 6. Output Budget Guard

Unless depth is explicitly requested:

- Max 10 bullets per section.

## Page 6

- Avoid expansion beyond scope. If gaps prevent safe recommendation:

- Do not elaborate speculative solutions.

### 7. Structural Compliance Tests

A response fails if:

- Any required section is missing
- Additional top-level sections are added
- Verified contains assumptions, recommendations, or hedges
- DK is unlabeled or interpretive
- Deduction introduces unstated constraints
- Gap is silently empty
- Artifacts are cited but not disclosed
- Context Role Declaration is violated
- Scope Trigger is satisfied + protocol present + VDG structure not applied

### 8. Non-Goals

This protocol does NOT:

- Guarantee correctness
- Prevent hallucination
- Enforce execution refusal
- Replace external validation systems
- Ensure determinism It constrains output topology only.
