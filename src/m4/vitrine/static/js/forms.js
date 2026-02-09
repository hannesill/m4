'use strict';

// ================================================================
// FORM FIELDS — render, collect values, freeze confirmed state
// ================================================================
function renderForm(container, cardData) {
  var preview = cardData.preview;
  if (!preview || !preview.fields) return;
  renderFormFields(container, preview.fields);
}

function renderFormFields(container, fields) {
  var wrapper = document.createElement('div');
  wrapper.className = 'form-fields';

  fields.forEach(function(field) {
    var fieldEl = document.createElement('div');
    fieldEl.className = 'form-field';
    fieldEl.dataset.fieldName = field.name;
    fieldEl.dataset.fieldType = field.type;

    switch (field.type) {
      case 'dropdown':
        renderDropdownField(fieldEl, field);
        break;
      case 'multiselect':
        renderMultiSelectField(fieldEl, field);
        break;
      case 'slider':
        renderSliderField(fieldEl, field);
        break;
      case 'range_slider':
        renderRangeSliderField(fieldEl, field);
        break;
      case 'checkbox':
        renderCheckboxField(fieldEl, field);
        break;
      case 'toggle':
        renderToggleField(fieldEl, field);
        break;
      case 'radio':
        renderRadioField(fieldEl, field);
        break;
      case 'text':
        renderTextField(fieldEl, field);
        break;
      case 'date_range':
        renderDateRangeField(fieldEl, field);
        break;
      case 'number':
        renderNumberField(fieldEl, field);
        break;
      default:
        fieldEl.textContent = 'Unknown field type: ' + field.type;
    }

    wrapper.appendChild(fieldEl);
  });

  container.appendChild(wrapper);
}

function renderDropdownField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }

  var options = Array.isArray(field.options) ? field.options.map(function(opt) { return String(opt); }) : [];
  var defaultValue = field.default != null ? String(field.default) : '';
  var currentValue = '';
  if (options.length > 0) {
    currentValue = options.indexOf(defaultValue) !== -1 ? defaultValue : options[0];
  }

  var wrap = document.createElement('div');
  wrap.className = 'form-select';

  var hiddenInput = document.createElement('input');
  hiddenInput.type = 'hidden';
  hiddenInput.className = 'form-hidden-input';
  hiddenInput.dataset.fieldInput = field.name;
  hiddenInput.value = currentValue;
  wrap.appendChild(hiddenInput);

  var trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'form-select-trigger';

  var triggerValue = document.createElement('span');
  triggerValue.className = 'form-select-value';
  trigger.appendChild(triggerValue);

  var arrow = document.createElement('span');
  arrow.className = 'dd-arrow';
  arrow.innerHTML = '&#9662;';
  trigger.appendChild(arrow);
  wrap.appendChild(trigger);

  var panel = document.createElement('div');
  panel.className = 'form-select-panel';
  panel.style.display = 'none';
  wrap.appendChild(panel);

  function syncTrigger() {
    var val = hiddenInput.value || '';
    triggerValue.textContent = val || 'Select option';
    triggerValue.classList.toggle('placeholder', !val);
    var btns = panel.querySelectorAll('.form-select-option');
    btns.forEach(function(btn) {
      btn.classList.toggle('selected', btn.dataset.value === val);
    });
  }

  if (options.length === 0) {
    var empty = document.createElement('div');
    empty.className = 'form-select-empty';
    empty.textContent = 'No options';
    panel.appendChild(empty);
  } else {
    options.forEach(function(opt) {
      var optionBtn = document.createElement('button');
      optionBtn.type = 'button';
      optionBtn.className = 'form-select-option';
      optionBtn.textContent = opt;
      optionBtn.dataset.value = opt;
      optionBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        hiddenInput.value = opt;
        syncTrigger();
        closePanel();
      });
      panel.appendChild(optionBtn);
    });
  }

  var outsideListener = null;
  function openPanel() {
    panel.style.display = '';
    trigger.classList.add('open');
    setTimeout(function() {
      outsideListener = function(e) {
        if (!wrap.contains(e.target)) closePanel();
      };
      document.addEventListener('mousedown', outsideListener);
    }, 0);
  }

  function closePanel() {
    panel.style.display = 'none';
    trigger.classList.remove('open');
    if (outsideListener) {
      document.removeEventListener('mousedown', outsideListener);
      outsideListener = null;
    }
  }

  trigger.addEventListener('click', function(e) {
    e.stopPropagation();
    if (panel.style.display === 'none') {
      openPanel();
    } else {
      closePanel();
    }
  });

  trigger.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closePanel();
    }
  });

  syncTrigger();
  container.appendChild(wrap);
}

