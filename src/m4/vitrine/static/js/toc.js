'use strict';

// ================================================================
// TABLE OF CONTENTS — overlay panel with card/section list
// ================================================================

(function() {
  var tocBtn = document.getElementById('toc-btn');
  var tocPanel = document.getElementById('toc-panel');
  var tocDropdown = document.getElementById('toc-dropdown');
  if (!tocBtn || !tocPanel) return;

  var hideTimer = null;
  var observer = null;
  var activeCardId = null;
  var debounceTimer = null;

  // --- Hover interaction ---
  function showPanel() {
    clearTimeout(hideTimer);
    buildToc();
    tocPanel.style.display = '';
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function() {
      tocPanel.style.display = 'none';
    }, 150);
  }

  function cancelHide() {
    clearTimeout(hideTimer);
  }

  tocBtn.addEventListener('mouseenter', showPanel);
  tocBtn.addEventListener('mouseleave', scheduleHide);
  tocPanel.addEventListener('mouseenter', cancelHide);
  tocPanel.addEventListener('mouseleave', scheduleHide);

  // Close on outside click (for touch devices)
  document.addEventListener('mousedown', function(e) {
    if (tocDropdown && !tocDropdown.contains(e.target)) {
      tocPanel.style.display = 'none';
    }
  });

  // --- Type badge config ---
  var TYPE_COLORS = {
    table:    'var(--table-color)',
    markdown: 'var(--md-color)',
    plotly:   'var(--chart-color)',
    image:    'var(--image-color)',
    keyvalue: 'var(--kv-color)',
    form:     'var(--form-color)',
    decision: 'var(--decision-color)',
  };

  // --- Build TOC entries ---
  function buildToc() {
    tocPanel.innerHTML = '';

    var children = feed.children;
    var hasEntries = false;
    var latestVisibleId = null;

    for (var i = 0; i < children.length; i++) {
      var el = children[i];

      // Skip hidden elements
      if (el.classList.contains('hidden-by-filter')) continue;
      // Skip dismissed (soft-hidden) cards
      if (el.classList.contains('hidden-by-dismiss')) continue;
      // Skip empty state
      if (el.id === 'empty-state') continue;
      // Skip study separators
      if (el.classList.contains('study-separator')) continue;

      if (el.classList.contains('section-divider')) {
        // Section header
        var secEl = document.createElement('div');
        secEl.className = 'toc-section-header';
        var secTitleEl = el.querySelector('.section-title');
        secEl.textContent = secTitleEl ? secTitleEl.textContent : el.textContent;
        if (el.classList.contains('section-collapsed')) {
          secEl.textContent += ' (collapsed)';
        }
        (function(target) {
          secEl.onclick = function() {
            // Expand section if collapsed
            if (target.classList.contains('section-collapsed')) {
              target.classList.remove('section-collapsed');
              if (typeof toggleSectionCards === 'function') {
                toggleSectionCards(target, false);
              }
            }
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          };
        })(el);
        tocPanel.appendChild(secEl);
        hasEntries = true;
      } else if (el.classList.contains('card')) {
        var cardId = el.dataset.cardId;
        var cardData = findCardData(cardId);
        var title = '';
        var cardType = '';
        var isDecision = false;

        if (cardData) {
          title = cardData.title || cardData.card_type;
          cardType = (cardData.response_requested || cardData.response_action) ? 'decision' : cardData.card_type;
          isDecision = !!(cardData.response_requested || cardData.response_action);
        } else {
          var titleEl = el.querySelector('.card-title');
          title = titleEl ? titleEl.textContent : 'Untitled';
          var headerEl = el.querySelector('.card-header');
          cardType = headerEl ? headerEl.getAttribute('data-type') || '' : '';
          isDecision = cardType === 'decision';
        }

        var entry = document.createElement('a');
        entry.className = 'toc-entry';
        if (cardId === activeCardId) entry.classList.add('toc-active');
        entry.href = '#card=' + buildCardRef(cardId, title);
        entry.addEventListener('click', makeTocClickHandler(cardId, title));

        // Type badge
        var badge = document.createElement('span');
        badge.className = 'toc-type-badge';
        var isResponded = isDecision && el.classList.contains('responded');
        badge.textContent = isResponded ? '\u2713' : ((typeof TYPE_LETTERS !== 'undefined' && TYPE_LETTERS[cardType]) || '?');
        badge.style.background = isResponded ? 'var(--success)' : (TYPE_COLORS[cardType] || 'var(--text-muted)');
        entry.appendChild(badge);

        // Title
        var titleSpan = document.createElement('span');
        titleSpan.className = 'toc-entry-title';
        titleSpan.textContent = title;
        entry.appendChild(titleSpan);

        // Decision status
        if (isDecision) {
          var statusSpan = document.createElement('span');
          statusSpan.className = 'toc-entry-status';
          var sentBadge = el.querySelector('.sent-badge');
          if (sentBadge) {
            statusSpan.textContent = sentBadge.textContent;
            statusSpan.classList.add('toc-status-done');
          } else if (el.classList.contains('waiting')) {
            statusSpan.textContent = 'Waiting';
            statusSpan.classList.add('toc-status-waiting');
          }
          if (statusSpan.textContent) entry.appendChild(statusSpan);
        }

        tocPanel.appendChild(entry);
        hasEntries = true;
        latestVisibleId = cardId;
      }
    }

    // "Jump to latest" pinned at bottom
    if (latestVisibleId) {
      var jumpEl = document.createElement('a');
      jumpEl.className = 'toc-jump-latest';
      jumpEl.textContent = 'Jump to latest';
      jumpEl.href = '#card=' + buildCardRef(latestVisibleId, '');
      jumpEl.addEventListener('click', makeTocClickHandler(latestVisibleId, ''));
      tocPanel.appendChild(jumpEl);
    }

    if (!hasEntries) {
      var emptyEl = document.createElement('div');
      emptyEl.className = 'toc-empty';
      emptyEl.textContent = 'No cards yet';
      tocPanel.appendChild(emptyEl);
    }

    // Auto-scroll to active entry
    var activeEntry = tocPanel.querySelector('.toc-active');
    if (activeEntry) {
      activeEntry.scrollIntoView({ block: 'nearest' });
    }
  }

  function buildCardRef(cardId, title) {
    var slug = (title || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').substring(0, 30).replace(/-$/, '');
    var ref = cardId.substring(0, 6);
    if (slug) ref += '-' + slug;
    return ref;
  }

  function makeTocClickHandler(cardId, title) {
    return function(e) {
      e.preventDefault();
      var ref = buildCardRef(cardId, title);
      var hashParts = ['card=' + ref];
      if (state.activeStudyFilter) {
        hashParts.unshift('study=' + encodeURIComponent(state.activeStudyFilter));
      }
      history.pushState(null, '', '#' + hashParts.join('&'));
      applyHashCard(ref);
      // Hide panel after click
      tocPanel.style.display = 'none';
    };
  }

  function findCardData(cardId) {
    for (var i = 0; i < state.cards.length; i++) {
      if (state.cards[i].card_id === cardId) return state.cards[i];
    }
    return null;
  }

  // --- Active card tracking via IntersectionObserver ---
  function setupObserver() {
    if (observer) observer.disconnect();
    if (!('IntersectionObserver' in window)) return;

    observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          var cardId = entry.target.dataset.cardId;
          if (cardId && cardId !== activeCardId) {
            activeCardId = cardId;
            updateActiveEntry();
          }
        }
      });
    }, {
      rootMargin: '0px 0px -66% 0px',
      threshold: 0,
    });

    var cards = feed.querySelectorAll('.card[data-card-id]');
    cards.forEach(function(el) {
      if (!el.classList.contains('hidden-by-filter')) {
        observer.observe(el);
      }
    });
  }

  function updateActiveEntry() {
    var entries = tocPanel.querySelectorAll('.toc-entry');
    for (var i = 0; i < entries.length; i++) {
      var href = entries[i].getAttribute('href') || '';
      // Extract card id prefix from href
      var match = href.match(/card=([a-f0-9]+)/);
      var entryPrefix = match ? match[1] : '';
      if (activeCardId && activeCardId.indexOf(entryPrefix) === 0 && entryPrefix) {
        entries[i].classList.add('toc-active');
        if (tocPanel.style.display !== 'none') {
          entries[i].scrollIntoView({ block: 'nearest' });
        }
      } else {
        entries[i].classList.remove('toc-active');
      }
    }
  }

  // --- Button visibility ---
  function updateButtonVisibility() {
    var children = feed.children;
    var hasVisible = false;
    for (var i = 0; i < children.length; i++) {
      var el = children[i];
      if (el.id === 'empty-state') continue;
      if (el.classList.contains('hidden-by-filter')) continue;
      if (el.classList.contains('study-separator')) continue;
      if (el.classList.contains('card') || el.classList.contains('section-divider')) {
        hasVisible = true;
        break;
      }
    }
    tocDropdown.style.display = hasVisible ? '' : 'none';
  }

  // --- Public notify function ---
  window.tocNotifyChange = function() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function() {
      updateButtonVisibility();
      if (tocPanel.style.display !== 'none') {
        buildToc();
      }
      setupObserver();
    }, 100);
  };

  // Initial setup
  setupObserver();
  updateButtonVisibility();
})();
