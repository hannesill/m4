'use strict';

// ================================================================
// RUN MANAGEMENT — dropdown, selection, metadata, rename, delete
// ================================================================
runDropdownTrigger.onclick = function(e) {
  e.stopPropagation();
  if (state.dropdownOpen) {
    closeDropdown();
  } else {
    openDropdown();
  }
};

function openDropdown() {
  state.dropdownOpen = true;
  runDropdownTrigger.classList.add('open');
  runDropdownTrigger.setAttribute('aria-expanded', 'true');
  renderDropdown();
  runDropdownPanel.style.display = '';
  // Close on outside click
  setTimeout(function() {
    document.addEventListener('mousedown', _closeDropdownOutside);
  }, 0);
}

function closeDropdown() {
  state.dropdownOpen = false;
  runDropdownTrigger.classList.remove('open');
  runDropdownTrigger.setAttribute('aria-expanded', 'false');
  runDropdownPanel.style.display = 'none';
  document.removeEventListener('mousedown', _closeDropdownOutside);
}

function _closeDropdownOutside(e) {
  var dd = document.getElementById('run-dropdown');
  if (dd && !dd.contains(e.target)) {
    closeDropdown();
  }
}


function renderDropdown() {
  runDropdownPanel.innerHTML = '';

  // "All runs" option
  var allOpt = document.createElement('div');
  allOpt.className = 'run-dropdown-all' + (!state.activeRunFilter ? ' selected' : '');
  allOpt.textContent = 'All runs';
  allOpt.onclick = function(e) {
    e.stopPropagation();
    selectRun('');
  };
  runDropdownPanel.appendChild(allOpt);

  if (state.runs.length === 0) {
    var emptyMsg = document.createElement('div');
    emptyMsg.className = 'run-dropdown-empty';
    emptyMsg.textContent = 'No runs yet';
    runDropdownPanel.appendChild(emptyMsg);
    return;
  }

  // Group runs by date
  var groupOrder = [];
  var groups = {};
  state.runs.forEach(function(run) {
    var gl = dateGroupLabel(run.start_time);
    if (!groups[gl]) {
      groups[gl] = [];
      groupOrder.push(gl);
    }
    groups[gl].push(run);
  });

  groupOrder.forEach(function(groupLabel) {
    var gh = document.createElement('div');
    gh.className = 'run-dropdown-group-label';
    gh.textContent = groupLabel;
    runDropdownPanel.appendChild(gh);

    groups[groupLabel].forEach(function(run) {
      var entry = document.createElement('div');
      entry.className = 'run-dropdown-entry' + (state.activeRunFilter === run.label ? ' selected' : '');

      var dot = document.createElement('span');
      dot.className = 'run-dot ' + (state.activeRunId === run.label ? 'active' : 'inactive');
      entry.appendChild(dot);

      var labelEl = document.createElement('span');
      labelEl.className = 'run-entry-label';
      labelEl.textContent = run.label;
      entry.appendChild(labelEl);

      var meta = document.createElement('span');
      meta.className = 'run-entry-meta';
      meta.textContent = (run.card_count || 0) + ' cards';
      if (run.start_time) meta.textContent += '  ' + formatRunTime(run.start_time);
      entry.appendChild(meta);

      var expBtn = document.createElement('button');
      expBtn.type = 'button';
      expBtn.className = 'run-export-btn';
      expBtn.innerHTML = '&#8615;';
      expBtn.title = 'Export run';
      expBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        exportRun(run.label, 'html');
        closeDropdown();
      });
      entry.appendChild(expBtn);

      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'run-delete-btn';
      delBtn.innerHTML = '&times;';
      delBtn.title = 'Delete run';
      delBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        deleteRun(run.label);
      });
      entry.appendChild(delBtn);

      entry.onclick = function(e) {
        e.stopPropagation();
        selectRun(run.label);
      };
      runDropdownPanel.appendChild(entry);
    });
  });
}

function selectRun(label) {
  state.activeRunFilter = label;
  closeDropdown();
  updateDropdownTrigger();
  applyRunFilter();
  updateRunMetadataBar();
  // Update URL hash for deep linking
  if (label) {
    history.replaceState(null, '', '#run=' + encodeURIComponent(label));
  } else {
    history.replaceState(null, '', location.pathname + location.search);
  }
}

function updateDropdownTrigger() {
  if (state.activeRunFilter) {
    runDropdownLabel.textContent = state.activeRunFilter;
  } else {
    runDropdownLabel.textContent = 'All runs';
  }
}

function updateRunMetadataBar() {
  if (!state.activeRunFilter) {
    runMetaBar.classList.remove('visible');
    return;
  }
  var run = null;
  for (var i = 0; i < state.runs.length; i++) {
    if (state.runs[i].label === state.activeRunFilter) {
      run = state.runs[i];
      break;
    }
  }
  if (!run) {
    runMetaBar.classList.remove('visible');
    return;
  }
  runMetaLabel.textContent = run.label;
  var parts = [];
  if (run.card_count !== undefined) parts.push(run.card_count + ' card' + (run.card_count !== 1 ? 's' : ''));
  if (run.start_time) parts.push(new Date(run.start_time).toLocaleDateString());
  runMetaDetail.textContent = parts.join(' \u00b7 ');
  runMetaBar.classList.add('visible');
}

