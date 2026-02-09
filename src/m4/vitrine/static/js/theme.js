'use strict';

// ================================================================
// THEME
// ================================================================
var _sunIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>';
var _moonIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';

function initTheme() {
  var saved = localStorage.getItem('m4-vitrine-theme');
  if (saved === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    themeToggleEl.innerHTML = _sunIcon;
  } else {
    themeToggleEl.innerHTML = _moonIcon;
  }
}

themeToggleEl.onclick = function() {
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (isDark) {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('m4-vitrine-theme', 'light');
    themeToggleEl.innerHTML = _moonIcon;
    _swapHljsTheme(false);
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('m4-vitrine-theme', 'dark');
    themeToggleEl.innerHTML = _sunIcon;
    _swapHljsTheme(true);
  }
};

// Swap highlight.js theme if loaded
function _swapHljsTheme(dark) {
  var el = document.getElementById('hljs-theme');
  if (!el) return;
  el.href = dark
    ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
    : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
}

initTheme();
