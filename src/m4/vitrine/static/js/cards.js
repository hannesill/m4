'use strict';

// ================================================================
// MODEL DISPLAY NAMES
// ================================================================
var MODEL_DISPLAY = {
  sonnet: 'Sonnet 4.5',
  opus: 'Opus 4.6',
  haiku: 'Haiku 4.5'
};

var AGENT_THINKING_MESSAGES = [
  'Accomplishing', 'Actioning', 'Actualizing', 'Annotating', 'Auditing',
  'Baking', 'Bootstrapping', 'Brewing', 'Calculating', 'Calibrating',
  'Cerebrating', 'Charting', 'Churning', 'Clauding', 'Coalescing',
  'Cogitating', 'Computing', 'Conjuring', 'Considering', 'Cooking',
  'Correlating', 'Crafting', 'Creating', 'Crunching', 'Curating',
  'Deliberating', 'Determining', 'Doing', 'Effecting', 'Finagling',
  'Forging', 'Forming', 'Generating', 'Hatching', 'Herding', 'Honking',
  'Hustling', 'Hypothesizing', 'Ideating', 'Incubating', 'Inferring',
  'Manifesting', 'Marinating', 'Moseying', 'Mulling', 'Mustering',
  'Musing', 'Noodling', 'Percolating', 'Pipetting', 'Pondering',
  'Processing', 'Puttering', 'Reticulating', 'Ruminating', 'Schlepping',
  'Shucking', 'Simmering', 'Smooshing', 'Spinning', 'Stewing',
  'Stratifying', 'Synthesizing', 'Thinking', 'Titrating', 'Transmuting',
  'Triaging', 'Vibing', 'Working'
];

