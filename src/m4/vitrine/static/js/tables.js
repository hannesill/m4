'use strict';

// ================================================================
// TABLE RENDERING — headers, rows, sorting, paging, row detail
// ================================================================
function mapDtypeLabel(dtype) {
  if (!dtype) return '';
  var d = dtype.toLowerCase();
  if (d.match(/^int/)) return 'int';
  if (d.match(/^float|^double|^decimal|^numeric/)) return 'float';
  if (d.match(/^bool/)) return 'bool';
  if (d.match(/^date|^time|^timestamp/)) return 'date';
  if (d.match(/^varchar|^text|^string|^utf|^object/)) return 'str';
  return dtype.split(/[^a-zA-Z]/)[0].toLowerCase().substring(0, 5);
}

function renderTable(container, cardData) {
  var preview = cardData.preview;
  if (!preview || !preview.columns) return;

  // Shared state for this table
  var sortState = { col: null, asc: true };
  var pagerState = { offset: 0, limit: 50 };
  var searchState = { text: '' };
  var shape = preview.shape || [0, 0];
  var totalRowsRef = { value: shape[0] };
  var rowInfoEl = document.createElement('span');
  var pagerEl = { current: null };

  function updateRowInfo() {
    var total = totalRowsRef.value;
    var start = total > 0 ? pagerState.offset + 1 : 0;
    var end = Math.min(pagerState.offset + pagerState.limit, total);
    var text = shape[1] + ' columns \u00b7 ' + total.toLocaleString() + ' rows';
    if (searchState.text) text += ' (filtered)';
    if (total > 0 && (start > 1 || end < total)) text += ' (showing ' + start + '\u2013' + end + ')';
    rowInfoEl.textContent = text;
  }

  // --- Toolbar (search + export) ---
  var toolbar = document.createElement('div');
  toolbar.className = 'table-toolbar';

  if (cardData.artifact_id) {
    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'table-search';
    searchInput.placeholder = 'Search rows...';
    var debounceTimer = null;
    searchInput.oninput = function() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        searchState.text = searchInput.value;
        pagerState.offset = 0;
        reloadTable(cardData.artifact_id, pagerState, sortState, searchState, wrapper, preview.columns, preview.dtypes, totalRowsRef, rowInfoEl, pagerEl, updateRowInfo);
      }, 300);
    };
    toolbar.appendChild(searchInput);

    var exportCsvBtn = document.createElement('button');
    exportCsvBtn.className = 'export-btn';
    exportCsvBtn.textContent = 'Export CSV';
    exportCsvBtn.onclick = function() {
      var url = '/api/table/' + cardData.artifact_id + '/export?format=csv';
      if (sortState.col) url += '&sort=' + encodeURIComponent(sortState.col) + '&asc=' + sortState.asc;
      if (searchState.text) url += '&search=' + encodeURIComponent(searchState.text);
      window.location = url;
    };
    toolbar.appendChild(exportCsvBtn);

    var copyTsvBtn = document.createElement('button');
    copyTsvBtn.className = 'export-btn';
    copyTsvBtn.textContent = 'Copy TSV';
    copyTsvBtn.onclick = function() {
      var tbody = wrapper.querySelector('tbody');
      var headerCells = wrapper.querySelectorAll('thead th:not(.select-col)');
      var headers = [];
      headerCells.forEach(function(th) {
        // Get just the column name text (not the sort indicator or type badge)
        headers.push(th.firstChild.textContent);
      });
      var lines = [headers.join('\t')];
      var bodyRows = tbody.querySelectorAll('tr');
      bodyRows.forEach(function(tr) {
        var cells = [];
        tr.querySelectorAll('td:not(.select-col)').forEach(function(td) { cells.push(td.textContent); });
        lines.push(cells.join('\t'));
      });
      navigator.clipboard.writeText(lines.join('\n')).then(function() {
        showToast('Copied TSV to clipboard');
      }).catch(function() {});
    };
    toolbar.appendChild(copyTsvBtn);
  }

  container.appendChild(toolbar);

  // --- Table ---
  var wrapper = document.createElement('div');
  wrapper.className = 'table-wrapper';

  var table = document.createElement('table');
  var thead = document.createElement('thead');
  var headerRow = document.createElement('tr');

  // Add select-all checkbox column for all table cards
  var selectAllTh = document.createElement('th');
  selectAllTh.className = 'select-col';
  var selectAllCb = document.createElement('input');
  selectAllCb.type = 'checkbox';
  selectAllCb.title = 'Select all on this page';
  selectAllCb.setAttribute('aria-label', 'Select all rows on this page');
  selectAllCb.onchange = function() {
    var cbs = wrapper.querySelectorAll('tbody .select-col input[type="checkbox"]');
    cbs.forEach(function(cb) {
      cb.checked = selectAllCb.checked;
      // Fire the onchange to update selection state
      if (cb.onchange) cb.onchange();
    });
    // Show "Select all N rows" banner when total exceeds visible
    var totalRows = (preview.shape && preview.shape[0]) || 0;
    var visibleRows = cbs.length;
    var existing = container.querySelector('.select-all-banner');
    if (selectAllCb.checked && totalRows > visibleRows) {
      if (!existing) {
        var banner = document.createElement('div');
        banner.className = 'select-all-banner';
        banner.textContent = 'All ' + visibleRows + ' rows on this page selected. ';
        var selectAllLink = document.createElement('a');
        selectAllLink.href = '#';
        selectAllLink.textContent = 'Select all ' + totalRows + ' rows';
        selectAllLink.onclick = function(e) {
          e.preventDefault();
          banner.textContent = 'All ' + totalRows + ' rows selected.';
        };
        banner.appendChild(selectAllLink);
        wrapper.parentNode.insertBefore(banner, wrapper);
      }
    } else if (existing) {
      existing.remove();
    }
  };
  selectAllTh.appendChild(selectAllCb);
  headerRow.appendChild(selectAllTh);

  preview.columns.forEach(function(col) {
    var th = document.createElement('th');
    var isNumeric = false;
    if (preview.dtypes) {
      var dtype = preview.dtypes[col] || '';
      if (dtype.match(/int|float|num/i)) {
        th.style.textAlign = 'right';
        isNumeric = true;
      }
    }

    var label = document.createTextNode(col);
    th.appendChild(label);

    // Type badge
    if (preview.dtypes && preview.dtypes[col]) {
      var badge = document.createElement('span');
      badge.className = 'type-badge';
      badge.textContent = mapDtypeLabel(preview.dtypes[col]);
      th.appendChild(badge);
    }

    var indicator = document.createElement('span');
    indicator.className = 'sort-indicator';
    indicator.textContent = '\u2195';
    th.appendChild(indicator);

    if (cardData.artifact_id) {
      th.onclick = function() {
        if (sortState.col === col) {
          sortState.asc = !sortState.asc;
        } else {
          sortState.col = col;
          sortState.asc = true;
        }
        headerRow.querySelectorAll('.sort-indicator').forEach(function(ind) {
          ind.classList.remove('active');
          ind.textContent = '\u2195';
        });
        indicator.classList.add('active');
        indicator.textContent = sortState.asc ? '\u25b2' : '\u25bc';
        pagerState.offset = 0;
        reloadTable(cardData.artifact_id, pagerState, sortState, searchState, wrapper, preview.columns, preview.dtypes, totalRowsRef, rowInfoEl, pagerEl, updateRowInfo);
      };
    }

    headerRow.appendChild(th);
  });

  thead.appendChild(headerRow);
  table.appendChild(thead);

  var tbody = document.createElement('tbody');
  var rows = preview.preview_rows || [];
  renderTableRows(tbody, rows, preview.columns, preview.dtypes, cardData);

  table.appendChild(tbody);
  wrapper.appendChild(table);

  // --- Table info & pagination ---
  var totalRows = totalRowsRef.value;
  var previewCount = rows.length;

  var info = document.createElement('div');
  info.className = 'table-info';
  info.appendChild(rowInfoEl);

  if (totalRows > previewCount && cardData.artifact_id) {
    // Initial view has only preview rows — load the full first page immediately
    reloadTable(cardData.artifact_id, pagerState, sortState, searchState, wrapper, preview.columns, preview.dtypes, totalRowsRef, rowInfoEl, pagerEl, updateRowInfo);
    var pager = createPager(cardData.artifact_id, totalRowsRef, preview.columns, preview.dtypes, wrapper, rowInfoEl, pagerState, sortState, searchState, cardData, updateRowInfo);
    pagerEl.current = pager;
    info.appendChild(pager);
  } else {
    // Small table — preview is the full data
    rowInfoEl.textContent = shape[1] + ' columns \u00b7 ' + totalRows.toLocaleString() + ' rows';
  }

  container.appendChild(wrapper);
  container.appendChild(info);
}

