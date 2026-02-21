<code>
```python
import ee
ee.Initialize(project='earthsense-436113')

# Step 1: Define geometry and years
great_plains = ee.Geometry.Rectangle([-104.5, 33.0, -96.0, 49.0])
early_year = 2008
late_year = 2019

# Step 2: Acquire CDL data and check availability
cdl = ee.ImageCollection('USDA/NASS/CDL')

early_col = cdl.filter(ee.Filter.date(f'{early_year}-01-01', f'{early_year}-12-31'))
late_col = cdl.filter(ee.Filter.date(f'{late_year}-01-01', f'{late_year}-12-31'))

early_size = early_col.size().getInfo()
late_size = late_col.size().getInfo()
print(f"CDL {early_year} images: {early_size}, CDL {late_year} images: {late_size}")

if early_size == 0:
    # Fallback: try 2009, then 2010
    for fallback_yr in [2009, 2010]:
        early_col = cdl.filter(ee.Filter.date(f'{fallback_yr}-01-01', f'{fallback_yr}-12-31'))
        early_size = early_col.size().getInfo()
        if early_size > 0:
            early_year = fallback_yr
            print(f"Fallback to CDL {early_year}: {early_size} images")
            break
    if early_size == 0:
        print("No CDL data available for early period.")
        print("<answer>C1</answer>")
        exit()

if late_size == 0:
    print("No CDL data available for 2019.")
    print("<answer>C1</answer>")
    exit()

early_img = early_col.first().select('cropland')
late_img = late_col.first().select('cropland')

# Step 3: Count crop pixels for each year
# Corn=1, Soybean=5, Wheat=22,23,24
def count_crop_pixels(img, region, crop_classes):
    mask = img.eq(crop_classes[0])
    for c in crop_classes[1:]:
        mask = mask.Or(img.eq(c))
    count = mask.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=1000,
        maxPixels=1e9,
    ).get('cropland').getInfo()
    return count

corn_early = count_crop_pixels(early_img, great_plains, [1])
corn_late = count_crop_pixels(late_img, great_plains, [1])
wheat_early = count_crop_pixels(early_img, great_plains, [22, 23, 24])
wheat_late = count_crop_pixels(late_img, great_plains, [22, 23, 24])
soy_early = count_crop_pixels(early_img, great_plains, [5])
soy_late = count_crop_pixels(late_img, great_plains, [5])

# Step 4: Print results
print(f"Corn {early_year}: {corn_early}, Corn {late_year}: {corn_late}")
print(f"Wheat {early_year}: {wheat_early}, Wheat {late_year}: {wheat_late}")
print(f"Soybean {early_year}: {soy_early}, Soybean {late_year}: {soy_late}")

# Step 5: Validate and determine answer
all_counts = [corn_early, corn_late, wheat_early, wheat_late, soy_early, soy_late]
if any(v is None for v in all_counts):
    print("One or more pixel counts is None.")
    print("<answer>C3</answer>")
elif all(v == 0 for v in all_counts):
    print("All pixel counts are 0.")
    print("<answer>C2</answer>")
else:
    corn_inc = corn_late > corn_early
    wheat_inc = wheat_late > wheat_early
    soy_inc = soy_late > soy_early
    print(f"Corn increased: {corn_inc}, Wheat increased: {wheat_inc}, Soybean increased: {soy_inc}")
    if corn_inc and wheat_inc and soy_inc:
        print("<answer>A</answer>")
    else:
        print("<answer>B</answer>")
```
</code>