// ================================================================
// CARD RENDERING — addCard, updateCard, toast
// ================================================================
function addCard(cardData) {
  // Remove empty state if present
  var empty = document.getElementById('empty-state');
  if (empty && empty.parentNode) {
    empty.remove();
  }

  // Deduplicate on reconnect replay
  var existing = document.getElementById('card-' + cardData.card_id);
  if (existing) return;

  state.cards.push(cardData);
  trackStudy(cardData.study);

  // Track active run and auto-switch
  if (cardData.study) {
    state.activeStudy = cardData.study;
    if (state.liveMode && state.activeStudyFilter !== cardData.study) {
      // Auto-switch to the new card's run
      state.activeStudyFilter = cardData.study;
      updateDropdownTrigger();
      // Defer full filter update to batch rapid arrivals
      if (!state._autoSelectPending) {
        state._autoSelectPending = true;
        requestAnimationFrame(function() {
          state._autoSelectPending = false;
          applyStudyFilter();
          updateStudyMetadataBar();
          // Refresh run list to get updated card counts
          loadStudies();
        });
      }
    }
  }

  var el = document.createElement('div');
  el.className = 'card';
  el.id = 'card-' + cardData.card_id;
  el.dataset.study = cardData.study || '';
  el.dataset.cardId = cardData.card_id;

  // Header
  var header = document.createElement('div');
  header.className = 'card-header';
  var headerType = (cardData.response_requested || cardData.response_action) ? 'decision' : cardData.card_type;
  header.setAttribute('data-type', headerType);

  // Collapse toggle
  var collapseBtn = document.createElement('button');
  collapseBtn.className = 'card-collapse-btn';
  collapseBtn.innerHTML = '&#9660;';
  collapseBtn.title = 'Collapse';
  collapseBtn.setAttribute('aria-label', 'Collapse card');
  collapseBtn.onclick = function() {
    var isCollapsed = collapseBtn.classList.toggle('collapsed');
    el.classList.toggle('card-collapsed', isCollapsed);
    collapseBtn.title = isCollapsed ? 'Expand' : 'Collapse';
    collapseBtn.setAttribute('aria-label', isCollapsed ? 'Expand card' : 'Collapse card');
  };
  header.appendChild(collapseBtn);

  // Type icon
  var typeIcon = document.createElement('div');
  typeIcon.className = 'card-type-icon';
  typeIcon.setAttribute('data-type', headerType);
  typeIcon.textContent = TYPE_LETTERS[headerType] || '?';
  header.appendChild(typeIcon);

  // Agent status indicator (pulsing dot for running, checkmark/X for done)
  if (cardData.card_type === 'agent' && cardData.preview) {
    var agentStatus = cardData.preview.status || 'pending';
    if (agentStatus === 'running') {
      var dot = document.createElement('span');
      dot.className = 'agent-status-dot running';
      header.appendChild(dot);
    } else if (agentStatus === 'completed') {
      var check = document.createElement('span');
      check.className = 'agent-status-dot completed';
      check.textContent = '\u2713';
      header.appendChild(check);
    } else if (agentStatus === 'failed') {
      var xmark = document.createElement('span');
      xmark.className = 'agent-status-dot failed';
      xmark.textContent = '\u2717';
      header.appendChild(xmark);
    }
  }

  // Title (click to rename)
  var title = document.createElement('span');
  title.className = 'card-title';
  title.textContent = cardData.title || cardData.card_type;
  title.addEventListener('click', function(e) {
    e.stopPropagation();
    startEditCardTitle(el, cardData.card_id);
  });
  header.appendChild(title);

  // Model badge (agent cards only)
  if (cardData.card_type === 'agent' && cardData.preview) {
    var modelBadge = document.createElement('span');
    modelBadge.className = 'agent-model-badge agent-header-badge';
    modelBadge.textContent = MODEL_DISPLAY[cardData.preview.model] || cardData.preview.model || '';
    if (modelBadge.textContent) header.appendChild(modelBadge);

    // Status reason badge for failed/cancelled agents
    if (cardData.preview.status === 'failed' && cardData.preview.error) {
      var reasonBadge = document.createElement('span');
      reasonBadge.className = 'agent-reason-badge';
      reasonBadge.textContent = cardData.preview.error;
      header.appendChild(reasonBadge);
    }
  }

  // Timestamp / duration / live timer
  var meta = document.createElement('span');
  meta.className = 'card-meta';
  if (cardData.card_type === 'agent' && cardData.preview) {
    var agentPreview = cardData.preview;
    if (agentPreview.status === 'running' && agentPreview.started_at) {
      // Live timer
      meta.textContent = formatElapsed(agentPreview.started_at);
      var timerId = setInterval(function() {
        meta.textContent = formatElapsed(agentPreview.started_at);
      }, 1000);
      el._agentTimer = timerId;
    } else if (agentPreview.duration != null) {
      meta.textContent = formatAgentDuration(agentPreview.duration);
    }
  } else if (cardData.timestamp) {
    meta.textContent = new Date(cardData.timestamp).toLocaleTimeString();
  }
  header.appendChild(meta);

  // Action buttons
  var actions = document.createElement('div');
  actions.className = 'card-actions';

  // Copy prompt button
  var promptBtn = document.createElement('button');
  promptBtn.className = 'card-action-btn copy-prompt-btn';
  promptBtn.title = 'Copy prompt for agent';
  promptBtn.setAttribute('aria-label', 'Copy prompt for agent');
  promptBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="8" height="10" rx="1"/><path d="M3 6v7a1 1 0 001 1h7"/></svg>';
  promptBtn.onclick = function(e) {
    e.stopPropagation();
    var prompt = buildCardPrompt(cardData);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(prompt).then(function() {
        showToast('Prompt copied');
      }, function() {
        showToast('Failed to copy', 'error');
      });
    }
  };
  actions.appendChild(promptBtn);

  // Annotate button
  var annotateBtn = document.createElement('button');
  annotateBtn.className = 'card-action-btn';
  annotateBtn.title = 'Add annotation';
  annotateBtn.setAttribute('aria-label', 'Add annotation');
  annotateBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 14s1-2 1-3V4a2 2 0 012-2h6a2 2 0 012 2v7c0 1 1 3 1 3"/><path d="M6 6h4"/><path d="M6 9h2"/></svg>';
  annotateBtn.onclick = function(e) {
    e.stopPropagation();
    toggleAnnotationForm(el, cardData);
  };
  actions.appendChild(annotateBtn);

  // Dismiss button
  var dismissBtn = document.createElement('button');
  dismissBtn.className = 'card-action-btn dismiss-btn';
  dismissBtn.title = cardData.dismissed ? 'Show card' : 'Hide card';
  dismissBtn.setAttribute('aria-label', cardData.dismissed ? 'Show card' : 'Hide card');
  dismissBtn.innerHTML = cardData.dismissed ? EYE_OFF_SVG : EYE_SVG;
  dismissBtn.onclick = function(e) {
    e.stopPropagation();
    var currentlyDismissed = el.classList.contains('dismissed');
    sendDismissEvent(cardData.card_id, !currentlyDismissed);
  };
  actions.appendChild(dismissBtn);

  // Delete button
  var deleteBtn = document.createElement('button');
  deleteBtn.className = 'card-action-btn delete-btn';
  deleteBtn.title = 'Delete card';
  deleteBtn.setAttribute('aria-label', 'Delete card');
  deleteBtn.innerHTML = TRASH_SVG;
  deleteBtn.onclick = function(e) {
    e.stopPropagation();
    el.classList.add('card-deleting');
    var cleaned = false;
    var cleanup = function() {
      if (cleaned) return;
      cleaned = true;
      el.classList.remove('card-deleting');
      el.classList.add('deleted', 'hidden-by-delete');
      updateCardCount();
      if (typeof tocNotifyChange === 'function') tocNotifyChange();
    };
    el.addEventListener('animationend', cleanup, { once: true });
    setTimeout(cleanup, 400);
    sendDeleteEvent(cardData.card_id, true);
    showUndoSnackbar(cardData.card_id, cardData.title || cardData.card_type);
  };
  actions.appendChild(deleteBtn);

  header.appendChild(actions);
  el.appendChild(header);

  // Description (subtitle / context line below header)
  if (cardData.description) {
    var desc = document.createElement('div');
    desc.className = 'card-description';
    desc.textContent = cardData.description;
    el.appendChild(desc);
  }

  // Body
  var body = document.createElement('div');
  body.className = 'card-body';

  switch (cardData.card_type) {
    case 'table':
      renderTable(body, cardData);
      break;
    case 'plotly':
      renderPlotly(body, cardData);
      break;
    case 'image':
      renderImage(body, cardData);
      break;
    case 'markdown':
      renderMarkdown(body, cardData);
      break;
    case 'decision':
      if (cardData.response_action && cardData.response_values && Object.keys(cardData.response_values).length > 0) {
        renderFrozenForm(body, cardData.response_values, (cardData.preview && cardData.preview.fields) || []);
      } else {
        renderForm(body, cardData);
      }
      break;
    case 'keyvalue':
      renderKeyValue(body, cardData);
      break;
    case 'agent':
      renderAgentCard(body, cardData);
      break;
    case 'section':
      el.remove();
      addSection(cardData.title || (cardData.preview && cardData.preview.title) || '', cardData.study);
      return;
    default:
      body.textContent = JSON.stringify(cardData.preview);
  }

  el.appendChild(body);

  // Controls bar for hybrid data+controls cards (table/chart with controls)
  if (cardData.preview && cardData.preview.controls && cardData.preview.controls.length > 0
      && !cardData.preview.fields) {
    var controlsBar = document.createElement('div');
    controlsBar.className = 'card-controls-bar';
    renderFormFields(controlsBar, cardData.preview.controls);
    el.appendChild(controlsBar);
  }

  // Waiting card: response UI
  if (cardData.response_requested) {
    el.classList.add('waiting');
    var responseUI = buildResponseUI(cardData, el);
    el.appendChild(responseUI);
    notifyDecisionCard(cardData);
  } else if (cardData.response_action) {
    // Already-responded decision card (loaded from disk)
    el.classList.add('responded');
    typeIcon.textContent = '\u2713';
    var badge = document.createElement('span');
    badge.className = 'sent-badge';
    if (cardData.response_action === 'confirm') {
      badge.textContent = 'Confirmed';
    } else if (cardData.response_action === 'skip') {
      badge.textContent = 'Skipped';
    } else {
      badge.textContent = cardData.response_action;
    }
    header.appendChild(badge);
    // Show researcher's note if provided
    if (cardData.response_message && cardData.response_message.trim()) {
      var noteEl = document.createElement('div');
      noteEl.className = 'decision-note';
      noteEl.textContent = cardData.response_message.trim();
      var bodyEl = el.querySelector('.card-body');
      if (bodyEl) bodyEl.appendChild(noteEl);
    }
  }

  // Annotations
  var annotationsContainer = document.createElement('div');
  annotationsContainer.className = 'card-annotations';
  renderAnnotations(annotationsContainer, cardData);
  el.appendChild(annotationsContainer);

  // Provenance
  if (cardData.provenance) {
    var prov = document.createElement('div');
    prov.className = 'card-provenance';
    var parts = [];
    if (cardData.provenance.source) parts.push(cardData.provenance.source);
    if (cardData.provenance.dataset) parts.push(cardData.provenance.dataset);
    if (cardData.provenance.timestamp) {
      parts.push(new Date(cardData.provenance.timestamp).toLocaleString());
    }
    prov.textContent = parts.join(' \u00b7 ');
    if (parts.length > 0) el.appendChild(prov);
  }

  feed.appendChild(el);

  // Apply dismissed state
  if (cardData.dismissed) {
    el.classList.add('dismissed');
    if (!state.showDismissed) {
      el.classList.add('hidden-by-dismiss');
    }
    updateDismissToggleVisibility();
  }

  // Apply deleted state
  if (cardData.deleted) {
    el.classList.add('deleted');
    el.classList.add('hidden-by-delete');
  }

  // Hide card if it lands inside a collapsed section
  if (isInCollapsedSection(el)) {
    el.classList.add('hidden-by-section');
  }

  // Apply study filter to the new card
  if (state.activeStudyFilter) {
    var cardRun = cardData.study || '';
    if (cardRun !== state.activeStudyFilter) {
      el.classList.add('hidden-by-filter');
    }
  }

  updateCardCount();
  if (typeof tocNotifyChange === 'function') tocNotifyChange();

  // Check for pending deep-link scroll (prefix match)
  if (state.pendingCardScroll && cardData.card_id.indexOf(state.pendingCardScroll) === 0) {
    state.pendingCardScroll = null;
    setTimeout(function() { applyHashCard(cardData.card_id); }, 100);
  } else {
    scrollToBottom();
  }
}

