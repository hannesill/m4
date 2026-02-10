'use strict';

// ================================================================
// STUDY MANAGEMENT — dropdown, selection, metadata, rename, delete
// ================================================================
studyDropdownTrigger.onclick = function(e) {
  e.stopPropagation();
  if (state.dropdownOpen) {
    closeDropdown();
  } else {
    openDropdown();
  }
};

function openDropdown() {
  state.dropdownOpen = true;
  studyDropdownTrigger.classList.add('open');
  studyDropdownTrigger.setAttribute('aria-expanded', 'true');
  renderDropdown();
  studyDropdownPanel.style.display = '';
  // Close on outside click
  setTimeout(function() {
    document.addEventListener('mousedown', _closeDropdownOutside);
  }, 0);
}

function closeDropdown() {
  state.dropdownOpen = false;
  studyDropdownTrigger.classList.remove('open');
  studyDropdownTrigger.setAttribute('aria-expanded', 'false');
  studyDropdownPanel.style.display = 'none';
  document.removeEventListener('mousedown', _closeDropdownOutside);
}

function _closeDropdownOutside(e) {
  var dd = document.getElementById('study-dropdown');
  if (dd && !dd.contains(e.target)) {
    closeDropdown();
  }
}


function renderDropdown() {
  studyDropdownPanel.innerHTML = '';

  // "All studies" option
  var allOpt = document.createElement('div');
  allOpt.className = 'study-dropdown-all' + (!state.activeStudyFilter ? ' selected' : '');
  allOpt.textContent = 'All studies';
  allOpt.onclick = function(e) {
    e.stopPropagation();
    selectStudy('');
  };
  studyDropdownPanel.appendChild(allOpt);

  if (state.studies.length === 0) {
    var emptyMsg = document.createElement('div');
    emptyMsg.className = 'study-dropdown-empty';
    emptyMsg.textContent = 'No studies yet';
    studyDropdownPanel.appendChild(emptyMsg);
    return;
  }

  // Group studies by date
  var groupOrder = [];
  var groups = {};
  state.studies.forEach(function(study) {
    var gl = dateGroupLabel(study.start_time);
    if (!groups[gl]) {
      groups[gl] = [];
      groupOrder.push(gl);
    }
    groups[gl].push(study);
  });

  groupOrder.forEach(function(groupLabel) {
    var gh = document.createElement('div');
    gh.className = 'study-dropdown-group-label';
    gh.textContent = groupLabel;
    studyDropdownPanel.appendChild(gh);

    groups[groupLabel].forEach(function(study) {
      var entry = document.createElement('div');
      entry.className = 'study-dropdown-entry' + (state.activeStudyFilter === study.label ? ' selected' : '');

      var dot = document.createElement('span');
      dot.className = 'study-dot ' + (state.activeStudy === study.label ? 'active' : 'inactive');
      entry.appendChild(dot);

      var labelEl = document.createElement('span');
      labelEl.className = 'study-entry-label';
      labelEl.textContent = study.label;
      entry.appendChild(labelEl);

      var meta = document.createElement('span');
      meta.className = 'study-entry-meta';
      meta.textContent = (study.card_count || 0) + ' cards';
      if (study.start_time) meta.textContent += '  ' + formatStudyTime(study.start_time);
      entry.appendChild(meta);

      var expBtn = document.createElement('button');
      expBtn.type = 'button';
      expBtn.className = 'study-export-btn';
      expBtn.innerHTML = '&#8615;';
      expBtn.title = 'Export study';
      expBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        exportStudy(study.label, 'html');
        closeDropdown();
      });
      entry.appendChild(expBtn);

      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'study-delete-btn';
      delBtn.innerHTML = '&times;';
      delBtn.title = 'Delete study';
      delBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        deleteStudy(study.label);
      });
      entry.appendChild(delBtn);

      entry.onclick = function(e) {
        e.stopPropagation();
        selectStudy(study.label);
      };
      studyDropdownPanel.appendChild(entry);
    });
  });
}

function selectStudy(label) {
  state.activeStudyFilter = label;
  closeDropdown();
  updateDropdownTrigger();
  applyStudyFilter();
  updateStudyMetadataBar();
  // Load files for the selected study
  if (typeof loadFiles === 'function') loadFiles(label);
  // Update URL hash for deep linking (preserve card fragment if present)
  var h = parseHash();
  var hashParts = [];
  if (label) hashParts.push('study=' + encodeURIComponent(label));
  if (h.card) hashParts.push('card=' + encodeURIComponent(h.card));
  if (hashParts.length > 0) {
    history.replaceState(null, '', '#' + hashParts.join('&'));
  } else {
    history.replaceState(null, '', location.pathname + location.search);
  }
}

