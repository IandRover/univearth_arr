We thank the reviewer for the detailed feedback. We address each concern below.

---

## W1: Unclear agents-track contribution

We would like to highlight two transferable contributions beyond the domain-specific findings.

First, please refer to **GR3** for the full error taxonomy. We identify that **knowledge-grounding failures, not code-generation failures, are the dominant bottleneck for tool-use agents in scientific domains.** Knowledge-grounding errors (wrong dataset, wrong band, temporal/spatial mismatch) account for ~40% of all failures, while only 10% are pure syntax errors. These failure categories have direct analogs in other agent domains: API hallucination in web agents, schema hallucination in database agents, and constraint violation in planning agents.

Second, please refer to **GR2** for the full OSCAR results. We show that **the performance ceiling is architecture-invariant.** Two structurally different agent frameworks (Reflexion and OSCAR) converge to ~56% accuracy with the same backbone (Gemini-2.5-Pro), indicating that the bottleneck lies in the LLM's domain knowledge and tool-grounding capabilities rather than in orchestration design.

---

## W2: Limited root-cause insight and reliability analysis

Please refer to **GR3** for the full error taxonomy and shift analysis. The dominant failure mode is **knowledge-grounding errors** (~40%): the LLM hallucinates plausible but incorrect GEE asset IDs and band names because the GEE data catalog (1K+ datasets, each with unique band schemas) exceeds what LLMs can reliably memorize. After re-planning, knowledge and execution errors drop substantially (e.g., wrong band: 9.6% → 1.5%, syntax/runtime: 10.0% → 2.5%), but the proportion of **wrong answers more than doubles** from 9.6% to 21.3%: as more questions successfully execute, the remaining errors shift from pipeline failures to reasoning errors where the code runs correctly but produces an incorrect conclusion.

These findings point to two concrete directions applicable beyond EO: (1) retrieval-augmented tool grounding, where agents query a structured catalog at inference time rather than relying on memorized schemas, and (2) improved domain reasoning through better prompting strategies or domain-specific fine-tuning.

---

## W3: Stronger agent baselines/ablations needed

Please refer to **GR2** for the full OSCAR experiment. We have added the OSCAR agent (ICLR 2025) as a structurally different baseline. OSCAR uses a state-machine with targeted re-planning (only failing steps are modified), in contrast to Reflexion's full regeneration. Both frameworks converge to ~56% with the same backbone, providing evidence that the results reflect LLM capability limits rather than weak scaffolding.

Regarding constrained decoding and structured tool-calling: UnivEARTH requires *open-ended code generation* (composing arbitrary sequences of GEE filtering, mapping, reducing, and masking operations into complete programs), not selection from a fixed, manual API function set. Our existing ablations (JavaScript vs. Python API, with vs. without documentation, zero-shot vs. Reflexion vs. OSCAR) already isolate the effects of language choice, retrieval augmentation, and iterative refinement.
