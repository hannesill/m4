'use strict';

// ================================================================
// WEBSOCKET — connect, reconnect, message dispatch
// ================================================================
function connect() {
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
  updateStatus('connecting');

  var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var ws;
  try {
    ws = new WebSocket(protocol + '//' + location.host + '/ws');
  } catch (e) {
    scheduleReconnect();
    return;
  }

  ws.onopen = function() {
    state.ws = ws;
    state.connected = true;
    state.reconnectDelay = 1000;
    state.liveMode = false;
    updateStatus('connected');
    loadSessionInfo();
    loadStudies();
    // After replay completes (~500ms), enable live auto-switching
    setTimeout(function() { state.liveMode = true; }, 500);
    // Start polling for new output files
    if (typeof startFilesPoll === 'function') startFilesPoll();
  };

  ws.onmessage = function(event) {
    try {
      var msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (e) {
      console.error('Failed to parse message:', e);
    }
  };

  ws.onclose = function() {
    state.connected = false;
    state.ws = null;
    updateStatus('disconnected');
    if (typeof stopFilesPoll === 'function') stopFilesPoll();
    showToast('Connection lost, reconnecting...', 'error');
    scheduleReconnect();
  };

  ws.onerror = function() {
    showToast('WebSocket error', 'error');
    ws.close();
  };
}

function scheduleReconnect() {
  state.reconnectTimer = setTimeout(connect, state.reconnectDelay);
  state.reconnectDelay = Math.min(state.reconnectDelay * 2, 15000);
}

function handleMessage(msg) {
  switch (msg.type) {
    case 'display.add':
      addCard(msg.card);
      if (state.activeStudyFilter && typeof loadFiles === 'function') loadFiles(state.activeStudyFilter);
      break;
    case 'display.section':
      addSection(msg.title, msg.study);
      break;
    case 'display.update':
      updateCard(msg.card_id, msg.card);
      break;
    case 'agent.started':
    case 'agent.completed':
    case 'agent.failed':
      if (typeof handleAgentMessage === 'function') handleAgentMessage(msg);
      break;
  }
}