function showToast(msg, type) {
  copyToastEl.textContent = msg;
  copyToastEl.classList.remove('toast-error');
  if (type === 'error') copyToastEl.classList.add('toast-error');
  copyToastEl.classList.add('visible');
  setTimeout(function() {
    copyToastEl.classList.remove('visible');
  }, type === 'error' ? 3000 : 1500);
}

// ================================================================
// SECTIONS, CARD UPDATES & STUDY FILTERING
// ================================================================
function addSection(title, study) {
  var empty = document.getElementById('empty-state');
  if (empty && empty.parentNode) {
    empty.remove();
  }

  if (study) trackStudy(study);

  var div = document.createElement('div');
  div.className = 'section-divider';
  div.dataset.study = study || '';

  var chevron = document.createElement('span');
  chevron.className = 'section-chevron';
  chevron.innerHTML = '&#9660;';
  div.appendChild(chevron);

  var titleSpan = document.createElement('span');
  titleSpan.className = 'section-title';
  titleSpan.textContent = title;
  div.appendChild(titleSpan);

  div.addEventListener('click', function() {
    var isCollapsed = div.classList.toggle('section-collapsed');
    toggleSectionCards(div, isCollapsed);
    if (typeof tocNotifyChange === 'function') tocNotifyChange();
  });

  feed.appendChild(div);

  if (state.activeStudyFilter) {
    applyStudyFilter();
  }

  scrollToBottom();
  if (typeof tocNotifyChange === 'function') tocNotifyChange();
}

function toggleSectionCards(sectionEl, collapsed) {
  var next = sectionEl.nextElementSibling;
  while (next && !next.classList.contains('section-divider')) {
    if (collapsed) {
      next.classList.add('hidden-by-section');
    } else {
      next.classList.remove('hidden-by-section');
    }
    next = next.nextElementSibling;
  }
}

function isInCollapsedSection(el) {
  var prev = el.previousElementSibling;
  while (prev) {
    if (prev.classList.contains('section-divider')) {
      return prev.classList.contains('section-collapsed');
    }
    prev = prev.previousElementSibling;
  }
  return false;
}

function startEditCardTitle(cardEl, cardId) {
  var titleEl = cardEl.querySelector('.card-title');
  if (!titleEl || titleEl.style.display === 'none') return;

  var originalTitle = titleEl.textContent;
  titleEl.style.display = 'none';

  var wrap = document.createElement('span');
  wrap.className = 'card-title-edit-wrap';

  var input = document.createElement('input');
  input.type = 'text';
  input.className = 'card-title-edit-input';
  input.value = originalTitle;
  wrap.appendChild(input);

  titleEl.parentNode.insertBefore(wrap, titleEl);
  input.focus();
  input.select();

  var committed = false;
  function commit() {
    if (committed) return;
    committed = true;
    var newTitle = input.value.trim();
    if (!newTitle || newTitle === originalTitle) { cleanup(); return; }

    if (ws && ws.readyState === 1) {
      ws.send(JSON.stringify({
        type: 'vitrine.event',
        event_type: 'rename',
        card_id: cardId,
        payload: { new_title: newTitle }
      }));
    }
    // Optimistic update
    titleEl.textContent = newTitle;
    for (var i = 0; i < state.cards.length; i++) {
      if (state.cards[i].card_id === cardId) {
        state.cards[i].title = newTitle;
        break;
      }
    }
    if (typeof tocNotifyChange === 'function') tocNotifyChange();
    cleanup();
  }

  function cleanup() {
    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    titleEl.style.display = '';
  }

  var _blurTimeout = null;
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); if (_blurTimeout) { clearTimeout(_blurTimeout); _blurTimeout = null; } commit(); }
    if (e.key === 'Escape') { e.preventDefault(); if (_blurTimeout) { clearTimeout(_blurTimeout); _blurTimeout = null; } cleanup(); }
  });
  input.addEventListener('blur', function() { _blurTimeout = setTimeout(commit, 100); });
}