function toIsoDate(dateObj) {
  if (!(dateObj instanceof Date) || isNaN(dateObj.getTime())) return '';
  var y = String(dateObj.getFullYear());
  var m = String(dateObj.getMonth() + 1).padStart(2, '0');
  var d = String(dateObj.getDate()).padStart(2, '0');
  return y + '-' + m + '-' + d;
}

function parseIsoDate(isoStr) {
  if (!isoStr || !/^\d{4}-\d{2}-\d{2}$/.test(isoStr)) return null;
  var parts = isoStr.split('-');
  return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
}

function formatIsoDate(isoStr) {
  var parsed = parseIsoDate(isoStr);
  if (!parsed) return '';
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function createDatePicker(fieldName, rangeEnd, initialValue) {
  var picker = document.createElement('div');
  picker.className = 'form-date-picker';

  var hiddenInput = document.createElement('input');
  hiddenInput.type = 'hidden';
  hiddenInput.className = 'form-hidden-input';
  hiddenInput.dataset.fieldInput = fieldName;
  hiddenInput.dataset.rangeEnd = rangeEnd;
  hiddenInput.value = initialValue || '';
  picker.appendChild(hiddenInput);

  var trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'form-date-trigger';

  var valueEl = document.createElement('span');
  valueEl.className = 'form-date-value';
  trigger.appendChild(valueEl);

  var arrow = document.createElement('span');
  arrow.className = 'dd-arrow';
  arrow.innerHTML = '&#9662;';
  trigger.appendChild(arrow);
  picker.appendChild(trigger);

  var panel = document.createElement('div');
  panel.className = 'form-calendar-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Date picker');
  panel.style.display = 'none';

  var header = document.createElement('div');
  header.className = 'form-calendar-header';

  var prevBtn = document.createElement('button');
  prevBtn.type = 'button';
  prevBtn.className = 'form-calendar-nav-btn';
  prevBtn.innerHTML = '&#9664;';

  var monthLabel = document.createElement('div');
  monthLabel.className = 'form-calendar-month';

  var nextBtn = document.createElement('button');
  nextBtn.type = 'button';
  nextBtn.className = 'form-calendar-nav-btn';
  nextBtn.innerHTML = '&#9654;';

  header.appendChild(prevBtn);
  header.appendChild(monthLabel);
  header.appendChild(nextBtn);
  panel.appendChild(header);

  var weekdays = document.createElement('div');
  weekdays.className = 'form-calendar-weekdays';
  ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].forEach(function(label) {
    var weekday = document.createElement('div');
    weekday.className = 'form-calendar-weekday';
    weekday.textContent = label;
    weekdays.appendChild(weekday);
  });
  panel.appendChild(weekdays);

  var daysGrid = document.createElement('div');
  daysGrid.className = 'form-calendar-days';
  panel.appendChild(daysGrid);
  picker.appendChild(panel);

  var selectedDate = parseIsoDate(hiddenInput.value);
  var visibleMonth = selectedDate || new Date();
  visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);

  function updateValueLabel() {
    var text = formatIsoDate(hiddenInput.value);
    valueEl.textContent = text || 'Select date';
    valueEl.classList.toggle('placeholder', !text);
  }

  function renderCalendar() {
    monthLabel.textContent = visibleMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    daysGrid.innerHTML = '';

    var firstOfMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
    var gridStart = new Date(firstOfMonth);
    gridStart.setDate(1 - firstOfMonth.getDay());
    var todayIso = toIsoDate(new Date());
    var selectedIso = hiddenInput.value || '';

    for (var i = 0; i < 42; i++) {
      var cellDate = new Date(gridStart);
      cellDate.setDate(gridStart.getDate() + i);
      var iso = toIsoDate(cellDate);
      var dayBtn = document.createElement('button');
      dayBtn.type = 'button';
      dayBtn.className = 'form-calendar-day';
      dayBtn.textContent = String(cellDate.getDate());
      dayBtn.dataset.value = iso;

      if (cellDate.getMonth() !== visibleMonth.getMonth()) {
        dayBtn.classList.add('other-month');
      }
      if (iso === todayIso) {
        dayBtn.classList.add('today');
      }
      if (iso === selectedIso) {
        dayBtn.classList.add('selected');
      }

      dayBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        hiddenInput.value = this.dataset.value || '';
        updateValueLabel();
        visibleMonth = parseIsoDate(hiddenInput.value) || visibleMonth;
        visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
        closePanel();
      });

      daysGrid.appendChild(dayBtn);
    }
  }

  prevBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1);
    renderCalendar();
  });

  nextBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1);
    renderCalendar();
  });

  var outsideListener = null;
  function openPanel() {
    var selected = parseIsoDate(hiddenInput.value);
    if (selected) {
      visibleMonth = new Date(selected.getFullYear(), selected.getMonth(), 1);
    }
    renderCalendar();
    panel.style.display = '';
    trigger.classList.add('open');
    setTimeout(function() {
      outsideListener = function(e) {
        if (!picker.contains(e.target)) closePanel();
      };
      document.addEventListener('mousedown', outsideListener);
    }, 0);
  }

  function closePanel() {
    panel.style.display = 'none';
    trigger.classList.remove('open');
    if (outsideListener) {
      document.removeEventListener('mousedown', outsideListener);
      outsideListener = null;
    }
  }

  trigger.addEventListener('click', function(e) {
    e.stopPropagation();
    if (panel.style.display === 'none') {
      openPanel();
    } else {
      closePanel();
    }
  });

  trigger.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      closePanel();
    }
    if (e.key === 'Backspace' || e.key === 'Delete') {
      e.preventDefault();
      hiddenInput.value = '';
      updateValueLabel();
    }
  });

  updateValueLabel();
  return picker;
}

