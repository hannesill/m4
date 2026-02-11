'use strict';

function renderPlotly(container, cardData) {
  var spec = cardData.preview && cardData.preview.spec;
  if (!spec) {
    container.textContent = 'No chart data';
    return;
  }

  var plotDiv = document.createElement('div');
  plotDiv.className = 'plotly-container';
  plotDiv.id = 'plotly-' + cardData.card_id;
  container.appendChild(plotDiv);

  function doRender() {
    var data = spec.data || [];
    var layout = Object.assign({}, spec.layout || {}, {
      autosize: true,
      margin: { l: 50, r: 30, t: 40, b: 50 },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { color: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() },
    });
    var config = { responsive: true, displayModeBar: true, displaylogo: false };

    window.Plotly.newPlot(plotDiv, data, layout, config).then(function() {
      // Attach point selection event (guard against missing .on method)
      if (typeof plotDiv.on === 'function') {
        plotDiv.on('plotly_selected', function(eventData) {
          if (eventData && state.ws && state.connected) {
            var points = (eventData.points || []).map(function(pt) {
              return { x: pt.x, y: pt.y, pointIndex: pt.pointIndex, curveNumber: pt.curveNumber };
            });
            var indices = points.map(function(pt) { return pt.pointIndex; });
            state.ws.send(JSON.stringify({
              type: 'vitrine.event',
              event_type: 'selection',
              card_id: cardData.card_id,
              payload: { selected_indices: indices, points: points },
            }));
          }
        });

        plotDiv.on('plotly_click', function(eventData) {
          if (eventData && state.ws && state.connected) {
            var points = (eventData.points || []).map(function(pt) {
              return { x: pt.x, y: pt.y, pointIndex: pt.pointIndex, curveNumber: pt.curveNumber };
            });
            state.ws.send(JSON.stringify({
              type: 'vitrine.event',
              event_type: 'point_click',
              card_id: cardData.card_id,
              payload: { points: points },
            }));
          }
        });
      }
    }).catch(function(err) {
      console.error('Plotly render failed for card ' + cardData.card_id + ':', err);
      plotDiv.innerHTML = '<div class="chart-loading" style="color:var(--text-muted)">'
        + 'Chart render error: ' + (err.message || err) + '</div>';
    });
  }

  if (window.Plotly) {
    doRender();
  } else {
    // Show loading indicator
    var loading = document.createElement('div');
    loading.className = 'chart-loading';
    loading.textContent = 'Loading chart library...';
    plotDiv.appendChild(loading);

    loadPlotly(function() {
      if (!window.Plotly) return;  // Script failed to load; onerror already shows message
      if (loading.parentNode === plotDiv) plotDiv.removeChild(loading);
      doRender();
    });
  }
}

function loadPlotly(callback) {
  if (window.Plotly) {
    if (callback) callback();
    return;
  }

  // Queue callbacks if already loading
  if (state.plotlyLoaded) {
    state.plotlyCallbacks.push(callback);
    return;
  }
  state.plotlyLoaded = true;
  state.plotlyCallbacks.push(callback);

  var script = document.createElement('script');
  script.src = '/static/vendor/plotly.min.js';
  script.onload = function() {
    var cbs = state.plotlyCallbacks;
    state.plotlyCallbacks = [];
    cbs.forEach(function(cb) { if (cb) cb(); });
  };
  script.onerror = function() {
    state.plotlyLoaded = false;
    var cbs = state.plotlyCallbacks;
    state.plotlyCallbacks = [];
    // Show error in any pending plot containers
    var containers = document.querySelectorAll('.plotly-container');
    containers.forEach(function(el) {
      if (!el.querySelector('.js-plotly-plot')) {
        el.innerHTML = '<div class="chart-loading" style="color:var(--text-muted)">Failed to load chart library</div>';
      }
    });
    cbs.forEach(function(cb) { if (cb) cb(); });
  };
  document.head.appendChild(script);
}

// Resize Plotly charts on window resize (debounced 150ms)
var _plotlyResizeTimer = null;
window.addEventListener('resize', function() {
  if (_plotlyResizeTimer) clearTimeout(_plotlyResizeTimer);
  _plotlyResizeTimer = setTimeout(function() {
    _plotlyResizeTimer = null;
    if (!window.Plotly) return;
    var plots = document.querySelectorAll('.plotly-container .js-plotly-plot');
    plots.forEach(function(plot) {
      window.Plotly.Plots.resize(plot);
    });
  }, 150);
});

// Re-color Plotly charts on theme change (additive listener)
themeToggleEl.addEventListener('click', function() {
  if (\!window.Plotly) return;
  var textColor = getComputedStyle(document.documentElement).getPropertyValue('--text').trim();
  var plots = document.querySelectorAll('.plotly-container .js-plotly-plot');
  plots.forEach(function(plot) {
    window.Plotly.relayout(plot, {
      'paper_bgcolor': 'transparent',
      'plot_bgcolor': 'transparent',
      'font.color': textColor,
    });
  });
});
