'use strict';

// ================================================================
// FILES PANEL — list, preview, download study output files
// ================================================================

var _FILE_TYPE_LETTERS = {
  python: 'P',
  markdown: 'M',
  csv: 'D',
  parquet: 'D',
  data: 'D',
  image: 'I',
  sql: 'Q',
  r: 'R',
  text: 'T',
  pdf: 'F',
  html: 'W',
  directory: '/',
  other: '?',
};

// Map file types to highlight.js language identifiers
var _HLJS_LANG_MAP = {
  python: 'python',
  sql: 'sql',
  r: 'r',
  data: 'json',
};

// Load highlight.js on demand (CDN)
var _hljsLoading = false;
function loadHighlightJs(callback) {
  if (window.hljs) { callback(); return; }
  if (_hljsLoading) {
    // Poll until loaded
    var poll = setInterval(function() {
      if (window.hljs) { clearInterval(poll); callback(); }
    }, 50);
    return;
  }
  _hljsLoading = true;

  // Pick theme based on current mode
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  var cssHref = isDark
    ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
    : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';

  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = cssHref;
  link.id = 'hljs-theme';
  document.head.appendChild(link);

  var script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js';
  script.onload = function() { if (window.hljs && callback) callback(); };
  document.head.appendChild(script);
}

// State
state.filesVisible = false;
state.files = [];

// DOM references
var filesPanel = document.getElementById('files-panel');
var filesToggleBtn = document.getElementById('files-toggle-btn');

function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB'];
  var i = 0;
  var size = bytes;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return (i === 0 ? size : size.toFixed(1)) + ' ' + units[i];
}

function toggleFilesPanel() {
  state.filesVisible = !state.filesVisible;
  if (state.filesVisible) {
    filesPanel.classList.add('visible');
    filesToggleBtn.classList.add('active');
  } else {
    filesPanel.classList.remove('visible');
    filesToggleBtn.classList.remove('active');
  }
}

function loadFiles(studyLabel) {
  if (!studyLabel) {
    state.files = [];
    updateFilesToggle();
    filesPanel.classList.remove('visible');
    state.filesVisible = false;
    return;
  }

  fetch('/api/studies/' + encodeURIComponent(studyLabel) + '/files')
    .then(function(r) { return r.json(); })
    .then(function(files) {
      state.files = files || [];
      updateFilesToggle();
      if (state.filesVisible) renderFilesPanel(studyLabel);
    })
    .catch(function() {
      state.files = [];
      updateFilesToggle();
    });
}

function updateFilesToggle() {
  var fileCount = state.files.filter(function(f) { return !f.is_dir; }).length;
  if (!filesToggleBtn) return;
  if (fileCount > 0) {
    filesToggleBtn.style.display = '';
    filesToggleBtn.innerHTML = '<span class="files-count">' + fileCount + '</span> file' + (fileCount !== 1 ? 's' : '');
  } else {
    filesToggleBtn.style.display = 'none';
    if (state.filesVisible) {
      state.filesVisible = false;
      filesPanel.classList.remove('visible');
      filesToggleBtn.classList.remove('active');
    }
  }
}

