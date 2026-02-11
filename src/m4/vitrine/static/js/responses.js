'use strict';

// ================================================================
// RESPONSE UI — confirm/skip, countdown, sendResponse
// ================================================================
function buildResponseUI(cardData, cardEl) {
  var container = document.createElement('div');
  container.className = 'card-response-ui';

  // Prompt
  if (cardData.prompt) {
    var promptEl = document.createElement('div');
    promptEl.className = 'response-prompt';
    promptEl.textContent = cardData.prompt;
    container.appendChild(promptEl);
  }

  // Message input
  var msgInput = document.createElement('textarea');
  msgInput.className = 'response-message-input';
  msgInput.placeholder = 'Optional message...';
  msgInput.rows = 1;
  container.appendChild(msgInput);

  // Actions
  var actionsRow = document.createElement('div');
  actionsRow.className = 'response-actions';

  // Quick actions: if cardData.actions is a non-empty array, render action buttons
  // instead of the default Confirm button
  if (cardData.actions && Array.isArray(cardData.actions) && cardData.actions.length > 0) {
    cardData.actions.forEach(function(actionName) {
      var actionBtn = document.createElement('button');
      actionBtn.className = 'response-btn response-btn-action';
      actionBtn.textContent = actionName;
      actionBtn.onclick = function() {
        sendResponse(cardData, cardEl, actionName, msgInput.value);
      };
      actionsRow.appendChild(actionBtn);
    });
  } else {
    var confirmBtn = document.createElement('button');
    confirmBtn.className = 'response-btn response-btn-confirm';
    confirmBtn.textContent = 'Confirm';
    confirmBtn.onclick = function() {
      sendResponse(cardData, cardEl, 'confirm', msgInput.value);
    };
    actionsRow.appendChild(confirmBtn);
  }

  var skipBtn = document.createElement('button');
  skipBtn.className = 'response-btn response-btn-skip';
  skipBtn.textContent = 'Skip';
  skipBtn.onclick = function() {
    sendResponse(cardData, cardEl, 'skip', null);
  };
  actionsRow.appendChild(skipBtn);

  // Timeout countdown
  var timeoutEl = document.createElement('span');
  timeoutEl.className = 'response-timeout';
  actionsRow.appendChild(timeoutEl);
  container.appendChild(actionsRow);

  // Start countdown (use backend-configured timeout, default 5 min)
  var remaining = (cardData.timeout && cardData.timeout > 0) ? Math.floor(cardData.timeout) : 300;
  function updateCountdown() {
    var mins = Math.floor(remaining / 60);
    var secs = remaining % 60;
    timeoutEl.textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
    if (remaining <= 0) {
      clearInterval(timer);
      timeoutEl.textContent = 'Timed out';
      return;
    }
    remaining--;
  }
  updateCountdown();
  var timer = setInterval(updateCountdown, 1000);
  container._timer = timer;

  return container;
}

function sendResponse(cardData, cardEl, action, message) {
  // Gather selected indices from selection state
  var selectedRows = null;
  var columns = null;
  var selectedIndices = null;
  var sel = state.selections[cardData.card_id];
  if (cardData.card_type === 'table' && sel && sel.size > 0) {
    columns = cardData.preview.columns;
    selectedIndices = Array.from(sel).sort(function(a, b) { return a - b; });
    // Also gather currently visible checked rows for backward compat
    var tbody = cardEl.querySelector('tbody');
    if (tbody) {
      var checkboxes = tbody.querySelectorAll('input[type="checkbox"]:checked');
      if (checkboxes.length > 0) {
        selectedRows = [];
        checkboxes.forEach(function(cb) {
          var tr = cb.closest('tr');
          var cells = [];
          tr.querySelectorAll('td:not(.select-col)').forEach(function(td) {
            cells.push(td.textContent === '\u2014' ? null : td.textContent);
          });
          selectedRows.push(cells);
        });
      }
    }
  }

  // Collect form values from form card body or controls bar
  var formValues = {};
  var hasFormFields = cardEl.querySelector('.form-field');
  if (hasFormFields) {
    formValues = collectFormValues(cardEl);
  }

  // Send via WebSocket
  if (state.ws && state.connected) {
    state.ws.send(JSON.stringify({
      type: 'vitrine.event',
      event_type: 'response',
      card_id: cardData.card_id,
      payload: {
        action: action,
        message: message,
        selected_rows: selectedRows,
        selected_indices: selectedIndices,
        columns: columns,
        form_values: formValues,
      },
    }));
  }

  // Update UI: remove response panel, keep decision branding
  var responseUI = cardEl.querySelector('.card-response-ui');
  if (responseUI) {
    if (responseUI._timer) clearInterval(responseUI._timer);
    responseUI.remove();
  }
  cardEl.classList.remove('waiting');
  cardEl.classList.add('responded');

  // Freeze form: replace interactive fields with compact frozen display
  if (hasFormFields && Object.keys(formValues).length > 0) {
    var formBody = cardEl.querySelector('.card-body');
    var controlsBar = cardEl.querySelector('.card-controls-bar');
    var fields = (cardData.preview && cardData.preview.fields) || (cardData.preview && cardData.preview.controls) || [];
    if (cardData.preview && cardData.preview.fields && formBody) {
      formBody.innerHTML = '';
      renderFrozenForm(formBody, formValues, fields);
    }
    if (controlsBar) {
      controlsBar.innerHTML = '';
      renderFrozenForm(controlsBar, formValues, fields);
    }
  }

  // Update type icon to checkmark
  var typeIcon = cardEl.querySelector('.card-type-icon');
  if (typeIcon) {
    typeIcon.textContent = '\u2713';
  }

  // Show response badge
  var badge = document.createElement('span');
  badge.className = 'sent-badge';
  if (action === 'confirm') {
    badge.textContent = 'Confirmed';
  } else if (action === 'skip') {
    badge.textContent = 'Skipped';
  } else {
    badge.textContent = action;
  }
  var header = cardEl.querySelector('.card-header');
  if (header) header.appendChild(badge);

  // Show additional note if provided
  if (message && message.trim()) {
    var noteEl = document.createElement('div');
    noteEl.className = 'decision-note';
    noteEl.textContent = message.trim();
    var body = cardEl.querySelector('.card-body');
    if (body) body.appendChild(noteEl);
  }
}
