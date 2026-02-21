# General Response

We thank all reviewers for their constructive feedback. Several concerns were raised by multiple reviewers, and we address these shared themes below. Reviewer-specific responses follow in the individual rebuttals.

---

## GR1: Yes/No Question Format

The yes/no format was a deliberate design decision driven by a fundamental challenge in EO evaluation. **Earth Observation questions admit multiple valid computational pathways, each with scene-dependent parameters.**

For example, to determine whether a region experienced flooding, an agent could:

- Compute **NDWI** (Normalized Difference Water Index) from optical imagery,
- Compute **MNDWI** (Modified NDWI) to better distinguish water from built-up areas,
- Process **SAR (Synthetic Aperture Radar)** backscatter imagery for cloud-independent water detection, or
- Apply a learned **segmentation model** for water body delineation.

The thresholds and hyperparameters for each approach are scene-specific: they depend on sun azimuth, water clarity, sediment content, and cover type. Although deriving a numerical answer (e.g., "342 km²") is desirable in the machine learning, computer vision, and/or reasoning communities, it does not carry the same meaning here: adopting different approaches may yield very different results that are individually reproducible yet mutually inconsistent. The yes/no format resolves this by providing a **robust evaluation signal**: it captures whether the agent's end-to-end reasoning pipeline (dataset selection → preprocessing → computation → interpretation) arrives at the correct qualitative conclusion, without penalizing methodological variation.

Despite the binary format, the *computational complexity* required to answer each question remains high. We conducted an automated capability analysis and found that **75.0%** of questions require two or more distinct reasoning capabilities. Concretely, to answer a typical question the agent must (1) identify and load the correct dataset, (2) compute the index or quantity of interest, (3) validate the value range against physical constraints, and (4) compare the results across regions or time periods. Beyond these steps, the agent must also handle problem scenarios such as invalid dataset IDs, empty collections, and masked pixels. The 40–60% accuracy range observed across state-of-the-art models confirms that these questions are far from trivial.

---

## GR2: Additional Agent Architecture (OSCAR)

We have conducted additional experiments using the **OSCAR** (Operating System Control via State-Aware Reasoning and Re-Planning) framework [1], a state-machine-based agent (ICLR 2025) that is architecturally distinct from Reflexion. Rather than retry-based self-reflection, OSCAR follows a stateful pipeline — **Init → Observe → Plan → Execute → (Re-Plan loop) → Verify → Done** — where only failing steps are modified while successful ones are preserved.

With Gemini-2.5-Pro on the full UnivEARTH benchmark, the cumulative accuracy across re-planning rounds is:

| Round | 0 (init) | 1 | 2 | 3 |
|---|---|---|---|---|
| Accuracy | 33% | 47% | 53% | **56%** |

This is consistent with the Reflexion-style agent on the same backbone (~56–60%). The convergence of two architecturally distinct frameworks to similar accuracy suggests the **bottleneck is intrinsic EO reasoning difficulty** (dataset/band selection, scene-specific thresholds, spatial/temporal resolution) rather than agent design, reinforcing our paper's central thesis.

[1] Wang et al., "OSCAR: Operating System Control via State-Aware Reasoning and Re-Planning," ICLR 2025.

---

## GR3: Process-Level Error Analysis

We have conducted a **process-level error analysis** by examining full agent trajectories (dataset selection, code generation, execution output, re-planning). We categorize failures by where in the pipeline they occur:

**Error Taxonomy (Gemini-2.5-Pro, Zero-Shot Baseline):**

| Error Type | Count | % |
|---|---|---|
| Correct | 150 | 36.8% |
| Wrong Dataset (hallucinated asset ID) | 58 | 14.2% |
| Temporal/Spatial Mismatch (empty collection) | 64 | 15.7% |
| Wrong Band (non-existent band name) | 39 | 9.6% |
| Syntax/Runtime Error | 41 | 10.0% |
| Wrong Answer (correct execution, wrong reasoning) | 39 | 9.6% |
| Masking/Preprocessing (no valid pixels) | 11 | 2.7% |
| Numerical Failure (NaN/None result) | 4 | 1.0% |

This reveals that **the dominant failure modes are knowledge-related, not code-related**: wrong dataset IDs (14.2%), temporal/spatial mismatch (15.7%), and wrong band names (9.6%) together account for ~40% of all failures, while only 10% are pure syntax errors.

After applying iterative re-planning (3 rounds), the error profile shifts:

| Error Type | Baseline | After Re-planning | Δ |
|---|---|---|---|
| Wrong Dataset | 14.2% | 4.8% | −9.4% |
| Wrong Band | 9.6% | 0.5% | −9.1% |
| Temporal/Spatial Mismatch | 15.7% | 1.5% | −14.2% |
| Syntax/Runtime | 10.0% | 46.0% | +36.0% |

The re-planning loop resolves dataset and band selection errors, but reveals a **repair fragility** pattern: as the agent iteratively repairs code, it grows more complex and fragile, leading to increased runtime errors. This process-level analysis provides **actionable diagnostic insight**: (1) **retrieval-augmented tool grounding**, where agents query a structured catalog at inference time rather than relying on memorized schemas, and (2) **modular code generation** that decomposes complex computations into independently verifiable subroutines to prevent cascading repair errors.

We will add this error taxonomy and process-level analysis to the revised paper.