function updateCard(cardId, newCardData) {
  var el = document.getElementById('card-' + cardId);
  if (!el) return;

  // Update state.cards entry (merge into existing, don't replace)
  if (newCardData) {
    for (var i = 0; i < state.cards.length; i++) {
      if (state.cards[i].card_id === cardId) {
        var existing = state.cards[i];
        // Merge top-level fields
        for (var key in newCardData) {
          if (key === 'preview' && existing.preview && newCardData.preview) {
            // Deep merge preview
            for (var pk in newCardData.preview) {
              existing.preview[pk] = newCardData.preview[pk];
            }
          } else {
            existing[key] = newCardData[key];
          }
        }
        newCardData = existing;
        break;
      }
    }

    // Update title
    var titleEl = el.querySelector('.card-title');
    if (titleEl) {
      titleEl.textContent = newCardData.title || newCardData.card_type;
    }

    // Update description
    var descEl = el.querySelector('.card-description');
    if (newCardData.description) {
      if (!descEl) {
        descEl = document.createElement('div');
        descEl.className = 'card-description';
        var headerEl = el.querySelector('.card-header');
        if (headerEl && headerEl.nextSibling) {
          el.insertBefore(descEl, headerEl.nextSibling);
        }
      }
      descEl.textContent = newCardData.description;
    } else if (descEl) {
      descEl.remove();
    }

    var header = el.querySelector('.card-header');
    if (header) {
      var headerType = (newCardData.response_requested || newCardData.response_action) ? 'decision' : newCardData.card_type;
      header.setAttribute('data-type', headerType);
      var typeIcon = header.querySelector('.card-type-icon');
      if (typeIcon) {
        typeIcon.setAttribute('data-type', headerType);
        typeIcon.textContent = newCardData.response_action ? '\u2713' : (TYPE_LETTERS[headerType] || '?');
      }

      // Update agent status indicator in header
      if (newCardData.card_type === 'agent' && newCardData.preview) {
        var oldDot = header.querySelector('.agent-status-dot');
        if (oldDot) oldDot.remove();
        var agentSt = newCardData.preview.status || 'pending';
        if (agentSt === 'running') {
          var dot = document.createElement('span');
          dot.className = 'agent-status-dot running';
          if (typeIcon) typeIcon.insertAdjacentElement('afterend', dot);
        } else if (agentSt === 'completed') {
          var chk = document.createElement('span');
          chk.className = 'agent-status-dot completed';
          chk.textContent = '\u2713';
          if (typeIcon) typeIcon.insertAdjacentElement('afterend', chk);
        } else if (agentSt === 'failed') {
          var xm = document.createElement('span');
          xm.className = 'agent-status-dot failed';
          xm.textContent = '\u2717';
          if (typeIcon) typeIcon.insertAdjacentElement('afterend', xm);
        }

        // Update duration/timer in meta
        var meta = header.querySelector('.card-meta');
        if (meta) {
          var st = newCardData.preview.status || 'pending';
          if (st === 'running' && newCardData.preview.started_at && !el._agentTimer) {
            meta.textContent = formatElapsed(newCardData.preview.started_at);
            el._agentTimer = setInterval(function() {
              meta.textContent = formatElapsed(newCardData.preview.started_at);
            }, 1000);
          } else if (st !== 'running' && newCardData.preview.duration != null) {
            if (el._agentTimer) {
              clearInterval(el._agentTimer);
              el._agentTimer = null;
            }
            meta.textContent = formatAgentDuration(newCardData.preview.duration);
          }
        }

        // Update or add model badge in header
        var existingModelBadge = header.querySelector('.agent-header-badge');
        if (newCardData.preview.model) {
          if (existingModelBadge) {
            existingModelBadge.textContent = MODEL_DISPLAY[newCardData.preview.model] || newCardData.preview.model;
          } else {
            var mb = document.createElement('span');
            mb.className = 'agent-model-badge agent-header-badge';
            mb.textContent = MODEL_DISPLAY[newCardData.preview.model] || newCardData.preview.model;
            var titleAfter = header.querySelector('.card-title');
            if (titleAfter) titleAfter.insertAdjacentElement('afterend', mb);
          }
        }

        // Update or add/remove status reason badge
        var existingReason = header.querySelector('.agent-reason-badge');
        if (newCardData.preview.status === 'failed' && newCardData.preview.error) {
          if (existingReason) {
            existingReason.textContent = newCardData.preview.error;
          } else {
            var rb = document.createElement('span');
            rb.className = 'agent-reason-badge';
            rb.textContent = newCardData.preview.error;
            // Insert after model badge or after title
            var anchor = header.querySelector('.agent-header-badge') || header.querySelector('.card-title');
            if (anchor) anchor.insertAdjacentElement('afterend', rb);
          }
        } else if (existingReason) {
          existingReason.remove();
        }

        // Remove any legacy usage badge from header
        var existingUsage = header.querySelector('.agent-usage-badge');
        if (existingUsage) existingUsage.remove();
      }
    }

    // Re-render body content
    var body = el.querySelector('.card-body');
    if (body) {
      // Agent cards: incremental updates to avoid jitter
      if (newCardData.card_type === 'agent' && newCardData.preview) {
        var newStatus = newCardData.preview.status || 'pending';
        // Detect current rendered state
        var currentState = 'pending';
        if (body.querySelector('.agent-terminal:not(.agent-terminal-compact)') || body.querySelector('.agent-meta-strip')) currentState = 'running';
        else if (body.querySelector('.agent-terminal-compact')) currentState = 'completed';
        else if (body.querySelector('.agent-config')) currentState = 'pending';

        if (currentState === newStatus && newStatus === 'running') {
          // Incremental: just update the terminal content markdown
          var termContent = body.querySelector('.agent-terminal-content');
          if (termContent && newCardData.preview.output) {
            if (typeof marked !== 'undefined') {
              termContent.innerHTML = marked.parse(newCardData.preview.output);
            } else {
              termContent.textContent = newCardData.preview.output;
            }
            // Auto-scroll terminal to bottom
            var termBox = body.querySelector('.agent-terminal');
            if (termBox) {
              requestAnimationFrame(function() { termBox.scrollTop = termBox.scrollHeight; });
            }
          }
          // Update usage info in alive strip
          var aliveUsage = body.querySelector('.agent-alive-usage');
          if (aliveUsage) {
            aliveUsage.textContent = formatAgentUsage(newCardData.preview);
          }
        } else if (currentState !== newStatus) {
          // State transition: clear timers + full re-render
          if (el._agentTimer) {
            clearInterval(el._agentTimer);
            el._agentTimer = null;
          }
          if (el._agentInactivityTimer) {
            clearInterval(el._agentInactivityTimer);
            el._agentInactivityTimer = null;
          }
          body.innerHTML = '';
          renderAgentCard(body, newCardData);

          // Update header badges for new state
          var hdr = el.querySelector('.card-header');
          if (hdr) {
            // Update model badge
            var existingBadge = hdr.querySelector('.agent-header-badge');
            if (!existingBadge && newCardData.preview.model) {
              var mb = document.createElement('span');
              mb.className = 'agent-model-badge agent-header-badge';
              mb.textContent = MODEL_DISPLAY[newCardData.preview.model] || newCardData.preview.model;
              var titleEl2 = hdr.querySelector('.card-title');
              if (titleEl2) titleEl2.insertAdjacentElement('afterend', mb);
            }
            // Update meta (duration or timer)
            var metaEl = hdr.querySelector('.card-meta');
            if (metaEl) {
              if (newStatus === 'running' && newCardData.preview.started_at) {
                metaEl.textContent = formatElapsed(newCardData.preview.started_at);
                el._agentTimer = setInterval(function() {
                  metaEl.textContent = formatElapsed(newCardData.preview.started_at);
                }, 1000);
              } else if (newCardData.preview.duration != null) {
                metaEl.textContent = formatAgentDuration(newCardData.preview.duration);
              }
            }
          }
        }
        // Same state (pending/completed/failed): no re-render needed
      } else {
        body.innerHTML = '';
        switch (newCardData.card_type) {
          case 'table':
            renderTable(body, newCardData);
            break;
          case 'plotly':
            renderPlotly(body, newCardData);
            break;
          case 'image':
            renderImage(body, newCardData);
            break;
          case 'markdown':
            if (newCardData.preview && newCardData.preview.fields) {
              renderForm(body, newCardData);
            } else {
              renderMarkdown(body, newCardData);
            }
            break;
          case 'keyvalue':
            renderKeyValue(body, newCardData);
            break;
          case 'decision':
            if (newCardData.response_action && newCardData.response_values && Object.keys(newCardData.response_values).length > 0) {
              renderFrozenForm(body, newCardData.response_values, (newCardData.preview && newCardData.preview.fields) || []);
            } else {
              renderForm(body, newCardData);
            }
            break;
          case 'agent':
            renderAgentCard(body, newCardData);
            break;
          default:
            body.textContent = JSON.stringify(newCardData.preview);
        }
      }
    }
  }

  // Handle response_requested toggling (e.g. wait_for() re-enabling after timeout)
  if (newCardData) {
    var existingResponseUI = el.querySelector('.card-response-ui');
    if (newCardData.response_requested && !existingResponseUI) {
      // Re-enable: remove responded state and old badges, add fresh response UI
      el.classList.remove('responded');
      el.classList.add('waiting');
      var oldBadge = el.querySelector('.sent-badge');
      if (oldBadge) oldBadge.remove();
      var responseUI = buildResponseUI(newCardData, el);
      el.appendChild(responseUI);
      notifyDecisionCard(newCardData);
    } else if (!newCardData.response_requested && existingResponseUI) {
      // Disable: remove response UI if no longer waiting
      if (existingResponseUI._timer) clearInterval(existingResponseUI._timer);
      existingResponseUI.remove();
      el.classList.remove('waiting');
    }
  }

  // Re-render annotations
  if (newCardData) {
    var annotationsContainer = el.querySelector('.card-annotations');
    if (annotationsContainer) {
      annotationsContainer.innerHTML = '';
      renderAnnotations(annotationsContainer, newCardData);
    }
  }

  // Handle dismissed state (with animation)
  if (newCardData) {
    var isDismissed = !!newCardData.dismissed;
    var wasDismissed = el.classList.contains('dismissed');
    var wasHiddenByDismiss = el.classList.contains('hidden-by-dismiss');

    if (isDismissed && !wasDismissed && !state.showDismissed) {
      // Newly dismissed and should be hidden — animate out
      el.classList.add('card-dismissing');
      var dCleaned = false;
      var dCleanup = function() {
        if (dCleaned) return;
        dCleaned = true;
        el.classList.remove('card-dismissing');
        el.classList.add('dismissed', 'hidden-by-dismiss');
        updateCardCount();
        if (typeof tocNotifyChange === 'function') tocNotifyChange();
      };
      el.addEventListener('animationend', dCleanup, { once: true });
      setTimeout(dCleanup, 350);
    } else if (!isDismissed && wasDismissed) {
      // Undismissed — animate in if was hidden
      el.classList.remove('dismissed');
      if (wasHiddenByDismiss) {
        el.classList.remove('hidden-by-dismiss');
        el.classList.add('card-undismissing');
        var uCleaned = false;
        var uCleanup = function() {
          if (uCleaned) return;
          uCleaned = true;
          el.classList.remove('card-undismissing');
        };
        el.addEventListener('animationend', uCleanup, { once: true });
        setTimeout(uCleanup, 350);
      }
    } else {
      // Sync state (no transition, e.g. initial load or showDismissed toggle)
      el.classList.toggle('dismissed', isDismissed);
      if (isDismissed && !state.showDismissed) {
        el.classList.add('hidden-by-dismiss');
      } else {
        el.classList.remove('hidden-by-dismiss');
      }
    }

    var dBtn = el.querySelector('.dismiss-btn');
    if (dBtn) {
      dBtn.title = isDismissed ? 'Show card' : 'Hide card';
      dBtn.setAttribute('aria-label', isDismissed ? 'Show card' : 'Hide card');
      dBtn.innerHTML = isDismissed ? EYE_OFF_SVG : EYE_SVG;
    }
    updateDismissToggleVisibility();
    updateCardCount();
  }

  // Handle deleted state (with animation)
  if (newCardData) {
    var isDeleted = !!newCardData.deleted;
    if (isDeleted) {
      // Card should be deleted — if already animating or hidden, don't interfere
      if (!el.classList.contains('card-deleting') && !el.classList.contains('hidden-by-delete')) {
        // Server-side delete (not initiated from this client's button)
        el.classList.add('deleted');
        el.classList.add('card-deleting');
        var sdCleaned = false;
        var sdCleanup = function() {
          if (sdCleaned) return;
          sdCleaned = true;
          el.classList.remove('card-deleting');
          el.classList.add('hidden-by-delete');
          updateCardCount();
          if (typeof tocNotifyChange === 'function') tocNotifyChange();
        };
        el.addEventListener('animationend', sdCleanup, { once: true });
        setTimeout(sdCleanup, 400);
      }
      el.classList.add('deleted');
    } else {
      // Restoring a deleted card
      var wasDeleted = el.classList.contains('deleted') || el.classList.contains('hidden-by-delete') || el.classList.contains('card-deleting');
      el.classList.remove('deleted', 'hidden-by-delete', 'card-deleting');
      if (wasDeleted) {
        el.classList.add('card-restoring');
        var rCleaned = false;
        var rCleanup = function() {
          if (rCleaned) return;
          rCleaned = true;
          el.classList.remove('card-restoring');
        };
        el.addEventListener('animationend', rCleanup, { once: true });
        setTimeout(rCleanup, 400);
        // Hide undo snackbar if this card was the one being undone
        if (_undoCardId === cardId) {
          hideUndoSnackbar();
        }
      }
    }
    updateCardCount();
    if (typeof tocNotifyChange === 'function') tocNotifyChange();
  }

  // Flash animation to highlight the update (skip during other animations)
  var isRunningAgent = newCardData && newCardData.card_type === 'agent'
    && newCardData.preview && newCardData.preview.status === 'running';
  var isAnimating = el.classList.contains('card-deleting') || el.classList.contains('card-restoring')
    || el.classList.contains('card-dismissing') || el.classList.contains('card-undismissing')
    || el.classList.contains('hidden-by-delete');
  if (!isRunningAgent && !isAnimating) {
    el.classList.remove('flash');
    void el.offsetWidth; // Force reflow
    el.classList.add('flash');
    setTimeout(function() { el.classList.remove('flash'); }, 600);
  }
  if (typeof tocNotifyChange === 'function') tocNotifyChange();
}

