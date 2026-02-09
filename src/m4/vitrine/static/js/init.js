'use strict';

// ================================================================
// INIT
// ================================================================
var _origLoadRuns = loadRuns;
loadRuns = function() {
  _origLoadRuns();
  // After runs load, check for deep link
  setTimeout(function() { applyHashRun(); }, 600);
};

connect();