function reloadTable(artifactId, pagerState, sortState, searchState, wrapper, columns, dtypes, totalRowsRef, rowInfoEl, pagerEl, updateRowInfo) {
  var url = '/api/table/' + artifactId + '?offset=' + pagerState.offset + '&limit=' + pagerState.limit;
  if (sortState && sortState.col) {
    url += '&sort=' + encodeURIComponent(sortState.col) + '&asc=' + sortState.asc;
  }
  if (searchState && searchState.text) {
    url += '&search=' + encodeURIComponent(searchState.text);
  }
  fetch(url)
    .then(function(r) {
      if (!r.ok) throw new Error('Server returned ' + r.status);
      return r.json();
    })
    .then(function(data) {
      if (!data.rows) throw new Error('Invalid response');
      totalRowsRef.value = data.total_rows;
      var tbody = wrapper.querySelector('tbody');
      // Find the parent card to get cardData for row click events
      var cardEl = wrapper.closest('.card');
      var cardData = null;
      if (cardEl) {
        var cardId = cardEl.dataset.cardId;
        cardData = state.cards.find(function(c) { return c.card_id === cardId; });
      }
      renderTableRows(tbody, data.rows, columns, dtypes, cardData, pagerState.offset);
      if (updateRowInfo) updateRowInfo();

      // Rebuild pager if needed
      if (pagerEl && pagerEl.current) {
        var parent = pagerEl.current.parentNode;
        parent.removeChild(pagerEl.current);
        var newPager = createPager(artifactId, totalRowsRef, columns, dtypes, wrapper, rowInfoEl, pagerState, sortState, searchState, cardData, updateRowInfo);
        pagerEl.current = newPager;
        parent.appendChild(newPager);
      } else if (data.total_rows > pagerState.limit) {
        var infoDiv = rowInfoEl.parentNode;
        var newPager = createPager(artifactId, totalRowsRef, columns, dtypes, wrapper, rowInfoEl, pagerState, sortState, searchState, cardData, updateRowInfo);
        pagerEl.current = newPager;
        infoDiv.appendChild(newPager);
      }
    })
    .catch(function(err) {
      console.error('Table fetch failed:', err);
      showToast('Search failed', 'error');
    });
}

