'use strict';

// ================================================================
// INIT
// ================================================================
var _origLoadStudies = loadStudies;
loadStudies = function() {
  _origLoadStudies();
  // After studies load, check for deep link
  setTimeout(function() { applyHash(); }, 600);
};

connect();