function showConfirmModal(title, message, confirmLabel, onConfirm) {
  var overlay = document.createElement('div');
  overlay.className = 'confirm-overlay';
  var dialog = document.createElement('div');
  dialog.className = 'confirm-dialog';
  dialog.innerHTML = '<h3></h3><p></p><div class="confirm-actions"><button class="confirm-cancel">Cancel</button><button class="confirm-danger"></button></div>';
  dialog.querySelector('h3').textContent = title;
  dialog.querySelector('p').textContent = message;
  dialog.querySelector('.confirm-danger').textContent = confirmLabel;
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  function dismiss() { overlay.remove(); }
  overlay.addEventListener('click', function(e) { if (e.target === overlay) dismiss(); });
  dialog.querySelector('.confirm-cancel').onclick = dismiss;
  dialog.querySelector('.confirm-danger').onclick = function() { dismiss(); onConfirm(); };
  dialog.querySelector('.confirm-danger').focus();

  // Esc to cancel
  function onKey(e) { if (e.key === 'Escape') { dismiss(); document.removeEventListener('keydown', onKey); } }
  document.addEventListener('keydown', onKey);
}

function deleteRun(label) {
  showConfirmModal(
    'Delete run',
    'Delete "' + label + '"? This cannot be undone.',
    'Delete',
    function() {
      closeDropdown();
      fetch('/api/runs/' + encodeURIComponent(label), { method: 'DELETE' })
        .then(function(r) {
          if (!r.ok) throw new Error('Server returned ' + r.status);
          return r.json();
        })
        .then(function(data) {
          if (data.status === 'ok') {
            state.runs = state.runs.filter(function(r) { return r.label !== label; });
            state.runIds = state.runIds.filter(function(id) { return id !== label; });
            var cards = feed.querySelectorAll('.card[data-run-id="' + label + '"], .section-divider[data-run-id="' + label + '"], .run-separator[data-run-separator="' + label + '"]');
            cards.forEach(function(el) { el.remove(); });
            state.cards = state.cards.filter(function(c) { return c.run_id !== label; });
            if (state.activeRunFilter === label) {
              selectRun('');
            } else {
              renderDropdown();
            }
            updateCardCount();
            showToast('Run deleted');
            if (state.cards.length === 0) showEmptyState();
          } else {
            showToast(data.error || 'Delete failed');
          }
        })
        .catch(function(err) {
          console.error('Delete run error:', err);
          showToast('Failed to delete run');
        });
    }
  );
}

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

  var runLabel = state.activeRunFilter || null;
  var label = runLabel ? runLabel : 'all runs';

  // HTML export
  var htmlItem = document.createElement('button');
  htmlItem.className = 'export-dropdown-item';
  htmlItem.innerHTML = '<span class="export-icon">&#128196;</span> Export as HTML';
  htmlItem.onclick = function(e) {
    e.stopPropagation();
    closeExportDropdown();
    exportRun(runLabel, 'html');
  };
  exportDropdownPanel.appendChild(htmlItem);

  // JSON export
  var jsonItem = document.createElement('button');
  jsonItem.className = 'export-dropdown-item';
  jsonItem.innerHTML = '<span class="export-icon">&#128230;</span> Export as JSON';
  jsonItem.onclick = function(e) {
    e.stopPropagation();
    closeExportDropdown();
    exportRun(runLabel, 'json');
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

function exportRun(runLabel, format) {
  var url;
  if (runLabel) {
    url = '/api/runs/' + encodeURIComponent(runLabel) + '/export?format=' + format;
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

function startEditRunName() {
  // Only works when a specific run is selected
  if (!state.activeRunFilter) return;
  // Prevent double-edit
  if (runMetaBar.querySelector('.run-meta-edit-wrap')) return;

  var run = null;
  for (var i = 0; i < state.runs.length; i++) {
    if (state.runs[i].label === state.activeRunFilter) { run = state.runs[i]; break; }
  }
  if (!run) return;

  var originalLabel = run.label;
  runMetaLabel.style.display = 'none';

  var wrap = document.createElement('span');
  wrap.className = 'run-meta-edit-wrap';

  var input = document.createElement('input');
  input.type = 'text';
  input.className = 'run-meta-edit-input';
  input.value = originalLabel;
  wrap.appendChild(input);

  var hintEl = document.createElement('span');
  hintEl.className = 'run-meta-edit-hint';
  wrap.appendChild(hintEl);

  runMetaLabel.parentNode.insertBefore(wrap, runMetaLabel);
  input.focus();
  input.select();

  function validate(val) {
    val = val.trim();
    if (!val) return 'Name cannot be empty';
    if (val === originalLabel) return '';
    for (var i = 0; i < state.runs.length; i++) {
      if (state.runs[i].label === val) return 'Name already in use';
    }
    return '';
  }

  input.addEventListener('input', function() {
    var err = validate(input.value);
    if (err) {
      input.classList.add('invalid');
      hintEl.textContent = err;
    } else {
      input.classList.remove('invalid');
      hintEl.textContent = '';
    }
  });

  var committed = false;
  function commit() {
    if (committed) return;
    committed = true;
    var newLabel = input.value.trim();
    var err = validate(newLabel);
    if (err && newLabel !== originalLabel) { cleanup(); return; }
    if (!newLabel || newLabel === originalLabel) { cleanup(); return; }

    fetch('/api/runs/' + encodeURIComponent(originalLabel) + '/rename', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_label: newLabel })
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'ok') {
          run.label = newLabel;
          state.runIds = state.runIds.map(function(id) { return id === originalLabel ? newLabel : id; });
          state.cards.forEach(function(c) { if (c.run_id === originalLabel) c.run_id = newLabel; });
          var els = feed.querySelectorAll('[data-run-id="' + originalLabel + '"]');
          els.forEach(function(el) { el.setAttribute('data-run-id', newLabel); });
          var seps = feed.querySelectorAll('[data-run-separator="' + originalLabel + '"]');
          seps.forEach(function(el) { el.setAttribute('data-run-separator', newLabel); });
          state.activeRunFilter = newLabel;
          updateDropdownTrigger();
          showToast('Run renamed');
        } else {
          showToast(data.error || 'Rename failed');
        }
        cleanup();
      })
      .catch(function() { showToast('Failed to rename run'); cleanup(); });
  }

  function cleanup() {
    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    runMetaLabel.style.display = '';
    runMetaLabel.textContent = run.label;
  }

  var _blurTimeout = null;
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); if (_blurTimeout) { clearTimeout(_blurTimeout); _blurTimeout = null; } commit(); }
    if (e.key === 'Escape') { e.preventDefault(); if (_blurTimeout) { clearTimeout(_blurTimeout); _blurTimeout = null; } cleanup(); }
  });
  input.addEventListener('blur', function() { _blurTimeout = setTimeout(commit, 100); });
}

