'use strict';

// ================================================================
// EXPORT
// ================================================================
var exportBtn = document.getElementById('export-btn');
var exportDropdownPanel = document.getElementById('export-dropdown-panel');
var exportDropdownOpen = false;

exportBtn.onclick = function(e) {
  e.stopPropagation();
  if (exportDropdownOpen) {
    closeExportDropdown();
  } else {
    openExportDropdown();
  }
};

function openExportDropdown() {
  exportDropdownOpen = true;
  renderExportDropdown();
  exportDropdownPanel.style.display = '';
  setTimeout(function() {
    document.addEventListener('mousedown', _closeExportOutside);
  }, 0);
}

function closeExportDropdown() {
  exportDropdownOpen = false;
  exportDropdownPanel.style.display = 'none';
  document.removeEventListener('mousedown', _closeExportOutside);
}

function _closeExportOutside(e) {
  var dd = document.getElementById('export-dropdown');
  if (dd && !dd.contains(e.target)) {
    closeExportDropdown();
  }
}

function renderExportDropdown() {
  exportDropdownPanel.innerHTML = '';

  var studyLabel = state.activeStudyFilter || null;
  var label = studyLabel ? studyLabel : 'all studies';

  // HTML export
  var htmlItem = document.createElement('button');
  htmlItem.className = 'export-dropdown-item';
  htmlItem.innerHTML = '<span class="export-icon">&#128196;</span> Export as HTML';
  htmlItem.onclick = function(e) {
    e.stopPropagation();
    closeExportDropdown();
    exportStudy(studyLabel, 'html');
  };
  exportDropdownPanel.appendChild(htmlItem);

  // JSON export
  var jsonItem = document.createElement('button');
  jsonItem.className = 'export-dropdown-item';
  jsonItem.innerHTML = '<span class="export-icon">&#128230;</span> Export as JSON';
  jsonItem.onclick = function(e) {
    e.stopPropagation();
    closeExportDropdown();
    exportStudy(studyLabel, 'json');
  };
  exportDropdownPanel.appendChild(jsonItem);

  // Separator
  var sep = document.createElement('div');
  sep.className = 'export-dropdown-sep';
  exportDropdownPanel.appendChild(sep);

  // Print
  var printItem = document.createElement('button');
  printItem.className = 'export-dropdown-item';
  printItem.innerHTML = '<span class="export-icon">&#128424;</span> Print (Ctrl+P)';
  printItem.onclick = function(e) {
    e.stopPropagation();
    closeExportDropdown();
    window.print();
  };
  exportDropdownPanel.appendChild(printItem);
}

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
