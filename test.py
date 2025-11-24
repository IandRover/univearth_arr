# 1. Import the necessary libraries
import ee
import geemap
ee.Initialize()

# 3. Create an interactive map.
# This map will be displayed in the output of your notebook cell.
Map = geemap.Map(center=[40, -100], zoom=4)

# 4. Load a Landsat 8 image collection.
# We'll filter it to a specific location and time period to get a clear image.
image = (
    ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
    .filterBounds(ee.Geometry.Point(-122.26, 37.87))
    .filterDate('2019-01-01', '2019-12-31')
    .sort('CLOUD_COVER')
    .first()
)

# 5. Define visualization parameters for a true-color composite.
# This will display the image in a way that is similar to what the human eye sees.
vis_params_true_color = {'bands': ['SR_B4', 'SR_B3', 'SR_B2'], 'min': 0, 'max': 3000}

# 6. Add the true-color Landsat image to the map.
Map.addLayer(image, vis_params_true_color, 'Landsat 8 True Color')

# 7. Calculate the NDVI.
# NDVI is a common indicator of live green vegetation.
# The formula is (NIR - Red) / (NIR + Red).
# For Landsat 8, the NIR band is B5 and the Red band is B4.
nir = image.select('SR_B5')
red = image.select('SR_B4')
ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')

# 8. Define a color palette for the NDVI layer.
# This will visually represent the NDVI values, with green indicating healthier vegetation.
ndvi_palette = [
    'FFFFFF', 'CE7E45', 'DF923D', 'F1B555', 'FCD163', '99B718', '74A901',
    '66A000', '529400', '3E8601', '207401', '056201', '004C00', '023B01',
    '012E01', '011D01', '011301'
]
vis_params_ndvi = {'min': -1, 'max': 1, 'palette': ndvi_palette}

# 9. Add the NDVI layer to the map.
Map.addLayer(ndvi, vis_params_ndvi, 'NDVI')

# 10. Add a layer control to the map.
# This allows you to toggle the visibility of the different layers.
Map.addLayerControl()

# 11. Display the map.
Map