'use strict';

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
  var headerType = cardData.response_requested ? 'decision' : cardData.card_type;
  header.setAttribute('data-type', headerType);

  // Collapse toggle
  var collapseBtn = document.createElement('button');
  collapseBtn.className = 'card-collapse-btn';
  collapseBtn.innerHTML = '&#9660;';
  collapseBtn.title = 'Collapse';
  collapseBtn.setAttribute('aria-label', 'Collapse card');
  collapseBtn.onclick = function() {
    var body = el.querySelector('.card-body');
    var prov = el.querySelector('.card-provenance');
    var isCollapsed = collapseBtn.classList.toggle('collapsed');
    if (body) body.classList.toggle('collapsed', isCollapsed);
    if (prov) prov.classList.toggle('collapsed', isCollapsed);
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

  // Title
  var title = document.createElement('span');
  title.className = 'card-title';
  title.textContent = cardData.title || cardData.card_type;
  header.appendChild(title);

  // Timestamp
  var meta = document.createElement('span');
  meta.className = 'card-meta';
  if (cardData.timestamp) {
    meta.textContent = new Date(cardData.timestamp).toLocaleTimeString();
  }
  header.appendChild(meta);

  // Action buttons
  var actions = document.createElement('div');
  actions.className = 'card-actions';

  // Link / copy deep-link button
  var linkBtn = document.createElement('button');
  linkBtn.className = 'card-action-btn';
  linkBtn.title = 'Copy card link';
  linkBtn.setAttribute('aria-label', 'Copy card link');
  linkBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 9.5a3 3 0 004.2.1l2-2a3 3 0 00-4.2-4.3l-1.2 1.1"/><path d="M9.5 6.5a3 3 0 00-4.2-.1l-2 2a3 3 0 004.2 4.3l1.1-1.1"/></svg>';
  linkBtn.onclick = function(e) {
    e.stopPropagation();
    var slug = (cardData.title || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').substring(0, 30).replace(/-$/, '');
    var cardRef = cardData.card_id.substring(0, 6);
    if (slug) cardRef += '-' + slug;
    var cardUrl = location.origin + location.pathname + '#card=' + cardRef;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(cardUrl).then(function() {
        showToast('Copied card link');
      }, function() {
        showToast('Failed to copy', 'error');
      });
    } else {
      showToast('Clipboard not available', 'error');
    }
  };
  actions.appendChild(linkBtn);

  header.appendChild(actions);
  el.appendChild(header);

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
      if (cardData.preview && cardData.preview.fields) {
        renderForm(body, cardData);
      } else {
        renderMarkdown(body, cardData);
      }
      break;
    case 'keyvalue':
      renderKeyValue(body, cardData);
      break;
    case 'section':
      el.remove();
      addSection(cardData.title || (cardData.preview && cardData.preview.title) || '');
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
    // Update agent status and send browser notification
    updateAgentStatus('Waiting for your response');
    notifyDecisionCard(cardData);
  }

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

  // Apply study filter to the new card
  if (state.activeStudyFilter) {
    var cardRun = cardData.study || '';
    if (cardRun !== state.activeStudyFilter && cardRun) {
      el.classList.add('hidden-by-filter');
    }
  }

  updateCardCount();

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
  div.textContent = title;
  div.dataset.study = study || '';
  feed.appendChild(div);

  if (state.activeStudyFilter) {
    applyStudyFilter();
  }

  scrollToBottom();
}

function updateCard(cardId, newCardData) {
  var el = document.getElementById('card-' + cardId);
  if (!el) return;

  // Update state.cards entry
  if (newCardData) {
    for (var i = 0; i < state.cards.length; i++) {
      if (state.cards[i].card_id === cardId) {
        state.cards[i] = newCardData;
        break;
      }
    }

    // Update title
    var titleEl = el.querySelector('.card-title');
    if (titleEl) {
      titleEl.textContent = newCardData.title || newCardData.card_type;
    }

    var header = el.querySelector('.card-header');
    if (header) {
      var headerType = newCardData.response_requested ? 'decision' : newCardData.card_type;
      header.setAttribute('data-type', headerType);
      var typeIcon = header.querySelector('.card-type-icon');
      if (typeIcon) {
        typeIcon.setAttribute('data-type', headerType);
        typeIcon.textContent = TYPE_LETTERS[headerType] || '?';
      }
    }

    // Re-render body content
    var body = el.querySelector('.card-body');
    if (body) {
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
        default:
          body.textContent = JSON.stringify(newCardData.preview);
      }
    }
  }

  // Flash animation to highlight the update
  el.classList.remove('flash');
  void el.offsetWidth; // Force reflow
  el.classList.add('flash');
  setTimeout(function() { el.classList.remove('flash'); }, 600);
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

function showEmptyState() {
  var existing = document.getElementById('empty-state');
  if (existing) return;

  var empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.id = 'empty-state';
  empty.innerHTML = '<div style="font-size: 32px; opacity: 0.3;">&#9671;</div>'
    + '<div style="font-size: 15px; font-weight: 500;">No analyses yet</div>'
    + '<div style="font-size: 13px;">Run an agent to get started</div>'
    + '<div><code>from m4.vitrine import show</code></div>';
  feed.appendChild(empty);
}
