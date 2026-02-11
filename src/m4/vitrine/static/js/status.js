'use strict';

// ================================================================
// UI HELPERS — status, card count, session info, scroll
// ================================================================
function updateStatus(status) {
  var dotClass = status === 'connected' ? 'status-connected'
    : status === 'disconnected' ? 'status-disconnected'
    : 'status-connecting';
  var label = status.charAt(0).toUpperCase() + status.slice(1);
  statusEl.innerHTML = '<span class="status-dot ' + dotClass + '"></span> ' + label;
}

function updateCardCount() {
  var all = feed.querySelectorAll('.card');
  var inScope = 0;   // cards matching current study filter
  var visible = 0;   // matching filter AND not dismissed
  all.forEach(function(el) {
    if (!el.classList.contains('hidden-by-filter')) {
      inScope++;
      if (!el.classList.contains('hidden-by-dismiss')) visible++;
    }
  });
  var text = visible + ' card' + (visible !== 1 ? 's' : '');
  if (visible !== inScope) {
    text += ' (' + (inScope - visible) + ' hidden)';
  }
  cardCountEl.textContent = text;

  // Footer: show study label or study count
  if (state.activeStudyFilter) {
    var study = null;
    for (var i = 0; i < state.studies.length; i++) {
      if (state.studies[i].label === state.activeStudyFilter) { study = state.studies[i]; break; }
    }
    if (study && study.start_time) {
      sessionInfoEl.textContent = state.activeStudyFilter + ' \u00b7 ' + dateGroupLabel(study.start_time);
    } else {
      sessionInfoEl.textContent = state.activeStudyFilter;
    }
  } else {
    var totalStudies = state.studies.length;
    sessionInfoEl.textContent = totalStudies > 0 ? totalStudies + ' stud' + (totalStudies !== 1 ? 'ies' : 'y') : '';
  }
}

function loadSessionInfo() {
  fetch('/api/session')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var sid = (data.session_id || '').substring(0, 8);
      sessionInfoEl.textContent = sid ? 'session: ' + sid : '';
    })
    .catch(function() {});
}

function loadStudies() {
  fetch('/api/studies')
    .then(function(r) { return r.json(); })
    .then(function(studies) {
      if (!Array.isArray(studies)) return;
      state.studies = studies;
      state.studyNames = [];
      studies.forEach(function(study) {
        var label = study.label || study.dir_name || '';
        if (label && state.studyNames.indexOf(label) === -1) state.studyNames.push(label);
      });

      // Validate current filter still exists
      if (state.activeStudyFilter && state.studyNames.indexOf(state.activeStudyFilter) === -1) {
        state.activeStudyFilter = '';
        updateDropdownTrigger();
      }

      // Auto-select most recent study on first load
      if (!state.liveMode && !state.activeStudyFilter && studies.length > 0) {
        state.activeStudyFilter = studies[0].label;
        updateDropdownTrigger();
        applyStudyFilter();
        updateStudyMetadataBar();
        if (typeof loadFiles === 'function') loadFiles(studies[0].label);
      }

      updateCardCount();
      // Re-check metadata bar now that state.studies is populated
      // (fixes live mode where updateStudyMetadataBar ran before fetch completed)
      if (state.activeStudyFilter) {
        updateStudyMetadataBar();
      }

      // Update empty state
      if (studies.length === 0 && state.cards.length === 0) {
        showEmptyState();
      }
    })
    .catch(function() {});
}

function scrollToBottom() {
  scrollToLatestCard();
}

function scrollToLatestCard() {
  requestAnimationFrame(function() {
    var cards = feed.querySelectorAll('.card:not(.hidden-by-filter):not(.hidden-by-dismiss), .section-divider:not(.hidden-by-filter)');
    var last = cards.length ? cards[cards.length - 1] : null;
    if (last) {
      last.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }
  });
}

// ================================================================
// BROWSER NOTIFICATIONS
// ================================================================
var _chimeCtx = null;
document.addEventListener('click', function() {
  if (!_chimeCtx) {
    _chimeCtx = new (window.AudioContext || window.webkitAudioContext)();
  } else if (_chimeCtx.state === 'suspended') {
    _chimeCtx.resume();
  }
}, { once: false });

function playDecisionChime() {
  try {
    if (!_chimeCtx) _chimeCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (_chimeCtx.state === 'suspended') _chimeCtx.resume();
    var osc = _chimeCtx.createOscillator();
    var gain = _chimeCtx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 1318.51;
    gain.gain.setValueAtTime(0.18, _chimeCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, _chimeCtx.currentTime + 0.25);
    osc.connect(gain);
    gain.connect(_chimeCtx.destination);
    osc.start();
    osc.stop(_chimeCtx.currentTime + 0.25);
  } catch (e) { /* AudioContext unavailable */ }
}

function notifyDecisionCard(cardData) {
  playDecisionChime();
  if (!document.hidden) return;
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') {
    var title = cardData.title || 'Decision needed';
    var body = cardData.prompt || 'A card is waiting for your response.';
    new Notification(title, { body: body, icon: '/static/favicon.ico' });
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then(function(perm) {
      if (perm === 'granted') {
        var title = cardData.title || 'Decision needed';
        var body = cardData.prompt || 'A card is waiting for your response.';
        new Notification(title, { body: body, icon: '/static/favicon.ico' });
      }
    });
  }
}