function renderFilesPanel(studyLabel) {
  if (!filesPanel) return;
  var study = studyLabel || state.activeStudyFilter;
  if (!study) {
    filesPanel.innerHTML = '';
    return;
  }

  var files = state.files.filter(function(f) { return !f.is_dir; });

  if (files.length === 0) {
    filesPanel.innerHTML = '<div class="files-panel-inner"><div class="files-empty">No output files</div></div>';
    return;
  }

  // Group by directory
  var groups = {};
  var groupOrder = [];
  files.forEach(function(f) {
    var parts = f.path.split('/');
    var dir = parts.length > 1 ? parts.slice(0, -1).join('/') : '.';
    if (!groups[dir]) {
      groups[dir] = [];
      groupOrder.push(dir);
    }
    groups[dir].push(f);
  });

  var html = '<div class="files-panel-inner">';
  html += '<div class="files-panel-header">';
  html += '<span class="files-panel-title">Research Files</span>';
  html += '<button class="files-download-all" onclick="downloadAllFiles(\'' + escapeAttr(study) + '\')">&#8615; Download all</button>';
  html += '</div>';
  html += '<ul class="files-list">';

  groupOrder.forEach(function(dir) {
    if (dir !== '.' || groupOrder.length > 1) {
      html += '<li class="files-dir-group">' + escapeHtml(dir === '.' ? 'Root' : dir) + '</li>';
    }
    groups[dir].forEach(function(f) {
      var letter = _FILE_TYPE_LETTERS[f.type] || '?';
      html += '<li class="files-list-item" onclick="previewFile(\'' + escapeAttr(study) + '\', \'' + escapeAttr(f.path) + '\', \'' + escapeAttr(f.type) + '\', \'' + escapeAttr(f.name) + '\')">';
      html += '<span class="file-type-icon" data-type="' + f.type + '">' + letter + '</span>';
      html += '<span class="file-name">' + escapeHtml(f.name) + '</span>';
      html += '<span class="file-size">' + formatFileSize(f.size) + '</span>';
      html += '<span class="file-actions">';
      html += '<button class="file-action-btn" onclick="event.stopPropagation(); downloadFile(\'' + escapeAttr(study) + '\', \'' + escapeAttr(f.path) + '\', \'' + escapeAttr(f.name) + '\')">Download</button>';
      html += '</span>';
      html += '</li>';
    });
  });

  html += '</ul></div>';
  filesPanel.innerHTML = html;
}