function rebuildStudyFilter() {
  // Rebuild studyNames from cards (used as fallback)
  var names = [];
  state.cards.forEach(function(c) {
    if (c.study && names.indexOf(c.study) === -1) names.push(c.study);
  });
  state.studyNames = names;

  // If the current filter no longer exists, switch to "All studies"
  if (state.activeStudyFilter && names.indexOf(state.activeStudyFilter) === -1) {
    state.activeStudyFilter = '';
    updateDropdownTrigger();
  }
}

// ================================================================
// ANNOTATIONS
// ================================================================
function renderAnnotations(container, cardData) {
  var annotations = cardData.annotations || [];
  if (annotations.length === 0) {
    container.style.display = 'none';
    return;
  }
  container.style.display = '';
  annotations.forEach(function(ann) {
    var annEl = document.createElement('div');
    annEl.className = 'card-annotation';
    annEl.dataset.annotationId = ann.id;

    var textEl = document.createElement('div');
    textEl.className = 'annotation-text';
    textEl.textContent = ann.text;
    annEl.appendChild(textEl);

    var metaEl = document.createElement('div');
    metaEl.className = 'annotation-meta';

    var ts = '';
    if (ann.timestamp) {
      try { ts = new Date(ann.timestamp).toLocaleString(); } catch(e) { ts = ann.timestamp; }
    }
    var metaText = document.createElement('span');
    metaText.textContent = ts;
    metaEl.appendChild(metaText);

    var editBtn = document.createElement('button');
    editBtn.className = 'annotation-action-btn';
    editBtn.textContent = 'edit';
    editBtn.onclick = function(e) {
      e.stopPropagation();
      startEditAnnotation(annEl, cardData, ann);
    };
    metaEl.appendChild(editBtn);

    var deleteBtn = document.createElement('button');
    deleteBtn.className = 'annotation-action-btn';
    deleteBtn.textContent = 'delete';
    deleteBtn.onclick = function(e) {
      e.stopPropagation();
      sendAnnotationEvent(cardData.card_id, 'delete', ann.id, '');
    };
    metaEl.appendChild(deleteBtn);

    annEl.appendChild(metaEl);
    container.appendChild(annEl);
  });
}

