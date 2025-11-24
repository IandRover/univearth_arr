// // Require client library and private key.
// var ee = require('@google/earthengine');
// var privateKey = require('./test-project-473922-29f05d49bed7');

// // Initialize client library and run analysis.
// var runAnalysis = function() {
//   ee.initialize(null, null, function() {
//     // 1. Define an Area of Interest (AOI) for Ithaca.
//     // We create a 1000-meter (1km) radius circle around a central point.
//     var ithacaAOI = ee.Geometry.Point([-76.5019, 42.4440]).buffer(1000);

//     // Load the Landsat 8 Surface Reflectance image collection.
//     var landsat8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2');

//     // Filter the collection by date and location to get the best image.
//     var image = landsat8
//         .filterDate('2017-08-01', '2017-08-31')
//         .filterBounds(ithacaAOI)
//         .sort('CLOUD_COVER')
//         .first();

//     // Calculate NDVI. The formula is (NIR - Red) / (NIR + Red).
//     // For Landsat 8, NIR is band 'SR_B5' and Red is 'SR_B4'.
//     var ndvi = image.expression(
//         '(NIR - RED) / (NIR + RED)', {
//           'NIR': image.select('SR_B5'),
//           'RED': image.select('SR_B4')
//         }).rename('NDVI');

//     // 2. Calculate the mean NDVI within the Ithaca AOI.
//     // reduceRegion() computes statistics for all pixels inside the given geometry.
//     var meanNdvi = ndvi.reduceRegion({
//       reducer: ee.Reducer.mean(),
//       geometry: ithacaAOI,
//       scale: 30,  // Scale in meters for Landsat imagery.
//       maxPixels: 1e9
//     });

//     // 3. Get the result from the server and print it.
//     // getInfo() is an asynchronous function that fetches the computation result.
//     // It takes a callback function that runs once the data is ready.
//     meanNdvi.getInfo(function(value, error) {
//       if (error) {
//         console.error('An error occurred:', error);
//       } else {
//         console.log('Calculation complete.');
//         console.log('Mean NDVI for Ithaca in August 2017:');
//         console.log(value); // This prints the dictionary, e.g., {NDVI: 0.548}
//         console.log('Just the value:', value.NDVI); // This prints just the number
//       }
//     });

//   }, function(e) {
//     console.error('Initialization error: ' + e);
//   });
// };

// // Authenticate using a service account.
// ee.data.authenticateViaPrivateKey(privateKey, runAnalysis, function(e) {
//   console.error('Authentication error: ' + e);
// });

const ee = require('@google/earthengine');
const privateKey = require('./.earthsense-436113-b294c5f5c2dc.json');

// const ee = require('@google/earthengine');