// Click the run title in the metadata bar to rename
runMetaLabel.addEventListener('click', startEditRunName);

function trackRunId(runId) {
  if (!runId || state.runIds.indexOf(runId) !== -1) return;
  state.runIds.push(runId);
}

function insertRunSeparators() {
  // Remove existing separators
  feed.querySelectorAll('.run-separator').forEach(function(el) { el.remove(); });

  var items = feed.querySelectorAll('.card, .section-divider');
  var lastRunId = null;

  items.forEach(function(el) {
    var runId = el.dataset.runId || '';
    if (runId && runId !== lastRunId) {
      var run = null;
      for (var i = 0; i < state.runs.length; i++) {
        if (state.runs[i].label === runId) { run = state.runs[i]; break; }
      }
      var sep = document.createElement('div');
      sep.className = 'run-separator';
      sep.dataset.runSeparator = runId;
      var text = runId;
      if (run && run.start_time) text += ' \u00b7 ' + dateGroupLabel(run.start_time) + ' ' + formatRunTime(run.start_time);
      if (run && run.card_count) text += ' \u00b7 ' + run.card_count + ' cards';
      sep.textContent = text;
      el.parentNode.insertBefore(sep, el);
      lastRunId = runId;
    } else if (runId) {
      lastRunId = runId;
    }
  });
}

function applyRunFilter() {
  var filter = state.activeRunFilter;

  // Remove existing run separators first
  feed.querySelectorAll('.run-separator').forEach(function(el) { el.remove(); });

  var items = feed.querySelectorAll('.card, .section-divider');

  if (!filter) {
    // "All runs" mode: show everything, add run separators
    items.forEach(function(el) { el.classList.remove('hidden-by-filter'); });
    if (items.length > 0) insertRunSeparators();
  } else {
    // Specific run: show matching cards only
    items.forEach(function(el) {
      var elRun = el.dataset.runId || '';
      if (elRun === filter || !elRun) {
        el.classList.remove('hidden-by-filter');
      } else {
        el.classList.add('hidden-by-filter');
      }
    });
  }

  updateCardCount();
}

// ================================================================
// DEEP-LINK URLs
// ================================================================
function parseHashRun() {
  var hash = location.hash || '';
  var m = hash.match(/^#run=(.+)$/);
  return m ? decodeURIComponent(m[1]) : null;
}

function applyHashRun() {
  var label = parseHashRun();
  if (label) {
    // Check if this run exists
    var exists = state.runs.some(function(r) { return r.label === label; }) ||
                 state.runIds.indexOf(label) !== -1;
    if (exists && state.activeRunFilter !== label) {
      selectRun(label);
    }
  }
}

window.addEventListener('hashchange', function() {
  applyHashRun();
});
