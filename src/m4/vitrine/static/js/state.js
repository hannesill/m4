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
  markedLoaded: false,
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
};

var TYPE_LETTERS = {
  table: 'T',
  markdown: 'M',
  plotly: 'P',
  image: 'I',
  keyvalue: 'K',
  section: 'S',
  decision: '!',
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

var agentStatusEl = document.getElementById('agent-status');
