'use strict';

// Constants
var CONSTANTS = {
  RECONNECT_DELAY_INITIAL: 1000,
  RECONNECT_DELAY_MAX: 15000,
  LIVE_MODE_DELAY: 500,
  TABLE_PAGE_SIZE: 50,
  TOAST_DURATION: 1500,
  TOAST_ERROR_DURATION: 3000,
  PLOTLY_RESIZE_DEBOUNCE: 150,
  EVENT_QUEUE_MAX: 1000,
  DEFAULT_TIMEOUT: 300,
};

// ================================================================
// STATE & DOM REFERENCES
// ================================================================
var state = {
  ws: null,
  cards: [],
  connected: false,
  reconnectDelay: 1000,
  reconnectTimer: null,
  markedConfigured: false,
  plotlyLoaded: false,
  plotlyCallbacks: [],
  studyNames: [],
  activeStudyFilter: '',
  studies: [],
  activeStudy: null,
  dropdownOpen: false,
  liveMode: false,
  _autoSelectPending: false,
  selections: {},
  pendingCardScroll: null,
  showDismissed: false,
};

var EYE_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
var EYE_OFF_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

var TYPE_LETTERS = {
  table: 'T',
  markdown: 'M',
  plotly: 'P',
  image: 'I',
  keyvalue: 'K',
  section: 'S',
  decision: '!',
  agent: 'A',
};

var feed = document.getElementById('feed');
var emptyState = document.getElementById('empty-state');
var statusEl = document.getElementById('status');
var sessionInfoEl = document.getElementById('session-info');
var cardCountEl = document.getElementById('card-count');
var themeToggleEl = document.getElementById('theme-toggle');
var copyToastEl = document.getElementById('copy-toast');
var studyDropdownTrigger = document.getElementById('study-dropdown-trigger');
var studyDropdownPanel = document.getElementById('study-dropdown-panel');
var studyDropdownLabel = document.getElementById('study-dropdown-label');
var studyMetaBar = document.getElementById('study-metadata-bar');
var studyMetaLabel = document.getElementById('study-meta-label');
var studyMetaDetail = document.getElementById('study-meta-detail');

function dateGroupLabel(isoStr) {
  if (!isoStr) return 'Unknown';
  var d = new Date(isoStr);
  var today = new Date();
  today.setHours(0, 0, 0, 0);
  var yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  var dDate = new Date(d);
  dDate.setHours(0, 0, 0, 0);

  if (dDate.getTime() === today.getTime()) return 'Today';
  if (dDate.getTime() === yesterday.getTime()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatStudyTime(isoStr) {
  if (!isoStr) return '';
  var d = new Date(isoStr);
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}
