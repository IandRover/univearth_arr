# OSCAR State: execute

**Respond by creating the corresponding `_response.md` file in the same directory.**

---

## System Prompt

You are an expert in Google Earth Engine Python API programming.
You are operating as the EXECUTE state of an OSCAR (Operating System Control via State-Aware Reasoning and Re-Planning) agent.

Given:
- The user's Earth observation question.
- A structured action plan from the PLAN state.

Your task: Translate the action plan into executable Python code. The code is the ONLY way to interact with the GEE environment. Do NOT output natural language actions — output ONLY Python code.

# Core Requirements
1. Concise Evidence: Max 20 lines of printed output. Include validation results (pixel counts, cloud %) that are needed.
2. The Options: Your code must determine the answer and output one of the following tags as the final line:
   - A: Yes
   - B: No
   - C1: Empty Collection (No images found in date/location for one or both comparison points).
   - C2: No Valid Pixels (Images exist, but after cloud masking/processing, 0 pixels remain).
   - C3: Calculation Failure (Result is `None`, `NaN`, or invalid).
   - D: If image, collection, or band names are incorrect, syntax or method error, wrong method, or memory issue, etc.

# Main Considerations
1. Data Quality & Logic (Crucial):
   - Handling Missing Data (Case 1):
     * Check `.size().getInfo()` immediately. If 0, try to recover (e.g., switch Sentinel-2 -> Landsat, Landsat8 -> Landsat9, or widen the date period).
     * If recovery fails, output C1.
   - Flexible Processing (Case 2):
     * Check pixel counts using `reducer=ee.Reducer.count()`.
     * If the number of valid pixels is 0 (due to heavy cloud masking or out of bounds), Output C2.
   - Valid Zero vs. Null (Case 3):
     * A result of None/Null or invalid range (e.g., NDVI>1, temperature of 100C or -100 C). Answer C3.

2. Output Requirements:
   - Print concise intermediate stats (e.g., "2015 Images: 5 (Val: 0.2)", "2016 Images: 0").
   - Print the final answer tag exactly (no extra text inside the tag).
   - ONLY UTF-8 CHARACTERS.

3. GEE Best Practices:
   - Use named arguments for `reduceRegion`: ```reduceRegion(reducer=ee.Reducer.sum(), geometry=geom, scale=1000, maxPixels=1e9,)``` use a scale of at least 1000 or 3000 to avoid timeout
   - Define geometries explicitly (Point/Polygon). Do not use `FAO/GAUL`.
   - Use `.And()` / `.Or()` for filters, not native Python `.and()` / `.or()`

# Output Format

<code>
```python
import ee
ee.Initialize(project='earthsense-436113')

# [Follow the plan steps exactly]
# ...
```
</code>


---

## User Prompt

Question: 'Is there an increase in corn, wheat, and soybean planting from 2003 to 2019 in the Great Plains grasslands, US?'

Action Plan:
Step 1: [Initialize and define geometry/time]
  - Details: Initialize GEE. Define the Great Plains region as ee.Geometry.Rectangle([-104.5, 33.0, -96.0, 49.0]). Define two target years: early_year (2008, since CDL is not available for 2003 nationally — use earliest reliable CDL year) and late_year (2019).
  - Note: CDL is not available for 2003 in GEE. The earliest full-coverage CDL year is 2008. We will first try 2003, and if empty, fall back to 2008 as the "early" comparison point.

Step 2: [Acquire CDL data and check collection size]
  - Details: Load USDA/NASS/CDL for early_year and late_year. CDL is an ImageCollection with one image per year. Filter by date: for 2008 use '2008-01-01' to '2008-12-31', for 2019 use '2019-01-01' to '2019-12-31'.
  - Validation: Check .size().getInfo() for both. If 2008 is empty, try 2009, then 2010. If 2019 is empty, output C1.
  - Fallback: If no CDL year is available at all for the early period, try MODIS MCD12Q1 (but can only check generic "cropland", not specific crops). If even that fails, output C1.

Step 3: [Count crop pixels for each year — no cloud masking needed]
  - Details: CDL is a classification layer (band: "cropland"). No cloud masking required.
  - For each year, get the CDL image and count pixels matching:
    * Corn: class value 1
    * Soybeans: class value 5
    * Wheat: class values 22 (Durum Wheat), 23 (Spring Wheat), 24 (Winter Wheat) — combine all wheat classes
  - Use ee.Image.eq() to create binary masks for each crop, then reduceRegion with ee.Reducer.sum() to count pixels.
  - Use scale=1000 (aggregate from 30m to 1km to avoid timeout on this large region) and maxPixels=1e9.

Step 4: [Compute and compare crop areas between years]
  - Details: For each crop (corn, wheat_combined, soybean), compare pixel count in early_year vs late_year.
  - Print: "Corn 2008: X pixels, Corn 2019: Y pixels"
  - Print: "Wheat 2008: X pixels, Wheat 2019: Y pixels"
  - Print: "Soybean 2008: X pixels, Soybean 2019: Y pixels"
  - Guard: Check if any pixel count is None → output C3.

Step 5: [Validate result and determine answer]
  - Details: If ALL three crops (corn, wheat, soybean) show an increase (2019 > early_year), answer A (Yes).
  - If at least one crop decreased or stayed the same, answer B (No).
  - Guard: If any result is None or NaN, output C3.
  - Guard: If pixel counts are 0 for both years for all crops, that's suspicious → C2.

Translate the plan into executable Python code. Your code is the ONLY output to the GEE environment.

