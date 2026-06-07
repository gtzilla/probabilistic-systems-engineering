# Contract-Centered Engineering v2.17

## Implementation Cost and the Shift in Engineering Topology

---

For most of modern software engineering, implementation cost shaped practice.

Writing a production-grade system required sustained effort: design, implementation, review, integration, testing, deployment, and iteration. Producing even a single complete implementation demanded coordination across roles. Producing multiple independent implementations of the same system was rarely practical outside regulated or safety-critical domains.

Under those constraints, engineering converged around a single artifact. The codebase was not only the system; it functioned as its authority. Tests were written against it. Documentation was derived from it. Disagreements were resolved by it. Rewrites were avoided because they were destabilizing and expensive.

That arrangement was economically rational.

When implementation is costly, authority concentrates in the implementation because replacing it is prohibitive.

Generative systems alter that condition.

Independent implementations can now be produced rapidly at negligible marginal cost. Alternative interpretations of the same operational description can be generated, compared, discarded, and regenerated without the coordination overhead that previously constrained such experimentation.

When implementation cost collapses, engineering topology can change.

Authority no longer needs to reside in a particular implementation. A contract-centered topology becomes viable: a clause-structured operational contract defines system behavior; independent implementations are derived from it and evaluated against it. Implementations become interchangeable samples rather than singular authorities.

Scarcity relocates.

Implementation effort is no longer the dominant constraint. Specification precision is.

Invariants must be explicit. Authority boundaries must be defined. Scope constraints must be unambiguous. Deletion semantics must be articulated. Abort conditions must be encoded deliberately. These cannot be inferred reliably from vague intention. They must be specified.

The collapse of implementation cost does not eliminate discipline. It increases the leverage of specification.

Engineering shifts from defending a single artifact to stabilizing contracts that survive independent derivation.

---

## **Relationship to Prior Work**

This work does not introduce contracts as a concept. It depends directly on the long-established tradition of contract-based specification, including Design by Contract (Meyer), formal specification practices, contract programming, and property-based testing traditions.

If invariants and explicit behavioral guarantees did not meaningfully constrain implementation, the method described in this paper would not function. The ability to evaluate independent derivations clause-by-clause presupposes that contracts are real constraints, not rhetorical artifacts.

Traditional Design by Contract embeds preconditions, postconditions, and invariants within a single implementation. Formal methods extend this tradition through mathematical specification and proof. Property-based testing evaluates a given implementation against generalized behavioral properties.

All of these approaches assume a primary implementation artifact that must be verified, tested, or proven.

The distinction here is economic rather than conceptual.

When independent implementations are expensive, contracts constrain a system. When independent implementations are inexpensive and repeatable, contracts can instead stabilize authority across multiple derivations.

The contribution of this work is not the invention of contracts, but the identification of a topology shift: collapsed implementation cost allows contracts to function as the stable artifact while implementations are sampled, compared, and refined against them.

This approach presumes the validity of contract-based specification. It explores what becomes possible once implementation is no longer the scarce resource.

---

## **The Contract-First Loop**

A contract-centered topology requires a disciplined method. Reduced implementation cost does not reduce rigor; it changes where rigor applies.

The following seven-step loop specifies, derives, evaluates, and refines systems under conditions where independent implementation is inexpensive.

This is not a benchmark procedure. It is not a model ranking exercise. It is a method for stabilizing specifications through controlled independent derivation.

### **1\. Contract-First Inversion**

The traditional artifact order is inverted.

Instead of exploratory discussion producing code, exploratory discussion produces a clause-structured operational contract.

The contract defines operational semantics explicitly: identity rules, authority relationships, scope boundaries, deletion behavior, abort conditions, output guarantees, and invariant preservation requirements.

No implementation is written at this stage.

The contract is treated as the primary engineering artifact.

### **2\. Adversarial Hardening**

The drafted contract is not assumed correct.

Each clause is examined for interpretive slack, undefined terms, implicit assumptions, boundary ambiguity, and edge-case instability.

Ambiguity is treated as a defect.

Hardening proceeds in deliberate rounds. The objective is not theoretical completeness but reduction of foreseeable divergence under independent derivation.

### **3\. Independent Derivation**

The hardened contract is used to generate multiple independent implementations.

Independence is enforced. There is no shared memory across runs. There is no iterative correction between implementations. One derivation does not influence another.

Implementations may be generated by different AI systems, different configurations of the same system, human engineers, or external vendors.

Each implementation is a sample induced by the contract.

No implementation is authoritative.

### **4\. Clause-Level Evaluation**

The contract is decomposed into discrete evaluable clauses.

Clauses are categorized by role — safety-critical invariants (MUST), behavioral expectations (SHOULD), and structural requirements.

Each implementation is evaluated against each clause independently. Adherence is recorded explicitly.

Evaluation is contract-driven. The question is not stylistic preference but clause satisfaction.

The output is a clause-level adherence matrix.

### **5\. Divergence Localization**

Where deviations occur, they are traced to specific clauses.

Failures are categorized — authority substitution, scope expansion or contraction, invariant omission, deletion logic drift, schema variance, abort condition failure.

Patterns across implementations are analyzed.

The objective is to determine whether divergence originates from specification ambiguity or from independent misinterpretation of a clearly defined clause.

### **6\. Clause Refinement**

Only clauses associated with observed divergence are modified.

Refinement clarifies boundary semantics, converts implicit expectations into explicit invariants, tightens conditional language, and reduces interpretive flexibility.

Each modification is versioned and traceable to observed divergence.

The contract evolves in response to empirical evidence.

### **7\. Re-Sampling and Convergence Measurement**

The revised contract is used to generate new independent implementations.