function startEditAnnotation(annEl, cardData, ann) {
  // Replace annotation content with edit form
  annEl.innerHTML = '';
  var textarea = document.createElement('textarea');
  textarea.className = 'annotation-textarea';
  textarea.value = ann.text;
  textarea.rows = 2;
  annEl.appendChild(textarea);

  var btns = document.createElement('div');
  btns.className = 'annotation-form-buttons';

  var saveBtn = document.createElement('button');
  saveBtn.className = 'response-btn response-btn-confirm';
  saveBtn.textContent = 'Save';
  saveBtn.onclick = function(e) {
    e.stopPropagation();
    var text = textarea.value.trim();
    if (text) {
      sendAnnotationEvent(cardData.card_id, 'edit', ann.id, text);
    }
  };
  btns.appendChild(saveBtn);

  var cancelBtn = document.createElement('button');
  cancelBtn.className = 'response-btn response-btn-skip';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.onclick = function(e) {
    e.stopPropagation();
    // Re-render annotations to restore original state
    var container = annEl.parentElement;
    if (container) {
      container.innerHTML = '';
      renderAnnotations(container, cardData);
    }
  };
  btns.appendChild(cancelBtn);
  annEl.appendChild(btns);

  textarea.focus();
}

function toggleAnnotationForm(cardEl, cardData) {
  var existing = cardEl.querySelector('.annotation-form');
  if (existing) {
    existing.remove();
    return;
  }

  var form = document.createElement('div');
  form.className = 'annotation-form';

  var textarea = document.createElement('textarea');
  textarea.className = 'annotation-textarea';
  textarea.placeholder = 'Add a note...';
  textarea.rows = 2;
  form.appendChild(textarea);

  var btns = document.createElement('div');
  btns.className = 'annotation-form-buttons';

  var saveBtn = document.createElement('button');
  saveBtn.className = 'response-btn response-btn-confirm';
  saveBtn.textContent = 'Save';
  saveBtn.onclick = function(e) {
    e.stopPropagation();
    var text = textarea.value.trim();
    if (text) {
      sendAnnotationEvent(cardData.card_id, 'add', '', text);
      form.remove();
    }
  };
  btns.appendChild(saveBtn);

  var cancelBtn = document.createElement('button');
  cancelBtn.className = 'response-btn response-btn-skip';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.onclick = function(e) {
    e.stopPropagation();
    form.remove();
  };
  btns.appendChild(cancelBtn);
  form.appendChild(btns);

  // Insert after annotations container
  var annotationsContainer = cardEl.querySelector('.card-annotations');
  if (annotationsContainer) {
    annotationsContainer.parentNode.insertBefore(form, annotationsContainer.nextSibling);
  } else {
    cardEl.appendChild(form);
  }

  textarea.focus();
}

function sendAnnotationEvent(cardId, action, annotationId, text) {
  if (!state.ws || !state.connected) return;
  var payload = { action: action };
  if (annotationId) payload.annotation_id = annotationId;
  if (text) payload.text = text;
  state.ws.send(JSON.stringify({
    type: 'vitrine.event',
    event_type: 'annotation',
    card_id: cardId,
    payload: payload
  }));
}

function showEmptyState() {
  var existing = document.getElementById('empty-state');
  if (existing) return;

  var empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.id = 'empty-state';
  empty.innerHTML = '<div style="font-size: 32px; opacity: 0.3;">&#9671;</div>'
    + '<div style="font-size: 15px; font-weight: 500;">No studies yet</div>'
    + '<div style="font-size: 13px;">Run an agent to get started</div>'
    + '<div><code>from m4.vitrine import show</code></div>';
  feed.appendChild(empty);
}

// ================================================================
// DISMISS / HIDE
// ================================================================
function sendDismissEvent(cardId, dismissed) {
  if (!state.ws || !state.connected) return;
  state.ws.send(JSON.stringify({
    type: 'vitrine.event',
    event_type: 'dismiss',
    card_id: cardId,
    payload: { dismissed: dismissed }
  }));
}

function sendDeleteEvent(cardId, deleted) {
  if (!state.ws || !state.connected) return;
  state.ws.send(JSON.stringify({
    type: 'vitrine.event',
    event_type: 'delete',
    card_id: cardId,
    payload: { deleted: deleted }
  }));
}

function applyDismissFilter() {
  var cards = feed.querySelectorAll('.card.dismissed');
  cards.forEach(function(el) {
    if (state.showDismissed) {
      el.classList.remove('hidden-by-dismiss');
    } else {
      el.classList.add('hidden-by-dismiss');
    }
  });
  updateCardCount();
}

function updateDismissToggleVisibility() {
  var toggle = document.getElementById('dismiss-toggle');
  if (!toggle) return;
  var hasDismissed = feed.querySelector('.card.dismissed') !== null;
  toggle.style.display = hasDismissed ? '' : 'none';
}

// Toggle click handler — wired up in init.js-compatible IIFE
(function() {
  var toggle = document.getElementById('dismiss-toggle');
  if (toggle) {
    toggle.addEventListener('click', function() {
      state.showDismissed = !state.showDismissed;
      toggle.classList.toggle('active', state.showDismissed);
      toggle.title = state.showDismissed ? 'Hide hidden cards' : 'Show hidden cards';
      toggle.innerHTML = state.showDismissed ? EYE_SVG : EYE_OFF_SVG;
      applyDismissFilter();
    });
  }
})();

// ================================================================
// UNDO SNACKBAR
// ================================================================
var _undoTimer = null;
var _undoCardId = null;

function showUndoSnackbar(cardId, title) {
  var snackbar = document.getElementById('undo-snackbar');
  if (!snackbar) return;
  var textEl = snackbar.querySelector('.undo-snackbar-text');
  if (_undoTimer) clearTimeout(_undoTimer);
  _undoCardId = cardId;
  var displayTitle = title || 'Card';
  if (displayTitle.length > 30) displayTitle = displayTitle.substring(0, 30) + '\u2026';
  textEl.textContent = '\u201c' + displayTitle + '\u201d deleted';
  snackbar.classList.add('visible');
  _undoTimer = setTimeout(function() { hideUndoSnackbar(); }, 5000);
}

function hideUndoSnackbar() {
  var snackbar = document.getElementById('undo-snackbar');
  if (snackbar) snackbar.classList.remove('visible');
  if (_undoTimer) { clearTimeout(_undoTimer); _undoTimer = null; }
  _undoCardId = null;
}

(function() {
  var btn = document.getElementById('undo-snackbar-btn');
  if (btn) {
    btn.addEventListener('click', function() {
      if (_undoCardId) {
        sendDeleteEvent(_undoCardId, false);
        hideUndoSnackbar();
      }
    });
  }
})();

// ================================================================
// AGENT CARD RENDERING
// ================================================================
function renderAgentCard(container, cardData) {
  var preview = cardData.preview || {};
  var status = preview.status || 'pending';

  container.innerHTML = '';

  if (status === 'pending') {
    renderAgentConfigForm(container, cardData);
  } else if (status === 'running') {
    renderAgentRunning(container, cardData);
  } else {
    // completed or failed
    renderAgentCompleted(container, cardData);
  }
}

