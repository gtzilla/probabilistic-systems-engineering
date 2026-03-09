# Probabilistic Systems Engineering

**Engineering discipline for systems where identical inputs do not guarantee identical outputs.**

When interacting with AI agents and generative models, outputs are sampled from probability distributions. Small context changes shift behavior. Identical prompts do not guarantee identical reasoning paths.

This repository documents experimental methods for applying engineering rigor to probabilistic substrates.

---

## Start Here

### 🔬 Contract-Centered Iterative Stability (v4.7.2)

*Empirical research paper*

Identifies a stability boundary in iterative AI-assisted development.

Across five structured executions spanning two LLM families:

- Same-surface changes remained stable.
- Cross-surface invariants failed to propagate unless their full scope was explicitly enumerated.

Core mechanism:

> When a requirement spans multiple mutation surfaces and only one surface is named in a prompt, only that surface should be expected to change.

---

## Supporting Artifacts

### Thesis & Experimental Methodology (v3.0.1)

Defines the contract-first evaluation loop used in the stability experiments.

Explains:

- Contract-first inversion
- Independent derivation
- Clause-level evaluation
- Divergence localization
- Iterative refinement

---

### Convergence Contract v2.6.3

The clause-structured operational contract used as the stable yardstick in the stability experiment.

Demonstrates:

- Explicit authority semantics
- Deletion safety gates
- Atomic convergence rules
- Clause-level evaluability

---

## Context Injection Research Program

A bounded document set focused on authority externalization, iterative stability, reproducible evaluation, and replication in AI-assisted development.

Core documents:

1. Canonical Glossary
2. Research Thesis
3. Experimental Methodology
4. Replication
5. Roadmap

Recommended reading order:

1. Research Thesis
2. Canonical Glossary
3. Experimental Methodology
4. Replication
5. Roadmap

Bundle location:

`papers/context-injection-research-program/`

These documents are intended to be read together as one research bundle inside the broader Probabilistic Systems Engineering repository.

---

## Foundational Work

### Verified / Deduction / Gap (VDG) v1.4.1

A response-partitioning protocol that reduces variance by separating:

- **Verified** — Evidence from artifacts and stable domain facts
- **Deduction** — Logical implications of verified statements
- **Gap** — Missing constraints and uncertainty

The model still samples from a distribution, but the shape of that distribution becomes constrained and inspectable.

---

### Contract-Centered Engineering (v2.16)

Explores how engineering topology changes when implementation becomes inexpensive and specification precision becomes scarce.

Introduces a 7-step loop:

1. Contract-first inversion
2. Adversarial hardening
3. Independent derivation
4. Clause-level evaluation
5. Divergence localization
6. Clause refinement
7. Re-sampling and convergence measurement

---

## Program Scope

This repository explores three related problems:

1. **Variance Reduction**  
   How do we constrain reasoning distributions without eliminating stochasticity?

2. **Authority Under Collapsed Implementation Cost**  
   What happens when generating alternative implementations becomes trivial?

3. **Iterative Stability**  
   Do invariants survive sequential tightening under conversational mutation?

---

## What This Is Not

- Not tooling or a framework
- Not determinism
- Not AI philosophy
- Not benchmark performance comparison

This is experimental engineering work.

---

## Reading Order

If new:

1. Contract-Centered Iterative Stability
2. Thesis & Methodology
3. Convergence Contract v2.6.3
4. VDG
5. Contract-Centered Engineering

---

## Status

- Iterative Stability: Mechanism replicated across multiple runs
- VDG: Validation Stage 1
- Contract-Centered Engineering: Empirical demonstration published
- All work: Experimental and evolving

---

## Markdown

Files in `markdown/` are created automatically from parent PDFs. This feature is experimental. Converted documents are not checked for errors or omissions. Please refer to the PDF as the authoritative document.

---

## Author

Gregory Tomlinson  
Lead Engineer  
LinkedIn: https://www.linkedin.com/in/gregorytomlinson/

---

## License

CC BY 4.0