'use strict';

// ================================================================
// CONTENT RENDERERS — markdown, key-value, plotly, image
// ================================================================
function renderMarkdown(container, cardData) {
  var text = (cardData.preview && cardData.preview.text) || '';
  container.className += ' markdown-body';

  if (window.marked) {
    container.innerHTML = window.marked.parse(text);
  } else {
    container.innerHTML = basicMarkdown(text);
    loadMarked(function() {
      container.innerHTML = window.marked.parse(text);
    });
  }
}

function basicMarkdown(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>');
}

function loadMarked(callback) {
  if (state.markedLoaded) return;
  state.markedLoaded = true;

  var script = document.createElement('script');
  script.src = '/static/vendor/marked.min.js';
  script.onload = function() {
    if (window.marked) {
      window.marked.setOptions({ breaks: true, gfm: true });
      if (callback) callback();
    }
  };
  script.onerror = function() {
    state.markedLoaded = false;
  };
  document.head.appendChild(script);
}

function renderKeyValue(container, cardData) {
  var items = (cardData.preview && cardData.preview.items) || {};
  var dl = document.createElement('div');
  dl.className = 'kv-list';

  Object.keys(items).forEach(function(key) {
    var keyEl = document.createElement('div');
    keyEl.className = 'kv-key';
    keyEl.textContent = key;

    var valEl = document.createElement('div');
    valEl.className = 'kv-value';
    valEl.textContent = items[key];

    dl.appendChild(keyEl);
    dl.appendChild(valEl);
  });

  container.appendChild(dl);

function renderImage(container, cardData) {
  var preview = cardData.preview || {};
  var imgContainer = document.createElement('div');
  imgContainer.className = 'image-container';

  var img = document.createElement('img');

  if (preview.data && preview.format === 'svg') {
    img.src = 'data:image/svg+xml;base64,' + preview.data;
  } else if (preview.data && preview.format === 'png') {
    img.src = 'data:image/png;base64,' + preview.data;
  } else if (cardData.artifact_id) {
    // Fall back to artifact endpoint
    img.src = '/api/artifact/' + cardData.artifact_id;
  } else {
    container.textContent = 'No image data';
    return;
  }

  img.alt = cardData.title || 'Figure';
  img.style.maxWidth = '100%';
  imgContainer.appendChild(img);
  container.appendChild(imgContainer);
}