function renderMultiSelectField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var optionsDiv = document.createElement('div');
  optionsDiv.className = 'form-multiselect-options';
  var defaults = field.default || [];
  (field.options || []).forEach(function(opt) {
    var optLabel = document.createElement('label');
    optLabel.className = 'form-multiselect-option';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = opt;
    cb.dataset.fieldInput = field.name;
    if (defaults.indexOf(opt) !== -1) cb.checked = true;
    optLabel.appendChild(cb);
    optLabel.appendChild(document.createTextNode(opt));
    optionsDiv.appendChild(optLabel);
  });
  container.appendChild(optionsDiv);
}

function renderSliderField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var row = document.createElement('div');
  row.className = 'form-slider-row';
  var slider = document.createElement('input');
  slider.type = 'range';
  slider.min = field.min != null ? field.min : 0;
  slider.max = field.max != null ? field.max : 100;
  slider.step = field.step != null ? field.step : ((field.max - field.min) <= 1 ? 0.01 : 1);
  slider.value = field.default != null ? field.default : field.min;
  slider.dataset.fieldInput = field.name;
  var valueEl = document.createElement('span');
  valueEl.className = 'form-slider-value';
  valueEl.textContent = slider.value;
  slider.oninput = function() { valueEl.textContent = slider.value; };
  row.appendChild(slider);
  row.appendChild(valueEl);
  container.appendChild(row);
}

