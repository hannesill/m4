'use strict';

// ================================================================
// EXPORT — functions called by actions.js palette
// ================================================================

function exportStudy(studyLabel, format) {
  var url;
  if (studyLabel) {
    url = '/api/studies/' + encodeURIComponent(studyLabel) + '/export?format=' + format;
  } else {
    url = '/api/export?format=' + format;
  }
  // Trigger download
  var a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('Export started');
}
