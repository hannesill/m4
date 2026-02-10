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

  // Hide card if it lands inside a collapsed section
  if (isInCollapsedSection(el)) {
    el.classList.add('hidden-by-section');
  }

  // Apply study filter to the new card
  if (state.activeStudyFilter) {
    var cardRun = cardData.study || '';
    if (cardRun !== state.activeStudyFilter && cardRun) {
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

  // Re-render annotations
  if (newCardData) {
    var annotationsContainer = el.querySelector('.card-annotations');
    if (annotationsContainer) {
      annotationsContainer.innerHTML = '';
      renderAnnotations(annotationsContainer, newCardData);
    }
  }

  // Flash animation to highlight the update
  el.classList.remove('flash');
  void el.offsetWidth; // Force reflow
  el.classList.add('flash');
  setTimeout(function() { el.classList.remove('flash'); }, 600);
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

  // Insert before annotations container
  var annotationsContainer = cardEl.querySelector('.card-annotations');
  if (annotationsContainer) {
    cardEl.insertBefore(form, annotationsContainer);
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
    + '<div style="font-size: 15px; font-weight: 500;">No analyses yet</div>'
    + '<div style="font-size: 13px;">Run an agent to get started</div>'
    + '<div><code>from m4.vitrine import show</code></div>';
  feed.appendChild(empty);
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