function renderRangeSliderField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var row = document.createElement('div');
  row.className = 'form-range-slider-row';
  var defaults = field.default || [field.min, field.max];
  var step = field.step != null ? field.step : ((field.max - field.min) <= 1 ? 0.01 : 1);

  var sliderLow = document.createElement('input');
  sliderLow.type = 'range';
  sliderLow.min = field.min != null ? field.min : 0;
  sliderLow.max = field.max != null ? field.max : 100;
  sliderLow.step = step;
  sliderLow.value = defaults[0];
  sliderLow.dataset.fieldInput = field.name;
  sliderLow.dataset.rangeEnd = 'low';

  var sliderHigh = document.createElement('input');
  sliderHigh.type = 'range';
  sliderHigh.min = field.min != null ? field.min : 0;
  sliderHigh.max = field.max != null ? field.max : 100;
  sliderHigh.step = step;
  sliderHigh.value = defaults[1];
  sliderHigh.dataset.fieldInput = field.name;
  sliderHigh.dataset.rangeEnd = 'high';

  var valueEl = document.createElement('span');
  valueEl.className = 'form-range-value';
  valueEl.textContent = sliderLow.value + ' \u2013 ' + sliderHigh.value;

  function updateRange() {
    var lo = parseFloat(sliderLow.value);
    var hi = parseFloat(sliderHigh.value);
    if (lo > hi) { sliderLow.value = hi; lo = hi; }
    if (hi < lo) { sliderHigh.value = lo; hi = lo; }
    valueEl.textContent = lo + ' \u2013 ' + hi;
  }
  sliderLow.oninput = updateRange;
  sliderHigh.oninput = updateRange;

  row.appendChild(sliderLow);
  row.appendChild(valueEl);
  row.appendChild(sliderHigh);
  container.appendChild(row);
}

function renderCheckboxField(container, field) {
  var row = document.createElement('div');
  row.className = 'form-check-row';
  var cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = !!field.default;
  cb.dataset.fieldInput = field.name;
  cb.id = 'form-cb-' + field.name;
  row.appendChild(cb);
  if (field.label) {
    var label = document.createElement('label');
    label.className = 'form-check-label';
    label.htmlFor = cb.id;
    label.textContent = field.label;
    row.appendChild(label);
  }
  container.appendChild(row);
}

function renderToggleField(container, field) {
  var row = document.createElement('div');
  row.className = 'form-check-row';
  var toggle = document.createElement('label');
  toggle.className = 'form-toggle-switch';
  var input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = !!field.default;
  input.dataset.fieldInput = field.name;
  var track = document.createElement('span');
  track.className = 'form-toggle-track';
  toggle.appendChild(input);
  toggle.appendChild(track);
  row.appendChild(toggle);
  if (field.label) {
    var label = document.createElement('span');
    label.className = 'form-check-label';
    label.textContent = field.label;
    row.appendChild(label);
  }
  container.appendChild(row);
}

function renderRadioField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var optionsDiv = document.createElement('div');
  optionsDiv.className = 'form-radio-options';
  var groupName = 'radio-' + field.name + '-' + Math.random().toString(36).slice(2, 8);
  (field.options || []).forEach(function(opt) {
    var optLabel = document.createElement('label');
    optLabel.className = 'form-radio-option';
    var radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = groupName;
    radio.value = opt;
    radio.dataset.fieldInput = field.name;
    if (field.default === opt) radio.checked = true;
    optLabel.appendChild(radio);
    optLabel.appendChild(document.createTextNode(opt));
    optionsDiv.appendChild(optLabel);
  });
  container.appendChild(optionsDiv);
}

function renderTextField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var input = document.createElement('input');
  input.type = 'text';
  input.value = field.default || '';
  input.placeholder = field.placeholder || '';
  input.dataset.fieldInput = field.name;
  container.appendChild(input);
}

function renderDateRangeField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var row = document.createElement('div');
  row.className = 'form-date-range-row';
  var defaults = field.default || ['', ''];
  var startPicker = createDatePicker(field.name, 'start', defaults[0] || '');

  var sep = document.createElement('span');
  sep.className = 'form-date-range-sep';
  sep.textContent = 'to';

  var endPicker = createDatePicker(field.name, 'end', defaults[1] || '');

  row.appendChild(startPicker);
  row.appendChild(sep);
  row.appendChild(endPicker);
  container.appendChild(row);
}