function escapeHtml(s) {
  var div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function escapeAttr(s) {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function downloadFile(study, filepath, filename) {
  var url = '/api/studies/' + encodeURIComponent(study) + '/files/' + encodeURIComponent(filepath) + '?mode=download';
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function downloadAllFiles(study) {
  var url = '/api/studies/' + encodeURIComponent(study) + '/files-archive';
  var a = document.createElement('a');
  a.href = url;
  a.download = study + '-files.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function previewFile(study, filepath, fileType, filename) {
  var overlay = document.createElement('div');
  overlay.className = 'file-preview-overlay';

  var modal = document.createElement('div');
  modal.className = 'file-preview-modal';

  // Header
  var header = document.createElement('div');
  header.className = 'file-preview-header';
  var title = document.createElement('span');
  title.className = 'file-preview-title';
  title.textContent = filename;
  var closeBtn = document.createElement('button');
  closeBtn.className = 'file-preview-close';
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = function() { overlay.remove(); };
  header.appendChild(title);
  header.appendChild(closeBtn);
  modal.appendChild(header);

  // Body (loading)
  var body = document.createElement('div');
  body.className = 'file-preview-body';
  body.textContent = 'Loading...';
  modal.appendChild(body);

  // Footer with download button
  var footer = document.createElement('div');
  footer.className = 'file-preview-actions';
  var dlBtn = document.createElement('button');
  dlBtn.className = 'file-action-btn';
  dlBtn.textContent = 'Download';
  dlBtn.onclick = function() { downloadFile(study, filepath, filename); };
  footer.appendChild(dlBtn);
  modal.appendChild(footer);

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Close on overlay click
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) overlay.remove();
  });

  // Close on Escape
  function onKey(e) {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); }
  }
  document.addEventListener('keydown', onKey);

  // Fetch content
  var url = '/api/studies/' + encodeURIComponent(study) + '/files/' + encodeURIComponent(filepath);

  if (fileType === 'image') {
    body.innerHTML = '';
    var img = document.createElement('img');
    img.className = 'file-preview-image';
    img.src = url;
    img.alt = filename;
    body.appendChild(img);
    return;
  }

  if (fileType === 'html') {
    body.innerHTML = '';
    var iframe = document.createElement('iframe');
    iframe.className = 'file-preview-iframe';
    iframe.sandbox = 'allow-scripts allow-same-origin';
    iframe.src = url;
    body.appendChild(iframe);
    return;
  }

  if (fileType === 'csv' || fileType === 'parquet') {
    fetch(url)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        body.innerHTML = '';
        if (data.error) {
          body.textContent = data.error;
          return;
        }
        var info = document.createElement('div');
        info.className = 'file-preview-table-info';
        info.textContent = data.total_rows + ' rows' + (data.truncated ? ' (showing first 1,000)' : '');
        body.appendChild(info);

        var wrap = document.createElement('div');
        wrap.className = 'file-preview-table-wrap';
        var table = document.createElement('table');
        var thead = '<thead><tr>' + data.columns.map(function(c) { return '<th>' + escapeHtml(String(c)) + '</th>'; }).join('') + '</tr></thead>';
        var tbody = '<tbody>' + data.rows.map(function(row) {
          return '<tr>' + row.map(function(v) { return '<td>' + escapeHtml(v == null ? '' : String(v)) + '</td>'; }).join('') + '</tr>';
        }).join('') + '</tbody>';
        table.innerHTML = thead + tbody;
        wrap.appendChild(table);
        body.appendChild(wrap);
      })
      .catch(function(err) { body.textContent = 'Failed to load: ' + err; });
    return;
  }

  if (fileType === 'markdown') {
    fetch(url)
      .then(function(r) { return r.text(); })
      .then(function(text) {
        body.innerHTML = '';
        var div = document.createElement('div');
        div.className = 'file-preview-markdown';
        if (window.marked) {
          div.innerHTML = window.marked.parse(text);
          _highlightCodeBlocks(div);
        } else {
          div.textContent = text;
        }
        body.appendChild(div);
      })
      .catch(function(err) { body.textContent = 'Failed to load: ' + err; });
    return;
  }

  if (fileType === 'pdf') {
    body.innerHTML = '';
    body.textContent = 'PDF preview not available. Use the download button.';
    return;
  }

  // Text/code files — with syntax highlighting
  fetch(url)
    .then(function(r) { return r.text(); })
    .then(function(text) {
      body.innerHTML = '';
      var pre = document.createElement('pre');
      pre.className = 'file-preview-code';
      var code = document.createElement('code');
      var lang = _HLJS_LANG_MAP[fileType];
      if (lang) code.className = 'language-' + lang;
      code.textContent = text;
      pre.appendChild(code);
      body.appendChild(pre);

      // Apply syntax highlighting if a language is known
      if (lang) {
        loadHighlightJs(function() {
          if (window.hljs) window.hljs.highlightElement(code);
        });
      }
    })
    .catch(function(err) { body.textContent = 'Failed to load: ' + err; });
}

// Highlight fenced code blocks inside rendered markdown
function _highlightCodeBlocks(container) {
  loadHighlightJs(function() {
    if (!window.hljs) return;
    var blocks = container.querySelectorAll('pre code');
    for (var i = 0; i < blocks.length; i++) {
      window.hljs.highlightElement(blocks[i]);
    }
  });
}

// Wire up toggle button
if (filesToggleBtn) {
  filesToggleBtn.addEventListener('click', function() {
    toggleFilesPanel();
    if (state.filesVisible && state.activeStudyFilter) {
      renderFilesPanel(state.activeStudyFilter);
    }
  });
  // Hide by default
  filesToggleBtn.style.display = 'none';
}

// Poll for new files every 5 seconds while connected with an active study
var _filesPollTimer = null;

function startFilesPoll() {
  stopFilesPoll();
  _filesPollTimer = setInterval(function() {
    if (state.connected && state.activeStudyFilter) {
      loadFiles(state.activeStudyFilter);
    }
  }, 5000);
}

function stopFilesPoll() {
  if (_filesPollTimer) {
    clearInterval(_filesPollTimer);
    _filesPollTimer = null;
  }
}
