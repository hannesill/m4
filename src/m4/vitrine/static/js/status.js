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
  var visible = 0;
  all.forEach(function(el) {
    if (!el.classList.contains('hidden-by-filter')) visible++;
  });
  var text = visible + ' card' + (visible !== 1 ? 's' : '');
  if (visible !== all.length) {
    text += ' (of ' + all.length + ')';
  }
  cardCountEl.textContent = text;

  // Footer: show run label or run count
  if (state.activeRunFilter) {
    var run = null;
    for (var i = 0; i < state.runs.length; i++) {
      if (state.runs[i].label === state.activeRunFilter) { run = state.runs[i]; break; }
    }
    if (run && run.start_time) {
      sessionInfoEl.textContent = state.activeRunFilter + ' \u00b7 ' + dateGroupLabel(run.start_time);
    } else {
      sessionInfoEl.textContent = state.activeRunFilter;
    }
  } else {
    var totalRuns = state.runs.length;
    sessionInfoEl.textContent = totalRuns > 0 ? totalRuns + ' run' + (totalRuns !== 1 ? 's' : '') : '';
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

function loadRuns() {
  fetch('/api/runs')
    .then(function(r) { return r.json(); })
    .then(function(runs) {
      if (!Array.isArray(runs)) return;
      state.runs = runs;
      state.runIds = [];
      runs.forEach(function(run) {
        var label = run.label || run.dir_name || '';
        if (label && state.runIds.indexOf(label) === -1) state.runIds.push(label);
      });

      // Validate current filter still exists
      if (state.activeRunFilter && state.runIds.indexOf(state.activeRunFilter) === -1) {
        state.activeRunFilter = '';
        updateDropdownTrigger();
      }

      // Auto-select most recent run on first load
      if (!state.liveMode && !state.activeRunFilter && runs.length > 0) {
        state.activeRunFilter = runs[0].label;
        updateDropdownTrigger();
        applyRunFilter();
        updateRunMetadataBar();
      }

      updateCardCount();

      // Update empty state
      if (runs.length === 0 && state.cards.length === 0) {
        showEmptyState();
      }
    })
    .catch(function() {});
}

function scrollToBottom() {
  requestAnimationFrame(function() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  });
}

// ================================================================
// AGENT STATUS & BROWSER NOTIFICATIONS
// ================================================================
var agentStatusEl = document.getElementById('agent-status');

function updateAgentStatus(text) {
  if (agentStatusEl) agentStatusEl.textContent = text;
}

function notifyDecisionCard(cardData) {
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
