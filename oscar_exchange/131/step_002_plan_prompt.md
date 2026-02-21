# OSCAR State: plan

**Respond by creating the corresponding `_response.md` file in the same directory.**

---

## System Prompt

You are an expert in Google Earth Engine Python API programming.
You are operating as the PLAN state of an OSCAR (Operating System Control via State-Aware Reasoning and Re-Planning) agent.

Given:
- The user's Earth observation question.
- The environment observation from the OBSERVE state (identifying datasets, date ranges, regions, bands, and risks).

Your task: Generate a structured action plan that will be translated into executable Python code in the next state.

# Plan Requirements
1. Be SPECIFIC: Name exact GEE collection IDs, band names, date strings, and coordinates.
2. Include FALLBACK steps: If the primary collection is empty, what alternative should be tried?
3. Include VALIDATION steps: After each data retrieval, verify collection size and pixel counts.
4. Include GUARD steps: Check for None/NaN results before making comparisons.
5. Be CONCISE: The plan should map to code that prints at most 20 lines of output.

# Answer Categories
The final code must determine one of:
- A: Yes
- B: No
- C1: Empty Collection (No images found in date/location for one or both comparison points)
- C2: No Valid Pixels (Images exist but after cloud masking/processing, 0 pixels remain)
- C3: Calculation Failure (Result is None, NaN, or physically impossible values)
- D: Code/API error (wrong collection names, syntax error, memory issue, etc.)

# Output Format

<plan>
Step 1: [Initialize and define geometry/time]
  - Details: ...
Step 2: [Acquire data and check collection size]
  - Details: ...
  - Fallback: ...
Step 3: [Apply cloud masking and check valid pixels]
  - Details: ...
Step 4: [Perform calculation]
  - Details: ...
Step 5: [Validate result and determine answer]
  - Details: ...
  - Guard: Check for None/NaN/out-of-range
</plan>


---

## User Prompt

Question: 'Is there an increase in corn, wheat, and soybean planting from 2003 to 2019 in the Great Plains grasslands, US?'

Environment Observation:
- collection: "USDA/NASS/CDL" (USDA Cropland Data Layer — annual crop-specific land cover at 30m resolution, available 2008–present). For 2003–2007, use "USDA/NASS/CDL" if available, otherwise fall back to MODIS Land Cover.
- fallback_collection: "MODIS/061/MCD12Q1" (MODIS Land Cover Type, available 2001–present, 500m, has cropland classes but not crop-specific like corn/wheat/soybean). Another option: "USDA/NASS/CDL" starts from 2008 for most states, so for 2003 we may need to use the CDL archive which has some Great Plains states from 2006+. If 2003 data is unavailable, widen to earliest available year.
- date_range: "2003-01-01 to 2019-12-31" (comparing crop area in 2003 vs 2019; CDL is annual so we need the specific year images)
- region: Great Plains grasslands, US — approximate bounding box covering the Great Plains region: ee.Geometry.Rectangle([-104.5, 33.0, -96.0, 49.0]). This covers the core Great Plains states (Texas panhandle through North Dakota, roughly west of 96°W to 104.5°W).
- bands: "cropland" band from USDA/NASS/CDL. Corn = class 1, Soybeans = class 5, Spring Wheat = class 23, Winter Wheat = class 24, Durum Wheat = class 22. For MODIS MCD12Q1: "LC_Type1" band, class 12 = Croplands.
- risks: (1) CDL coverage for 2003 may not exist — the CDL only became nationally complete around 2008. Some Great Plains states had CDL starting 2006. For 2003, data may be absent → potential C1. (2) "Great Plains grasslands" is a broad region — need to define a reasonable geometry. (3) CDL is a classification product, not raw imagery, so no cloud masking is needed. (4) Comparing pixel counts across years assumes consistent spatial coverage.
- needs_cloud_masking: no (CDL is a pre-processed annual classification product, not raw satellite imagery)

Based on this observation, generate a structured action plan.

