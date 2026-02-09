'use strict';

// ================================================================
// THEME
// ================================================================
function initTheme() {
  var saved = localStorage.getItem('m4-vitrine-theme');
  if (saved === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    themeToggleEl.innerHTML = '&#9788;';
  }
}

themeToggleEl.onclick = function() {
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (isDark) {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('m4-vitrine-theme', 'light');
    themeToggleEl.innerHTML = '&#9789;';
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('m4-vitrine-theme', 'dark');
    themeToggleEl.innerHTML = '&#9788;';
  }
};

initTheme();
