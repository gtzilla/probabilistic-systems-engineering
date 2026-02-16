# Probabilistic Systems Engineering

**Research on engineering methods for systems where identical inputs don't guarantee identical outputs.**

When you interact with AI agents, generative models, or other probabilistic systems, outputs vary. The same prompt produces different responses. Small context changes shift behavior. This creates a specific engineering problem: **how do you apply discipline when the substrate is stochastic?**

This repository documents experimental approaches to reducing variance, improving auditability, and making reasoning observable in probabilistic systems.

---

## The Core Problem

AI systems produce outputs by sampling from probability distributions. This creates two challenges:

1. **Structural variance** – Identical requests produce different reasoning paths, making drift hard to measure
2. **Collapsed implementation cost** – Generating alternative implementations is now cheap, changing what "authority" means in software development

Traditional engineering practices assume determinism. These experiments explore what changes when that assumption breaks.

---

## What's Here

### [Is This Engineering?](papers/is-this-engineering.pdf)
*Exploratory essay*

Frames the substrate shift. When systems produce distributions instead of certainties, does "engineering" still mean the same thing? Examines the discomfort of applying familiar patterns to unfamiliar substrates.

**Published:** [Date]  
**Length:** 3 pages

---

### [Verified/Deduction/Gap (VDG)](papers/verified-deduction-gap-v1.4.1.pdf)
*Structural discipline for reducing variance*

A response-partitioning protocol that separates:
- **Verified** – Evidence from artifacts and stable domain facts
- **Deduction** – Logical implications of verified statements  
- **Gap** – Missing constraints and uncertainty

By forcing explicit boundaries, VDG reduces degrees of freedom in response formation. The model continues sampling from a distribution, but the shape of that distribution is constrained.

**Why it matters:** Makes inference inspectable, reduces assumption leakage, decreases review entropy, narrows behavioral range under reset conditions.

**Published:** [Date]  
**Version:** 1.4.1  
**Contract:** [VDG Response Protocol](contracts/vdg-contract-v1.4.1.pdf)

---

### [Contract-Centered Engineering](papers/contract-centered-engineering-v2.10.pdf)
*Engineering topology under collapsed implementation cost*

When generating implementations becomes inexpensive, authority can migrate from singular codebases to clause-structured operational contracts.

**The shift:**
- Traditional: Implementation is scarce, specification is cheap
- Now: Implementation is cheap, specification precision is scarce

**The method:** A 7-step loop for hardening contracts through independent derivation:
1. Contract-first inversion
2. Adversarial hardening
3. Independent derivation  
4. Clause-level evaluation
5. Divergence localization
6. Clause refinement
7. Re-sampling and convergence measurement

**Empirical demonstration:** Artifact synchronization system specified via contract, then independently derived multiple times. Divergence concentrated in authority rules and deletion semantics. Clause refinement reduced instability across subsequent derivations.

**Published:** [Date]  
**Version:** 2.10  
**Demonstration:** [Convergence Contract v1.1](contracts/convergence-contract-v1.1.pdf)

---

## Contracts

Operational specifications that demonstrate the methodology:

**[VDG Contract v1.4.1](contracts/vdg-contract-v1.4.1.pdf)**  
Response structure protocol. Defines scope triggers, section requirements, classification rules, and compliance tests for VDG responses.

**[Convergence Contract v1.1](contracts/convergence-contract-v1.1.pdf)**  
Document synchronization system specification. Demonstrates explicit authority semantics, deletion safety gates, abort conditions, and clause-level evaluability.

Both contracts were tested through independent derivation as described in Contract-Centered Engineering.

---

## Reading Order

**If you're new to this work:**
1. Start with **Is This Engineering?** for framing
2. Read **VDG** for an operational method
3. Read **Contract-Centered Engineering** for the topology shift

**If you're already thinking about AI system rigor:**
- Go straight to **VDG** for variance reduction technique
- Go straight to **Contract-Centered** for specification-first methodology

**If you want to see examples:**
- Read the contracts alongside the papers they demonstrate

---

## What This Is Not

- **Not tooling** – These are methodology papers, not frameworks or libraries
- **Not determinism** – This doesn't eliminate randomness, it shapes distributions
- **Not general AI theory** – This is engineering practice for probabilistic systems
- **Not prescriptive** – Methods are experimental and expected to evolve

---

## Updates and Evolution

This work evolves through continued experimentation. Papers are versioned. Contracts are tested and refined.

**For automatic update notifications:** [Download on Gumroad](https://gtzilla.gumroad.com/) – free, includes all updates

**To follow development:** Watch this repo

**To contribute observations:** Open an issue describing your experiments

---

## Status

- **VDG:** Validation Stage 1 (Internal model testing)
- **Contract-Centered Engineering:** Empirical demonstration published, method under continued testing
- **All work:** Experimental, expected to evolve

---

## Citation

If you reference this work:

**VDG:**
```
Tomlinson, G. (2026). Verified/Deduction/Gap: A Structural Discipline for 
Reducing Variance in Probabilistic Systems (v1.4.1). 
https://github.com/gtzilla/probabilistic-systems-engineering
```

**Contract-Centered Engineering:**
```
Tomlinson, G. (2026). Contract-Centered Engineering Under Collapsed 
Implementation Cost (v2.10). 
https://github.com/gtzilla/probabilistic-systems-engineering
```


---

## Author

**Gregory Tomlinson**  
Lead Engineer  
[LinkedIn](https://www.linkedin.com/in/gregorytomlinson/)

This work emerged from internal experiments with AI agents and ticket systems, driven by the question: when the substrate is probabilistic, what does engineering discipline actually look like?

---

## License

[CC BY 4.0](LICENSE) – You're free to use, adapt, and build on this work with attribution.
