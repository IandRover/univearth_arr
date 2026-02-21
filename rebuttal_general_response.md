# General Response

We thank all reviewers for their constructive feedback. Several concerns were raised by multiple reviewers, and we address these shared themes below. Reviewer-specific responses follow in the individual rebuttals.

---

## GR1: Yes/No Question Format

The yes/no format was a deliberate design decision driven by a fundamental challenge in EO evaluation. **Earth Observation questions admit multiple valid computational pathways to derive answers, and each requires scene-dependent parameters.** This makes it challenging to construct an open-ended benchmark (or even a multi-choice benchmark).

For example, to determine a region's flooding extent, an agent could choose one of the following approaches:

- Compute **NDWI** (Normalized Difference Water Index) from optical imagery,
- Compute **MNDWI** (Modified NDWI) to better distinguish water from built-up areas,
- Process **SAR (Synthetic Aperture Radar)** backscatter imagery for cloud-independent water detection,
- Apply a learned **segmentation model** for water body delineation, or
- Use existing Google Earth Engine datasets for flood mapping.

The thresholds and hyperparameters for each approach are scene-specific: they depend on sun azimuth, water clarity, sediment content, and cover type. Although deriving a numerical answer (e.g., "342 km²") is desirable in the machine learning, computer vision, and/or reasoning communities, it does not carry the same meaning here: adopting different approaches may yield very different results that are individually reproducible yet mutually inconsistent. The yes/no format resolves this by providing a **robust evaluation signal**: it captures whether the agent's end-to-end reasoning pipeline (dataset selection → preprocessing → computation → interpretation) arrives at the correct qualitative conclusion, without penalizing methodological variation.

Despite the binary format, the *computational complexity* required to answer each question remains high. Concretely, to answer a typical question the agent must (1) identify and load the correct dataset, (2) compute the index or quantity of interest, (3) validate the value range against physical constraints, and (4) compare the results across regions or time periods. Beyond these steps, the agent must also handle problem scenarios such as invalid dataset IDs, empty collections, and masked pixels. The 40–60% accuracy range observed across state-of-the-art models confirms that these questions are far from trivial.

---

## GR2: Additional Agent Architecture (OSCAR)

We have conducted additional experiments using the **OSCAR** (Operating System Control via State-Aware Reasoning and Re-Planning) framework [1], a state-machine-based agent (ICLR 2025) that is architecturally distinct from Reflexion. Rather than retry-based self-reflection, OSCAR follows a stateful pipeline — **Init → Observe → Plan → Execute → (Re-Plan loop) → Verify → Done** — where only failing steps are modified while successful ones are preserved.

With Gemini-2.5-Pro on the full UnivEARTH benchmark, the cumulative accuracy across re-planning rounds is:

| Round | 0 (init) | 1 | 2 | 3 |
|---|---|---|---|---|
| Accuracy | 31% | 49% | 53% | **56%** |

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

After applying iterative re-planning (OSCAR, 3 rounds), the error profile shifts significantly:

| Error Type | Baseline | After Re-planning | Δ |
|---|---|---|---|
| Correct | 36.8% | 55.9% | +19.1% |
| Wrong Dataset | 14.2% | 10.3% | −3.9% |
| Wrong Band | 9.6% | 1.5% | −8.1% |
| Temporal/Spatial Mismatch | 15.7% | 2.9% | −12.8% |
| Syntax/Runtime | 10.0% | 2.5% | −7.5% |
| Wrong Answer | 9.6% | 21.3% | +11.7% |

Re-planning substantially reduces knowledge-grounding errors (wrong dataset, wrong band, temporal/spatial mismatch) and execution errors. However, the proportion of **wrong answers more than doubles** from 9.6% to 21.3%: as more questions successfully execute, the remaining errors shift from pipeline failures to **reasoning errors** where the code runs correctly but produces an incorrect conclusion (e.g., wrong threshold, incorrect comparison logic). This suggests that after resolving surface-level failures, the next frontier is improving the agent's domain reasoning and scientific judgment.

This process-level analysis provides **actionable diagnostic insight**: (1) **retrieval-augmented tool grounding**, where agents query a structured catalog at inference time rather than relying on memorized schemas, and (2) **improved domain reasoning** through better prompting strategies or domain-specific fine-tuning to address the growing proportion of reasoning errors.

We will add this error taxonomy and process-level analysis to the revised paper.