Clause-level evaluation is repeated.

Convergence is measured as elimination of safety-critical failures, reduction in cross-implementation disagreement, and stabilization of defined behavior across independent derivations.

Convergence does not imply identical code. It implies behavioral stability under independent sampling.

---

## **Comparative Implementation Capability**

The collapse of implementation cost makes comparative derivation practical.

Under prior constraints, producing multiple independent implementations required justification. Teams invested in a single artifact and iterated on it.

With generative systems, a single hardened contract can produce multiple independent implementations at negligible cost. These implementations may differ internally in structure or strategy, but they share a common origin.

This enables structured comparison.

Multiple implementations can be evaluated against the same clause structure. Adherence can be measured explicitly. Divergence can be categorized. Patterns can be observed.

This is not a leaderboard.

The purpose is not to determine which generative system is superior. The purpose is to expose instability in the specification and assess behavioral adherence under independent derivation.

When implementations are inexpensive, they are replaceable.

The contract remains stable while implementations are sampled, evaluated, discarded, or selected.

---

## **Contract as Cross-Functional Authority**

Code expresses behavior precisely but is not broadly legible.

A clause-structured operational contract expresses behavioral guarantees and constraints explicitly.

It defines invariants that must always hold. It defines authority boundaries, scope constraints, deletion semantics, and abort conditions.

These constructs remain technical but are legible at the behavioral level across roles.

QA teams test against clauses. Product teams evaluate guarantees. On-call engineers reference explicit invariants during incident analysis. Change requests modify clauses rather than relying on institutional memory embedded in code.

Authority is decoupled from a particular implementation and anchored in specification.

---

## **Empirical Demonstration**

The method was applied to a deterministic system specified as a clause-structured contract:

**Artifact Sync System — Convergence Contract (v1.1)**  
 (Published alongside this paper.)

The contract defined identity semantics, authority rules, deletion conditions, and convergence guarantees governing document synchronization.

It was hardened through multiple adversarial rounds prior to derivation.

Independent implementations were generated under enforced isolation, including at least one implementation produced by a different AI system than the one used to assist drafting.

Each implementation was evaluated clause-by-clause.

### **Clause Excerpt: Authority Rule**

“The document stored under the authoritative doc\_id SHALL be treated as the single source of truth. Manual file variants SHALL NOT override the authoritative document unless explicitly promoted.”

Observed divergence included implicit merging of manual variants, filename-based identity inference, and conditional overrides without explicit promotion logic.

### **Clause Excerpt: Deletion Semantics**

“Manual file variants SHALL be removed when no authoritative document exists for the corresponding doc\_id. Historical versions MAY be preserved but SHALL NOT participate in active synchronization.”

Observed divergence included unconditional deletion, indefinite retention of orphaned variants, and inconsistent deletion timing.

### **Clause Excerpt: Convergence Guarantee**

“Given identical authoritative state, independent nodes SHALL converge to identical active document sets after synchronization.”

Observed divergence included transient-state inconsistency and ambiguity in synchronization ordering.

### **Clause-Level Adherence Matrix (Excerpt)**

| Clause Category | Impl A | Impl B | Impl C |
| ----- | ----- | ----- | ----- |
| Authority Rule (MUST) | FAIL | PARTIAL | PASS |
| Deletion Semantics (MUST) | FAIL | PARTIAL | PASS |
| Convergence Guarantee (MUST) | PARTIAL | PASS | PASS |
| Schema Structure (STRUCTURAL) | PASS | PARTIAL | PASS |

Divergence concentrated in authority and deletion clauses. Structural clauses were comparatively stable.

Clauses associated with recurrent divergence were refined. The contract was re-sampled. Subsequent derivations demonstrated reduced instability across previously unstable clauses.

The objective was not to rank systems. It was to test whether a clause-structured contract could remain behaviorally stable under independent derivation.

Divergence localized predictably and decreased under clause refinement.

A subsequent replication using stricter Convergence Contract v2.5.2 evaluated independent implementations across two AI systems under identical prompts. Both ultimately achieved full MUST-level compliance (16/16), though remediation rounds differed. The contract remained unchanged. Clause-level corrections reduced divergence until invariant stability was achieved.

---

## **Implications for Writing Software**

If implementation can be produced in seconds, engineering effort concentrates where scarcity remains.

Code remains necessary. Architecture and performance remain technical disciplines.

But when implementations are inexpensive and replaceable, they need not carry authority.

The contract can.

Teams can agree on operational semantics before defending implementations. Competing implementations can be generated and evaluated without destabilizing system truth. QA tests against explicit clauses. On-call engineers reference defined invariants. Change requests modify the contract rather than relying on implicit behavioral memory.

This paper does not claim that contract-centered derivation guarantees superior software.

It claims something structural:

When implementation is inexpensive, separating specification authority from implementation artifact becomes practical.

That separation enables comparative derivation, measurable convergence, and cross-functional clarity in ways that were previously impractical.

---

### **Related Practitioner Writing**

Independent practitioner writing reflects the same structural shift described in this paper: when implementation becomes inexpensive, precision in operational description becomes the constraining factor.

Oliver Cronk describes a renewed emphasis on specification clarity in generative-assisted development. Thoughtworks discusses the possibility that maintained specifications may become the durable artifact while code becomes transient.

Boris Tane documents approximately nine months of sustained specification-first generative workflow in practice, demonstrating that detailed operational descriptions can reliably drive implementation.

These accounts reflect the same structural condition described in this paper. The method presented here focuses on what becomes measurable when multiple independent implementations are derived from a shared contract and evaluated clause-by-clause.

![][image1]

[image1]: <data:image/png;base64,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>