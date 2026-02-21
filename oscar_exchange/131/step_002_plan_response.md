<plan>
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
</plan>