function updateDropdownTrigger() {
  if (state.activeStudyFilter) {
    studyDropdownLabel.textContent = state.activeStudyFilter;
  } else {
    studyDropdownLabel.textContent = 'All studies';
  }
}

function updateStudyMetadataBar() {
  if (!state.activeStudyFilter) {
    studyMetaBar.classList.remove('visible');
    return;
  }
  var study = null;
  for (var i = 0; i < state.studies.length; i++) {
    if (state.studies[i].label === state.activeStudyFilter) {
      study = state.studies[i];
      break;
    }
  }
  if (!study) {
    studyMetaBar.classList.remove('visible');
    return;
  }
  studyMetaLabel.textContent = study.label;
  var parts = [];
  if (study.card_count !== undefined) parts.push(study.card_count + ' card' + (study.card_count !== 1 ? 's' : ''));
  if (study.start_time) parts.push(new Date(study.start_time).toLocaleDateString());
  studyMetaDetail.textContent = parts.join(' \u00b7 ');
  studyMetaBar.classList.add('visible');
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

function deleteStudy(label) {
  showConfirmModal(
    'Delete study',
    'Delete "' + label + '"? This cannot be undone.',
    'Delete',
    function() {
      closeDropdown();
      fetch('/api/studies/' + encodeURIComponent(label), { method: 'DELETE' })
        .then(function(r) {
          if (!r.ok) throw new Error('Server returned ' + r.status);
          return r.json();
        })
        .then(function(data) {
          if (data.status === 'ok') {
            state.studies = state.studies.filter(function(s) { return s.label !== label; });
            state.studyNames = state.studyNames.filter(function(id) { return id !== label; });
            var cards = feed.querySelectorAll('.card[data-study="' + label + '"], .section-divider[data-study="' + label + '"], .study-separator[data-study-separator="' + label + '"]');
            cards.forEach(function(el) { el.remove(); });
            state.cards = state.cards.filter(function(c) { return c.study !== label; });
            if (state.activeStudyFilter === label) {
              selectStudy('');
            } else {
              renderDropdown();
            }
            updateCardCount();
            showToast('Study deleted');
            if (state.cards.length === 0) showEmptyState();
          } else {
            showToast(data.error || 'Delete failed');
          }
        })
        .catch(function(err) {
          console.error('Delete study error:', err);
          showToast('Failed to delete study');
        });
    }
  );
}

function startEditStudyName() {
  // Only works when a specific study is selected
  if (!state.activeStudyFilter) return;
  // Prevent double-edit
  if (studyMetaBar.querySelector('.study-meta-edit-wrap')) return;

  var study = null;
  for (var i = 0; i < state.studies.length; i++) {
    if (state.studies[i].label === state.activeStudyFilter) { study = state.studies[i]; break; }
  }
  if (!study) return;

  var originalLabel = study.label;
  studyMetaLabel.style.display = 'none';

  var wrap = document.createElement('span');
  wrap.className = 'study-meta-edit-wrap';

  var input = document.createElement('input');
  input.type = 'text';
  input.className = 'study-meta-edit-input';
  input.value = originalLabel;
  wrap.appendChild(input);

  var hintEl = document.createElement('span');
  hintEl.className = 'study-meta-edit-hint';
  wrap.appendChild(hintEl);

  studyMetaLabel.parentNode.insertBefore(wrap, studyMetaLabel);
  input.focus();
  input.select();

  function validate(val) {
    val = val.trim();
    if (!val) return 'Name cannot be empty';
    if (val === originalLabel) return '';
    for (var i = 0; i < state.studies.length; i++) {
      if (state.studies[i].label === val) return 'Name already in use';
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

    fetch('/api/studies/' + encodeURIComponent(originalLabel) + '/rename', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_label: newLabel })
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'ok') {
          study.label = newLabel;
          state.studyNames = state.studyNames.map(function(id) { return id === originalLabel ? newLabel : id; });
          state.cards.forEach(function(c) { if (c.study === originalLabel) c.study = newLabel; });
          var els = feed.querySelectorAll('[data-study="' + originalLabel + '"]');
          els.forEach(function(el) { el.setAttribute('data-study', newLabel); });
          var seps = feed.querySelectorAll('[data-study-separator="' + originalLabel + '"]');
          seps.forEach(function(el) { el.setAttribute('data-study-separator', newLabel); });
          state.activeStudyFilter = newLabel;
          updateDropdownTrigger();
          showToast('Study renamed');
        } else {
          showToast(data.error || 'Rename failed');
        }
        cleanup();
      })
      .catch(function() { showToast('Failed to rename study'); cleanup(); });
  }

  function cleanup() {
    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    studyMetaLabel.style.display = '';
    studyMetaLabel.textContent = study.label;
  }

  var _blurTimeout = null;
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); if (_blurTimeout) { clearTimeout(_blurTimeout); _blurTimeout = null; } commit(); }
    if (e.key === 'Escape') { e.preventDefault(); if (_blurTimeout) { clearTimeout(_blurTimeout); _blurTimeout = null; } cleanup(); }
  });
  input.addEventListener('blur', function() { _blurTimeout = setTimeout(commit, 100); });
}