function renderTableRows(tbody, rows, columns, dtypes, cardData, pageOffset) {
  tbody.innerHTML = '';
  var cardId = cardData ? cardData.card_id : null;
  pageOffset = pageOffset || 0;
  // Ensure selection set exists for this card
  if (cardId && !state.selections[cardId]) {
    state.selections[cardId] = new Set();
  }
  rows.forEach(function(row, rowIdx) {
    var tr = document.createElement('tr');
    var absIdx = pageOffset + rowIdx;
    // Add selection checkbox for all table cards
    var selTd = document.createElement('td');
    selTd.className = 'select-col';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    if (cardId && state.selections[cardId] && state.selections[cardId].has(absIdx)) {
      cb.checked = true;
    }
    cb.onclick = function(e) { e.stopPropagation(); };
    cb.onchange = function() {
      if (!cardId) return;
      if (!state.selections[cardId]) state.selections[cardId] = new Set();
      if (cb.checked) {
        state.selections[cardId].add(absIdx);
      } else {
        state.selections[cardId].delete(absIdx);
      }
      updateSelectionBadge(cardId);
      sendSelectionEvent(cardId);
    };
    selTd.appendChild(cb);
    tr.appendChild(selTd);
    row.forEach(function(val, i) {
      var td = document.createElement('td');
      td.textContent = val === null ? '\u2014' : String(val);
      if (dtypes) {
        var dtype = dtypes[columns[i]] || '';
        if (dtype.match(/int|float|num/i)) {
          td.style.textAlign = 'right';
        }
      }
      tr.appendChild(td);
    });
    // Row click → detail panel + WebSocket event
    tr.onclick = function() {
      var rowObj = {};
      columns.forEach(function(col, i) { rowObj[col] = row[i]; });
      showRowDetail(columns, row, dtypes, cardData);
      // Fire WebSocket event
      if (cardData && state.ws && state.connected) {
        state.ws.send(JSON.stringify({
          type: 'vitrine.event',
          event_type: 'row_click',
          card_id: cardData.card_id,
          payload: { row_index: rowIdx, row: rowObj },
        }));
      }
    };
    tbody.appendChild(tr);
  });
}

function showRowDetail(columns, row, dtypes, cardData) {
  // Remove any existing detail panel
  closeRowDetail();

  var overlay = document.createElement('div');
  overlay.className = 'row-detail-overlay';
  overlay.id = 'row-detail-overlay';
  overlay.onclick = function(e) {
    if (e.target === overlay) closeRowDetail();
  };

  var panel = document.createElement('div');
  panel.className = 'row-detail-panel';

  var header = document.createElement('div');
  header.className = 'row-detail-header';
  var headerTitle = document.createElement('span');
  headerTitle.textContent = (cardData && cardData.title ? cardData.title + ' \u2014 ' : '') + 'Row Detail';
  header.appendChild(headerTitle);
  var closeBtn = document.createElement('button');
  closeBtn.className = 'row-detail-close';
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = closeRowDetail;
  header.appendChild(closeBtn);
  panel.appendChild(header);

  var body = document.createElement('div');
  body.className = 'row-detail-body';

  var dl = document.createElement('div');
  dl.className = 'kv-list';

  columns.forEach(function(col, i) {
    var keyEl = document.createElement('div');
    keyEl.className = 'kv-key';
    var keyText = col;
    if (dtypes && dtypes[col]) {
      keyText += ' ';
      var badge = document.createElement('span');
      badge.className = 'type-badge';
      badge.textContent = mapDtypeLabel(dtypes[col]);
      keyEl.textContent = col + ' ';
      keyEl.appendChild(badge);
    } else {
      keyEl.textContent = col;
    }

    var valEl = document.createElement('div');
    valEl.className = 'kv-value';
    valEl.textContent = row[i] === null ? '\u2014' : String(row[i]);
    valEl.style.wordBreak = 'break-all';

    dl.appendChild(keyEl);
    dl.appendChild(valEl);
  });

  body.appendChild(dl);
  panel.appendChild(body);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  // ESC to close
  document.addEventListener('keydown', _rowDetailEsc);
}