function renderNumberField(container, field) {
  if (field.label) {
    var label = document.createElement('div');
    label.className = 'form-field-label';
    label.textContent = field.label;
    container.appendChild(label);
  }
  var input = document.createElement('input');
  input.type = 'number';
  if (field.default != null) input.value = field.default;
  if (field.min != null) input.min = field.min;
  if (field.max != null) input.max = field.max;
  if (field.step != null) input.step = field.step;
  input.dataset.fieldInput = field.name;
  container.appendChild(input);
}

function collectFormValues(cardEl) {
  var values = {};
  var fields = cardEl.querySelectorAll('.form-field');
  fields.forEach(function(fieldEl) {
    var name = fieldEl.dataset.fieldName;
    var type = fieldEl.dataset.fieldType;

    switch (type) {
      case 'dropdown': {
        var hidden = fieldEl.querySelector('input.form-hidden-input[data-field-input]');
        if (hidden) {
          values[name] = hidden.value;
          break;
        }
        var sel = fieldEl.querySelector('select');
        if (sel) values[name] = sel.value;
        break;
      }
      case 'multiselect': {
        var checked = fieldEl.querySelectorAll('input[type="checkbox"]:checked');
        values[name] = Array.prototype.map.call(checked, function(cb) { return cb.value; });
        break;
      }
      case 'slider': {
        var sl = fieldEl.querySelector('input[type="range"]');
        if (sl) values[name] = parseFloat(sl.value);
        break;
      }
      case 'range_slider': {
        var lo = fieldEl.querySelector('input[data-range-end="low"]');
        var hi = fieldEl.querySelector('input[data-range-end="high"]');
        if (lo && hi) values[name] = [parseFloat(lo.value), parseFloat(hi.value)];
        break;
      }
      case 'checkbox':
      case 'toggle': {
        var cb = fieldEl.querySelector('input[type="checkbox"]');
        if (cb) values[name] = cb.checked;
        break;
      }
      case 'radio': {
        var selected = fieldEl.querySelector('input[type="radio"]:checked');
        values[name] = selected ? selected.value : null;
        break;
      }
      case 'text': {
        var txt = fieldEl.querySelector('input[type="text"]');
        if (txt) values[name] = txt.value;
        break;
      }
      case 'date_range': {
        var s = fieldEl.querySelector('input[data-range-end="start"]');
        var e = fieldEl.querySelector('input[data-range-end="end"]');
        if (s && e) values[name] = [s.value, e.value];
        break;
      }
      case 'number': {
        var num = fieldEl.querySelector('input[type="number"]');
        if (num) values[name] = num.value !== '' ? parseFloat(num.value) : null;
        break;
      }
    }
  });
  return values;
}

function renderFrozenForm(container, values, fields) {
  var frozen = document.createElement('div');
  frozen.className = 'form-frozen';

  // Build a map of field names to labels
  var labelMap = {};
  (fields || []).forEach(function(f) {
    labelMap[f.name] = f.label || f.name;
  });

  Object.keys(values).forEach(function(key) {
    var val = values[key];
    var item = document.createElement('span');
    item.className = 'form-frozen-item';

    var labelSpan = document.createElement('span');
    labelSpan.className = 'frozen-label';
    labelSpan.textContent = (labelMap[key] || key) + ':';
    item.appendChild(labelSpan);

    var valueSpan = document.createElement('span');
    valueSpan.className = 'frozen-value';
    if (typeof val === 'boolean') {
      valueSpan.textContent = val ? 'yes' : 'no';
    } else if (Array.isArray(val)) {
      valueSpan.textContent = val.join(' \u2013 ');
    } else {
      valueSpan.textContent = String(val);
    }
    item.appendChild(valueSpan);
    frozen.appendChild(item);
  });

  container.appendChild(frozen);
}