// Click the study title in the metadata bar to rename
studyMetaLabel.addEventListener('click', startEditStudyName);

function trackStudy(studyName) {
  if (!studyName || state.studyNames.indexOf(studyName) !== -1) return;
  state.studyNames.push(studyName);
}

function insertStudySeparators() {
  // Remove existing separators
  feed.querySelectorAll('.study-separator').forEach(function(el) { el.remove(); });

  var items = feed.querySelectorAll('.card, .section-divider');
  var lastStudy = null;

  items.forEach(function(el) {
    var studyName = el.dataset.study || '';
    if (studyName && studyName !== lastStudy) {
      var study = null;
      for (var i = 0; i < state.studies.length; i++) {
        if (state.studies[i].label === studyName) { study = state.studies[i]; break; }
      }
      var sep = document.createElement('div');
      sep.className = 'study-separator';
      sep.dataset.studySeparator = studyName;
      var text = studyName;
      if (study && study.start_time) text += ' \u00b7 ' + dateGroupLabel(study.start_time) + ' ' + formatStudyTime(study.start_time);
      if (study && study.card_count) text += ' \u00b7 ' + study.card_count + ' cards';
      sep.textContent = text;
      el.parentNode.insertBefore(sep, el);
      lastStudy = studyName;
    } else if (studyName) {
      lastStudy = studyName;
    }
  });
}

function applyStudyFilter() {
  var filter = state.activeStudyFilter;

  // Remove existing study separators first
  feed.querySelectorAll('.study-separator').forEach(function(el) { el.remove(); });

  var items = feed.querySelectorAll('.card, .section-divider');

  if (!filter) {
    // "All studies" mode: show everything, add study separators
    items.forEach(function(el) { el.classList.remove('hidden-by-filter'); });
    if (items.length > 0) insertStudySeparators();
  } else {
    // Specific study: show matching cards only
    items.forEach(function(el) {
      var elStudy = el.dataset.study || '';
      if (elStudy === filter || !elStudy) {
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
function parseHash() {
  var hash = location.hash || '';
  if (!hash || hash === '#') return { study: null, card: null };
  var params = hash.substring(1).split('&');
  var result = { study: null, card: null };
  for (var i = 0; i < params.length; i++) {
    var parts = params[i].split('=');
    if (parts[0] === 'study' && parts[1]) {
      result.study = decodeURIComponent(parts[1]);
    } else if (parts[0] === 'card' && parts[1]) {
      result.card = decodeURIComponent(parts[1]);
    }
  }
  return result;
}

function applyHashCard(cardParam) {
  var idPrefix = cardParam.split('-')[0];
  var el = null;
  var cards = feed.querySelectorAll('.card[data-card-id]');
  for (var i = 0; i < cards.length; i++) {
    if (cards[i].dataset.cardId.indexOf(idPrefix) === 0) {
      el = cards[i];
      break;
    }
  }
  if (!el) {
    state.pendingCardScroll = idPrefix;
    return;
  }
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('card-highlight');
  void el.offsetWidth;
  el.classList.add('card-highlight');
  setTimeout(function() { el.classList.remove('card-highlight'); }, 2200);
}

function applyHash() {
  var h = parseHash();
  if (h.study) {
    var exists = state.studies.some(function(s) { return s.label === h.study; }) ||
                 state.studyNames.indexOf(h.study) !== -1;
    if (exists && state.activeStudyFilter !== h.study) {
      selectStudy(h.study);
    }
  }
  if (h.card) {
    // Small delay to let study filter settle before scrolling
    setTimeout(function() { applyHashCard(h.card); }, 200);
  }
}

window.addEventListener('hashchange', function() {
  applyHash();
});