function renderAgentConfigForm(container, cardData) {
  var preview = cardData.preview || {};
  var form = document.createElement('div');
  form.className = 'agent-config';

  // Model selector
  var modelRow = document.createElement('div');
  modelRow.className = 'agent-config-row';
  var modelLabel = document.createElement('label');
  modelLabel.className = 'agent-config-label';
  modelLabel.textContent = 'Model';
  modelRow.appendChild(modelLabel);
  var modelSelect = document.createElement('select');
  modelSelect.className = 'agent-config-select';
  ['sonnet', 'opus', 'haiku'].forEach(function(m) {
    var opt = document.createElement('option');
    opt.value = m;
    opt.textContent = MODEL_DISPLAY[m] || m;
    if (m === (preview.model || 'sonnet')) opt.selected = true;
    modelSelect.appendChild(opt);
  });
  modelRow.appendChild(modelSelect);
  form.appendChild(modelRow);

  // Tools (read-only)
  var toolsRow = document.createElement('div');
  toolsRow.className = 'agent-config-row';
  var toolsLabel = document.createElement('label');
  toolsLabel.className = 'agent-config-label';
  toolsLabel.textContent = 'Tools';
  toolsRow.appendChild(toolsLabel);
  var toolsText = document.createElement('span');
  toolsText.className = 'agent-config-value';
  toolsText.textContent = (preview.tools || []).join(', ');
  toolsRow.appendChild(toolsText);
  form.appendChild(toolsRow);

  // Permissions warning
  var permsRow = document.createElement('div');
  permsRow.className = 'agent-config-row';
  var permsLabel = document.createElement('label');
  permsLabel.className = 'agent-config-label';
  permsLabel.textContent = 'Perms';
  permsRow.appendChild(permsLabel);
  var permsBadge = document.createElement('span');
  permsBadge.className = 'agent-perms-badge';
  permsBadge.textContent = 'Autonomous';
  permsRow.appendChild(permsBadge);
  form.appendChild(permsRow);

  // Budget (optional)
  var budgetRow = document.createElement('div');
  budgetRow.className = 'agent-config-row';
  var budgetLabel = document.createElement('label');
  budgetLabel.className = 'agent-config-label';
  budgetLabel.textContent = 'Max turns';
  budgetRow.appendChild(budgetLabel);
  var budgetInput = document.createElement('input');
  budgetInput.type = 'number';
  budgetInput.className = 'agent-config-input';
  budgetInput.placeholder = 'unlimited';
  budgetInput.min = '1';
  if (preview.budget) budgetInput.value = preview.budget;
  budgetRow.appendChild(budgetInput);
  form.appendChild(budgetRow);

  // Additional instructions
  var instrRow = document.createElement('div');
  instrRow.className = 'agent-config-row agent-config-row-full';
  var instrLabel = document.createElement('label');
  instrLabel.className = 'agent-config-label';
  instrLabel.textContent = 'Additional instructions';
  instrRow.appendChild(instrLabel);
  var instrTextarea = document.createElement('textarea');
  instrTextarea.className = 'agent-config-textarea';
  instrTextarea.placeholder = 'Extra instructions for the agent...';
  instrTextarea.rows = 3;
  instrTextarea.value = preview.additional_prompt || '';
  instrRow.appendChild(instrTextarea);
  form.appendChild(instrRow);

  // Advanced toggle (view full prompt)
  var advToggle = document.createElement('details');
  advToggle.className = 'agent-advanced-toggle';
  var advSummary = document.createElement('summary');
  advSummary.textContent = 'Advanced (view full prompt)';
  advToggle.appendChild(advSummary);
  var advContent = document.createElement('pre');
  advContent.className = 'agent-prompt-preview';
  advContent.textContent = preview.full_prompt || preview.prompt_preview || '';
  advToggle.appendChild(advContent);
  form.appendChild(advToggle);

  container.appendChild(form);

  // Bottom bar with Run button
  var bottomBar = document.createElement('div');
  bottomBar.className = 'agent-bottom-bar';
  var runBtn = document.createElement('button');
  runBtn.className = 'response-btn response-btn-confirm agent-run-btn';
  runBtn.textContent = 'Run Agent';
  runBtn.onclick = function() {
    runBtn.disabled = true;
    runBtn.textContent = 'Starting...';
    var config = {
      model: modelSelect.value,
      additional_prompt: instrTextarea.value.trim()
    };
    var budgetVal = budgetInput.value.trim();
    if (budgetVal) config.budget = parseFloat(budgetVal);
    fetch('/api/agents/' + encodeURIComponent(cardData.card_id) + '/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    })
      .then(function(r) {
        if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || 'Failed'); });
        return r.json();
      })
      .then(function() {
        showToast('Agent started');
      })
      .catch(function(err) {
        showToast(err.message || 'Failed to start agent', 'error');
        runBtn.disabled = false;
        runBtn.textContent = 'Run Agent';
      });
  };
  bottomBar.appendChild(runBtn);
  container.appendChild(bottomBar);
}