function _rowDetailEsc(e) {
  if (e.key === 'Escape') closeRowDetail();
}

function closeRowDetail() {
  var overlay = document.getElementById('row-detail-overlay');
  if (overlay) overlay.remove();
  document.removeEventListener('keydown', _rowDetailEsc);
}

function createPager(artifactId, totalRowsRef, columns, dtypes, wrapper, rowInfoEl, pagerState, sortState, searchState, cardData, updateRowInfo) {
  var limit = pagerState.limit;

  var pager = document.createElement('div');
  pager.className = 'table-pager';

  var prevBtn = document.createElement('button');
  prevBtn.textContent = '\u2190 Prev';
  prevBtn.disabled = true;

  var pageInfo = document.createElement('span');

  var nextBtn = document.createElement('button');
  nextBtn.textContent = 'Next \u2192';

  function updatePage() {
    var total = totalRowsRef.value;
    var start = total > 0 ? pagerState.offset + 1 : 0;
    var end = Math.min(pagerState.offset + limit, total);
    pageInfo.textContent = start + '\u2013' + end + ' of ' + total.toLocaleString();
    prevBtn.disabled = pagerState.offset === 0;
    nextBtn.disabled = pagerState.offset + limit >= total;
    if (updateRowInfo) updateRowInfo();
  }

  function loadPage() {
    var url = '/api/table/' + artifactId + '?offset=' + pagerState.offset + '&limit=' + limit;
    if (sortState && sortState.col) {
      url += '&sort=' + encodeURIComponent(sortState.col) + '&asc=' + sortState.asc;
    }
    if (searchState && searchState.text) {
      url += '&search=' + encodeURIComponent(searchState.text);
    }
    fetch(url)
      .then(function(r) {
        if (!r.ok) throw new Error('Server returned ' + r.status);
        return r.json();
      })
      .then(function(data) {
        if (!data.rows) throw new Error('Invalid response');
        totalRowsRef.value = data.total_rows;
        var tbody = wrapper.querySelector('tbody');
        renderTableRows(tbody, data.rows, columns, dtypes, cardData, pagerState.offset);
        updatePage();
      })
      .catch(function(err) {
        console.error('Table page fetch failed:', err);
        showToast('Failed to load page', 'error');
      });
  }

  prevBtn.onclick = function() {
    pagerState.offset = Math.max(0, pagerState.offset - limit);
    loadPage();
  };

  nextBtn.onclick = function() {
    pagerState.offset = pagerState.offset + limit;
    loadPage();
  };

  pager.appendChild(prevBtn);
  pager.appendChild(pageInfo);
  pager.appendChild(nextBtn);
  updatePage();

  return pager;
}

// ================================================================
// SELECTION TRACKING
// ================================================================
function sendSelectionEvent(cardId) {
  if (!state.ws || !state.connected) return;
  var sel = state.selections[cardId];
  if (!sel) return;
  state.ws.send(JSON.stringify({
    type: 'vitrine.event',
    event_type: 'selection',
    card_id: cardId,
    payload: { selected_indices: Array.from(sel).sort(function(a, b) { return a - b; }) },
  }));
}

function updateSelectionBadge(cardId) {
  var cardEl = document.getElementById('card-' + cardId);
  if (!cardEl) return;
  var header = cardEl.querySelector('.card-header');
  if (!header) return;
  var badge = header.querySelector('.selection-badge');
  var sel = state.selections[cardId];
  var count = sel ? sel.size : 0;
  if (count > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'selection-badge';
      // Insert before card-actions
      var actions = header.querySelector('.card-actions');
      if (actions) {
        header.insertBefore(badge, actions);
      } else {
        header.appendChild(badge);
      }
    }
    badge.textContent = count + ' selected';
  } else if (badge) {
    badge.remove();
  }
}
