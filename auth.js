// // Require client library and private key.
var ee = require('@google/earthengine');
var privateKey = require('./.earthsense-436113-b294c5f5c2dc.json');

// Initialize client library and run analysis.
var runAnalysis = function() {
  ee.initialize(null, null, function() {
    // ... run analysis ...
  }, function(e) {
    console.error('Initialization error: ' + e);
  });
};

// Authenticate using a service account.
ee.data.authenticateViaPrivateKey(privateKey, runAnalysis, function(e) {
  console.error('Authentication error: ' + e);
});