function renderAgentRunning(container, cardData) {
  var preview = cardData.preview || {};

  // Metadata strip
  var strip = document.createElement('div');
  strip.className = 'agent-meta-strip';

  var modelBadge = document.createElement('span');
  modelBadge.className = 'agent-model-badge';
  modelBadge.textContent = MODEL_DISPLAY[preview.model] || preview.model || 'Sonnet 4.5';
  strip.appendChild(modelBadge);

  var permsBadge = document.createElement('span');
  permsBadge.className = 'agent-perms-badge-sm';
  permsBadge.textContent = 'Autonomous';
  strip.appendChild(permsBadge);

  if (preview.tools && preview.tools.length > 0) {
    var toolsList = document.createElement('span');
    toolsList.className = 'agent-tools-list';
    toolsList.textContent = preview.tools.join(', ');
    strip.appendChild(toolsList);
  }

  container.appendChild(strip);

  // Terminal box
  var terminal = document.createElement('div');
  terminal.className = 'agent-terminal';

  var termContent = document.createElement('div');
  termContent.className = 'agent-terminal-content markdown-body';
  var outputText = preview.output || '*Agent starting...*';
  if (typeof marked !== 'undefined') {
    termContent.innerHTML = marked.parse(outputText);
  } else {
    termContent.textContent = outputText;
  }
  terminal.appendChild(termContent);

  // Alive indicator — pulsing dot + rotating message
  var aliveStrip = document.createElement('div');
  aliveStrip.className = 'agent-alive-strip';
  var aliveDot = document.createElement('span');
  aliveDot.className = 'agent-alive-dot';
  aliveStrip.appendChild(aliveDot);
  var aliveMsg = document.createElement('span');
  aliveMsg.className = 'agent-alive-msg';
  aliveMsg.textContent = AGENT_THINKING_MESSAGES[Math.floor(Math.random() * AGENT_THINKING_MESSAGES.length)] + '\u2026';
  aliveStrip.appendChild(aliveMsg);

  // Inactivity indicator — hidden until 2 min idle
  var inactivityEl = document.createElement('span');
  inactivityEl.className = 'agent-inactivity-indicator';
  inactivityEl.style.display = 'none';
  aliveStrip.appendChild(inactivityEl);

  // Usage info (tokens + context %) — right-aligned
  var aliveUsage = document.createElement('span');
  aliveUsage.className = 'agent-alive-usage';
  aliveUsage.textContent = formatAgentUsage(preview);
  aliveStrip.appendChild(aliveUsage);

  terminal.appendChild(aliveStrip);

  var aliveTickCount = 0;
  // Check inactivity every 5s, rotate message every ~30s
  var aliveTimer = setInterval(function() {
    aliveTickCount++;
    if (aliveTickCount % 6 === 0) {
      aliveMsg.textContent = AGENT_THINKING_MESSAGES[Math.floor(Math.random() * AGENT_THINKING_MESSAGES.length)] + '\u2026';
    }

    // Check inactivity
    var cardEl = terminal.closest('.card');
    if (!cardEl) return;
    var cid = cardEl.dataset.cardId;
    var current = null;
    for (var i = 0; i < state.cards.length; i++) {
      if (state.cards[i].card_id === cid) { current = state.cards[i]; break; }
    }
    if (!current || !current.preview || !current.preview.last_activity_at) {
      inactivityEl.style.display = 'none';
      return;
    }
    var elapsed = Math.floor((Date.now() - new Date(current.preview.last_activity_at).getTime()) / 1000);
    if (elapsed < 120) {
      inactivityEl.style.display = 'none';
      return;
    }
    var mins = Math.floor(elapsed / 60);
    inactivityEl.textContent = ' \u00b7 No new output for ' + mins + 'm';
    inactivityEl.style.display = '';
  }, 4000);

  // Store timer ref on the card element for cleanup
  var outerCard = container.closest('.card');
  if (outerCard) outerCard._agentInactivityTimer = aliveTimer;

  // Auto-scroll to bottom
  requestAnimationFrame(function() { terminal.scrollTop = terminal.scrollHeight; });

  container.appendChild(terminal);

  // Bottom bar with expand toggle + cancel
  var bottomBar = document.createElement('div');
  bottomBar.className = 'agent-bottom-bar agent-bottom-bar-running';

  var expandBtn = document.createElement('button');
  expandBtn.className = 'agent-expand-btn';
  expandBtn.textContent = 'Expand';
  expandBtn.onclick = function() {
    var isExpanded = terminal.classList.toggle('expanded');
    expandBtn.textContent = isExpanded ? 'Collapse' : 'Expand';
    if (!isExpanded) {
      requestAnimationFrame(function() { terminal.scrollTop = terminal.scrollHeight; });
    }
  };
  bottomBar.appendChild(expandBtn);

  var cancelBtn = document.createElement('button');
  cancelBtn.className = 'agent-cancel-btn';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.onclick = function() {
    cancelBtn.disabled = true;
    fetch('/api/agents/' + encodeURIComponent(cardData.card_id), {
      method: 'DELETE'
    })
      .then(function(r) {
        if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || 'Failed'); });
        showToast('Agent cancelled');
      })
      .catch(function(err) {
        showToast(err.message || 'Cancel failed', 'error');
        cancelBtn.disabled = false;
      });
  };
  bottomBar.appendChild(cancelBtn);

  container.appendChild(bottomBar);
}

function renderAgentCompleted(container, cardData) {
  var preview = cardData.preview || {};
  var isSuccess = preview.status === 'completed';
  var outputText = preview.output || '';

  // Terminal box — compact height with gradient fade
  var terminal = document.createElement('div');
  terminal.className = 'agent-terminal agent-terminal-compact';

  var termContent = document.createElement('div');
  termContent.className = 'agent-terminal-content markdown-body';
  if (typeof marked !== 'undefined' && outputText) {
    termContent.innerHTML = marked.parse(outputText);
  } else {
    termContent.textContent = outputText;
  }
  terminal.appendChild(termContent);
  container.appendChild(terminal);

  // Bottom bar with usage info (left) + expand toggle (right)
  var usageStr = formatAgentUsage(preview);
  if (outputText || usageStr) {
    var bottomBar = document.createElement('div');
    bottomBar.className = 'agent-bottom-bar agent-bottom-bar-completed';

    if (usageStr) {
      var usageEl = document.createElement('span');
      usageEl.className = 'agent-bottom-usage';
      usageEl.textContent = usageStr;
      bottomBar.appendChild(usageEl);
    }

    if (outputText) {
      var expandBtn = document.createElement('button');
      expandBtn.className = 'agent-expand-btn';
      expandBtn.textContent = 'Expand';
      expandBtn.onclick = function() {
        var isExpanded = terminal.classList.toggle('expanded');
        terminal.classList.toggle('agent-terminal-compact', !isExpanded);
        expandBtn.textContent = isExpanded ? 'Collapse' : 'Expand';
      };
      bottomBar.appendChild(expandBtn);
    }

    container.appendChild(bottomBar);
  }
}

function formatAgentDuration(seconds) {
  if (seconds == null) return '';
  var secs = Math.round(seconds);
  if (secs >= 60) {
    return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
  }
  return secs + 's';
}

function formatTokenCount(n) {
  if (n == null || n === 0) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

function formatAgentUsage(preview) {
  var usage = preview.usage;
  if (!usage) return '';
  var parts = [];
  var totalTokens = (usage.input_tokens || 0) + (usage.output_tokens || 0);
  if (totalTokens > 0) {
    parts.push(formatTokenCount(totalTokens) + ' tokens');
  }
  if (usage.input_tokens > 0 && usage.context_window > 0) {
    var pct = Math.round((usage.input_tokens / usage.context_window) * 100);
    parts.push(pct + '% ctx');
  }
  if (usage.cost_usd != null) {
    var cost = usage.cost_usd;
    parts.push(cost < 0.01 ? '<$0.01' : '$' + cost.toFixed(2));
  }
  return parts.join(' \u00b7 ');
}

function formatElapsed(isoTimestamp) {
  var start = new Date(isoTimestamp).getTime();
  var elapsed = Math.max(0, Math.floor((Date.now() - start) / 1000));
  var mins = Math.floor(elapsed / 60);
  var secs = elapsed % 60;
  return mins + ':' + (secs < 10 ? '0' : '') + secs;
}

function buildCardPrompt(card) {
  var prompt = 'Re: "' + (card.title || 'Untitled') + '" [card:' + card.card_id + (card.study ? ', study:' + card.study : '') + ']\n';
  if (card.card_type === 'table' && card.preview && card.preview.columns) {
    var cols = card.preview.columns.join(', ');
    var rows = card.preview.row_count || (card.preview.rows ? card.preview.rows.length : '?');
    prompt += 'Preview: ' + rows + ' rows \u00d7 ' + card.preview.columns.length + ' cols (' + cols + ')\n';
  } else if (card.card_type === 'plotly') {
    prompt += 'Type: plotly chart\n';
  } else if (card.card_type === 'keyvalue') {
    prompt += 'Type: key-value\n';
  } else if (card.card_type === 'image') {
    prompt += 'Type: image\n';
  }
  prompt += '/m4-vitrine\n\n';
  return prompt;
}
