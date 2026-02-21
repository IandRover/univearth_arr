# Rebuttal Draft — UnivEARTH

We thank the reviewers for their constructive feedback. We address each concern below.

---

## W1: Limited comparison with other agent architectures

We have conducted additional experiments using **OSCAR** [1], a state-machine-based agent (ICLR 2025) that is architecturally distinct from Reflexion. Rather than retry-based self-reflection, OSCAR follows a stateful pipeline — **Init → Observe → Plan → Execute → (Re-Plan loop) → Verify → Done** — where only failing steps are modified while successful ones are preserved.

With Gemini-2.5-Pro on the full UnivEARTH benchmark:

| Round | 0 (init) | 1 | 2 | 3 |
|---|---|---|---|---|
| Accuracy | 33% | 47% | 53% | **56%** |

This is consistent with Reflexion on the same backbone (~56–60%). The convergence of two architecturally distinct frameworks to similar accuracy suggests the **bottleneck is intrinsic EO reasoning difficulty** — dataset/band selection, scene-specific thresholds, spatial/temporal resolution — rather than agent design, reinforcing our paper's central thesis.

[1] Wang et al., "OSCAR: Operating System Control via State-Aware Reasoning and Re-Planning," ICLR 2025.

## W2: Insufficient annotation details

The annotation followed four principles: **(1) Domain Specificity** — questions span seven predefined categories (Hydrosphere, Geology, Human Activity, Fire, Atmosphere, Land Cover, Temperatures); **(2) Objectivity** — each question is grounded in quantitative statistics from the source article or visual comparisons between satellite image pairs with captions; **(3) Clarity** — temporal scope, spatial scope, and measurable quantities are precisely specified using domain-standard terms (e.g., "NDVI" not "vegetation greenness," "land surface temperature" not "temperature"); **(4) GEE Feasibility** — every target quantity must be available in the Google Earth Engine catalog. All QA pairs were reviewed by at least two annotators; ambiguous or GEE-infeasible questions were discarded.

## W3: Limited dataset size and yes/no format

Diversity and complexity of the underlying EO reasoning were our primary focus throughout the research. **The core challenge is that Earth Observation questions admit multiple valid computational pathways, each with scene-dependent parameters.** For example, to determine whether a region experienced flooding, an agent could:

- Compute **NDWI** (Normalized Difference Water Index) from optical imagery,
- Compute **MNDWI** (Modified NDWI) to better distinguish water from built-up areas,
- Process **SAR (Synthetic Aperture Radar)** backscatter imagery for cloud-independent water detection, or
- Apply a learned **segmentation model** for water body delineation.

Furthermore, the thresholds and hyperparameters for each approach are scene-specific: they depend on sun azimuth, water clarity, sediment content, land cover type, and sensor calibration. This means that **a numerical answer (e.g., "the flooded area is 342 km²") can vary dramatically depending on the method and parameters chosen, making inter-annotator agreement on free-form numerical answers extremely difficult to establish fairly**. The yes/no format resolves this by providing a **robust evaluation signal**: it captures whether the agent's end-to-end reasoning pipeline (dataset selection → preprocessing → computation → interpretation) arrives at the correct qualitative conclusion, without penalizing methodological variation.

We note that despite the binary format, the *computational complexity* required to answer each question remains high — the agent must still write correct GEE code that selects appropriate datasets, handles spatial/temporal filtering, applies domain-appropriate indices, and interprets the results. The 40–60% accuracy range observed across state-of-the-art models confirms that these questions are far from trivial.

## W4: Incomplete related work

We will include both suggested references. "Vision-Language Reasoning for Geolocalization" (AAAI 2026) tackles geospatial reasoning via RL for localization, while "SpatialWebAgent" (ACL 2025) applies LLM agents to spatial information extraction. Our work is complementary — UnivEARTH evaluates a deeper level of geospatial reasoning requiring agents to write executable scientific code over multi-spectral, multi-temporal satellite data.
