# glossary-v0.7.pdf

## Page 1

Canonical Glossary v0.7 — Spine Draft

### 1. Governing Artifact

Public-facing definition: A durable artifact that governs what counts as correct for a system, workflow, or evaluation. Plain-English shadow: The thing that actually decides what counts as correct. Notes:

- This term exists to identify where binding authority lives.
- It is meant to be broader than “spec” or “contract” alone.
- Its purpose is to constrain acceptable change, not merely describe intent.

### 2. Invariant

Public-facing definition: A property that must continue to hold across valid system states or valid mutations. Plain-English shadow: A rule that must keep being true even as the system changes. Notes:

- An invariant is binding, not merely preferred.
- It is stronger than a loose expectation or best practice.

## Page 2

- Violation indicates incorrectness, not style difference.

### 3. Invariant Scope

Public-facing definition: The full set of surfaces, paths, or mutation points across which an invariant must hold. Plain-English shadow: All the places a rule has to hold, not just the place you happened to edit. Notes:

- An invariant may appear satisfied locally while still being violated elsewhere.
- This term exists to prevent false local success from being mistaken for full compliance.
- Invariant scope is central to distinguishing local modification from propagated obligation.

### 4. Same-Surface Change

Public-facing definition: A requirement change whose effects are confined to the same surface or mutation path already under modification. Plain-English shadow: A change that only needs to be made in the same place you are already touching. Notes:

- Same-surface changes can often be satisfied through local mutation alone.

## Page 3

- This term matters primarily as one half of a contrast pair with cross-surface change.
- It identifies the simpler topology class in iterative change.

### 5. Cross-Surface Change

Public-facing definition: A requirement change whose effects must propagate across more than one surface, path, or mutation mechanism. Plain-English shadow: A change that has to carry through into other places too, not just the one you touched first. Notes:

- Cross-surface changes commonly expose incomplete propagation.
- A system may appear compliant if only the named local surface is updated.
- This term identifies the topology class where iterative instability is more likely to appear.

### 6. Iterative

Stability Public-facing definition: The degree to which a workflow preserves binding requirements across sequential rounds of modification. Plain-English shadow: How well a workflow keeps the important rules intact as changes keep piling up. Notes:

## Page 4

- Iterative stability is not the same as one-shot correctness.
- The concern is not whether a system works once, but whether correctness survives continued mutation.
- This is a core object of study in the research program.

### 7. Decision Surface

Public-facing definition: The set of externally observable decisions or state transitions used to determine whether a system or artifact is semantically compliant. Plain-English shadow: The points where the system’s real outcomes can change in a way that matters. Notes:

- Stability is judged at the decision surface, not at the byte, formatting, or wording surface.
- A finding affects the decision surface only if it can change an externally observable outcome or state transition.
- This term exists to block noise, overfitting, and spec pollution from being mistaken for meaningful instability.