async function runAnalysis() {
  // 1. Geometry & Time Definitions
  const windhoek = ee.Geometry.Point(17.0833, -22.5594); // Approximate coordinates for Windhoek
  const analysisRegion = windhoek.buffer(5000); // 5 km buffer around Windhoek

  // Target dates for comparison
  const date2020 = '2020-01-29';
  const date2021 = '2021-02-07';

  // Define a search window around the target dates to find suitable images
  const windowDays = 7;
  const start2020 = ee.Date(date2020).advance(-windowDays, 'day');
  const end2020 = ee.Date(date2020).advance(windowDays, 'day');
  const start2021 = ee.Date(date2021).advance(-windowDays, 'day');
  const end2021 = ee.Date(date2021).advance(windowDays, 'day');

  // Scale for reduceRegion to avoid memory issues and speed up computation
  const scale = 1000;

  // 2. Data Acquisition & Cloud Masking Function
  function maskS2clouds(image) {
    const s2Cloudless = image.select('SCL');
    // Cloud-related SCL values:
    // 3: Cloud shadow
    // 8: Medium probability cloud
    // 9: High probability cloud
    // 10: Cirrus
    const cloudMask = s2Cloudless.eq(3).or(s2Cloudless.eq(8)).or(s2Cloudless.eq(9)).or(s2Cloudless.eq(10)).not();
    return image.updateMask(cloudMask);
  }

  // Function to calculate NDVI
  function addNdvi(image) {
    const ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
    return image.addBands(ndvi);
  }

  // Helper function to process data for a given period
  async function processPeriod(start, end, region, yearStr) {
    let collection = ee.ImageCollection('COPERNICUS/S2_SR')
      .filterBounds(region)
      .filterDate(start, end)
      .map(maskS2clouds)
      .map(addNdvi);

    const collectionSize = await collection.size().getInfo();
    if (collectionSize === 0) {
      console.log(`No images found for ${yearStr} after initial filter.`);
      return { ndvi: null, pixelCount: 0, imageCount: 0 };
    }

    // Select the least cloudy image within the collection.
    // Cloud percentage is not directly available in S2_SR without extra computation.
    // A common proxy is to just use the median image, or filter by a cloud cover property if it existed directly.
    // For simplicity, we'll take the median of all valid images after masking.
    const medianImage = collection.select('NDVI').median();

    if (!medianImage) {
      console.log(`No valid median image could be generated for ${yearStr}.`);
      return { ndvi: null, pixelCount: 0, imageCount: collectionSize };
    }

    // Calculate valid pixel count after masking for the median image
    const pixelCountResult = await medianImage.reduceRegion({
      reducer: ee.Reducer.count(),
      geometry: region,
      scale: scale,
      maxPixels: 1e9
    }).getInfo();

    const validPixelCount = pixelCountResult && pixelCountResult.NDVI ? pixelCountResult.NDVI : 0;

    if (validPixelCount === 0) {
      console.log(`No valid pixels remaining for ${yearStr} after cloud masking.`);
      return { ndvi: null, pixelCount: 0, imageCount: collectionSize };
    }

    // Calculate mean NDVI for the period
    const ndviResult = await medianImage.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: region,
      scale: scale,
      maxPixels: 1e9
    }).getInfo();

    const meanNdvi = ndviResult && ndviResult.NDVI ? ndviResult.NDVI : null;

    console.log(`${yearStr} Images: ${collectionSize} (Val Pixels: ${validPixelCount}, Mean NDVI: ${meanNdvi !== null ? meanNdvi.toFixed(3) : 'N/A'})`);
    return { ndvi: meanNdvi, pixelCount: validPixelCount, imageCount: collectionSize };
  }

  let result2020, result2021;

  try {
    result2020 = await processPeriod(start2020, end2020, analysisRegion, '2020');
    result2021 = await processPeriod(start2021, end2021, analysisRegion, '2021');
  } catch (error) {
    console.log(`An error occurred during data processing: ${error.message}`);
    console.log("C3"); // Catch potential calculation or runtime errors
    return;
  }

  // 4. Validation & Final Answer
  if (result2020.imageCount === 0 || result2021.imageCount === 0) {
    console.log("C1"); // One or both collections were empty
    return;
  }

  if (result2020.pixelCount === 0 || result2021.pixelCount === 0) {
    console.log("C2"); // No valid pixels after masking for one or both periods
    return;
  }

  const ndvi2020 = result2020.ndvi;
  const ndvi2021 = result2021.ndvi;

  if (ndvi2020 === null || ndvi2021 === null || isNaN(ndvi2020) || isNaN(ndvi2021)) {
    console.log("C3"); // Calculation failed, result is None or NaN
    return;
  }

  if (ndvi2021 > ndvi2020) {
    console.log("A"); // Greener in 2021
  } else {
    console.log("B"); // Not greener in 2021 (i.e., less green or same)
  }
}

// Boilerplate for Earth Engine authentication and initialization
async function initEE() {
  const privateKey = require('./.earthsense-436113-b294c5f5c2dc.json'); // Ensure this path is correct
  await new Promise((resolve, reject) => {
    ee.data.authenticateViaPrivateKey(privateKey, resolve, reject);
  });
  await new Promise((resolve, reject) => {
    ee.initialize(null, null, resolve, reject);
  });
  await runAnalysis();
}

initEE();