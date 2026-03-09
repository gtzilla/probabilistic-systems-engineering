# methodology-v0.2.pdf

## Page 1

Experimental Methodology v0.2 — Draft

### 1. Purpose

This methodology tests iterative stability under evolving requirements in AI-assisted software modification. It does not ask whether a model can satisfy a requirement once. It asks whether earlier invariants survive later tightening, especially when a later change must hold across more than one mutation surface.

### 2. Comparative Structure

The experiment compares two modification workflows on the same baseline system. Track A — Spec-First For each delta:

### 1. Revise the written contract.

### 2. Derive or modify the implementation to conform.

### 3. Evaluate against the revised contract.

This is the workflow in which written authority evolves explicitly with each iteration. Track B — Code-Only For each delta:

### 1. Describe the requirement change conversationally.

### 2. Modify code directly.

### 3. Do not update the contract artifact.

## Page 2

This is the workflow in which authority does not accumulate in a durable written artifact. At later stages, the only stable written yardstick remains the original contract because prompt-based deltas do not accumulate into an evolving reference. Methodological Note This asymmetry is intentional and under test. The methodology is not trying to equalize documentation practice between the two tracks. It is testing what happens when one workflow carries forward written invariant authority and the other does not.

### 3. Experimental Focus

The methodology retains the earlier same-surface scaffolding, but the primary target is now cross-surface invariant propagation. Earlier work centered the experimental chain on tightening deltas within the same behavioral surface. That remains useful as scaffolding, but it is no longer the methodological center. The primary target is now cross-surface propagation failure.

### 4. Change Topology Classes

The methodology distinguishes two classes of requirement change. 4.1 Same-Surface Change A requirement change that tightens behavior within the surface already under modification. Methodological role:

- establishes the easier comparison class
- separates local tightening from propagated obligation
- confirms that not all tightening produces the same instability profile

4.2 Cross-Surface Change A requirement change whose invariant must hold across more than one mutation surface. Methodological role:

## Page 3

- tests whether the workflow preserves full invariant scope
- exposes prompt-local success masking broader noncompliance
- targets the failure class that proved more structurally important than same-surface tightening alone

This distinction is now the center of the methodology because cross-surface deltas are where incomplete propagation becomes predictable.

### 5. Baseline and Delta Design

The experiment begins from a shared baseline implementation and a shared baseline contract. The baseline must:

- have a working implementation
- have a written contract or equivalent governing artifact for the spec-first track
- be rich enough that a later invariant can plausibly span more than one mutation surface

The delta sequence should include:

### 1. at least one same-surface tightening delta

### 2. at least one cross-surface tightening delta

A useful default sequence remains:

- baseline
- same-surface tightening
- additional same-surface tightening or architectural tightening

## Page 4

- cross-surface tightening

That structure preserves continuity with the earlier scaffold while shifting the center of measurement to the later cross-surface failure class.

### 6. Oracle and Evaluation Rule

The workflow under test is not the oracle. The code-only path cannot be judged by treating its final implementation as proof of what should have been true. That would make the comparison circular. The fact that code-only does not retain an updated contract artifact is part of the workflow being evaluated, not permission for the resulting code to define its own correctness after the fact. Both tracks are therefore evaluated against the same invariant under test for each delta. That invariant may come from business rules, operational obligations, or system-level correctness requirements. It is not derived from whatever final code shape emerges. This matters most for cross-surface changes, because the prompt may name only one affected path while the required invariant applies across several.

### 7. Immediate Mechanism Under Test

The methodology isolates explicit invariant-scope enumeration as the immediate mechanism. A sufficiently explicit prompt can succeed. But conversational prompts naturally scope work to the surfaces they mention, while clause-structured contracts force enumeration of affected mutation surfaces. This is why cross-surface deltas matter methodologically:

- they reveal whether the workflow preserved full scope
- or only the locally named surface

Later prompt-gradient results also matter here: structural invariant propagation was achieved only at near-contract phrasing, and once prompts explicitly named all affected paths, the propagation gap disappeared.

## Page 5

### 8. Measurement Criteria

The methodology retains the earlier measurement structure and adds one explicit cross-surface completion check. 8.1 Regression Count Clauses or invariants satisfied earlier that remain applicable but are violated after a later delta. 8.2 Collateral Drift Scope and dispersion of code changes outside the intended mutation surface. 8.3 Convergence Stability Number of correction iterations required to satisfy all applicable clauses. 8.4 Invariant Preservation Whether earlier guarantees survive later tightening without explicit restatement. 8.5 Diff Locality Whether tightening produces localized change or structural thrash. 8.6 Required-Surface Completion For cross-surface deltas, record:

- which mutation surfaces were required
- which mutation surfaces changed
- which required surfaces remained untouched

This is the main measurement refinement in v0.2.

### 9. Decision-Surface Rule

Instability is judged at the Decision Surface, not at the wording, formatting, or byte surface.

## Page 6

A finding matters only if it can change an externally observable decision or state transition: success/failure, accept/reject, converge/non-converge, create/delete, refusal behavior, or another externally observable state transition. If none change, it is not instability. This rule prevents representation variance, formatting drift, or implementation-shape preference from being misclassified as methodological instability.

### 10. Falsifier Shape

This methodology supports two falsifier families. 10.1 Comparative Falsifier If code-only workflows exhibit invariant preservation, regression behavior, collateral drift, and convergence stability equivalent to spec-first workflows across the same delta sequence, the main thesis weakens. 10.2 Topology Falsifier If cross-surface deltas do not show greater instability than same-surface deltas, or if omitted invariant-scope enumeration does not predict incomplete propagation, the topology-centered claim weakens.

### 11. Reproducibility

The methodology is designed to be replicated across agents, operators, and later systems. Minimum required inputs:

- baseline contract
- baseline implementation
- at least one same-surface delta
- at least one cross-surface delta
- prompts or instructions used in the code-only path
- scoring criteria for regression, collateral drift, convergence, invariant preservation, and required-surface completion

## Page 7

Minimum required outputs:

- code snapshots or commits after each stage
- clause or invariant satisfaction matrix
- diff-locality / collateral-drift notes
- required-surface completion record for cross-surface deltas
- summary comparison between tracks

### 12. What

This Methodology Is Not This methodology is not:

- a coding benchmark
- a model ranking exercise
- a test of raw model intelligence
- a claim that AI cannot code
- a generic software-quality framework for all systems

It is a controlled comparative methodology for testing whether explicit written invariant authority reduces iterative instability, especially at the cross-surface boundary.
