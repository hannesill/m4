/**
 * M4 Cohort Builder MCP App
 *
 * Interactive cohort filtering UI that runs in MCP Apps-enabled hosts.
 * Uses the @modelcontextprotocol/ext-apps SDK for host communication.
 */

import {
  App,
  applyDocumentTheme,
  applyHostStyleVariables,
  applyHostFonts,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";

// Initialize the MCP App
const app = new App({
  name: "M4 Cohort Builder",
  version: "1.0.0",
});

// DOM Elements
const loadingOverlay = document.getElementById("loadingOverlay") as HTMLElement;
const errorMessage = document.getElementById("errorMessage") as HTMLElement;
const patientCount = document.getElementById("patientCount") as HTMLElement;
const patientCountStat = document.getElementById("patientCountStat") as HTMLElement;
const admissionCountStat = document.getElementById("admissionCountStat") as HTMLElement;
const icuStayCountStat = document.getElementById("icuStayCountStat") as HTMLElement;
const icuStayStatCard = document.getElementById("icuStayStatCard") as HTMLElement;
const ageChart = document.getElementById("ageChart") as HTMLElement;
const genderChart = document.getElementById("genderChart") as HTMLElement;
const sqlCode = document.getElementById("sqlCode") as HTMLElement;
const sqlToggle = document.getElementById("sqlToggle") as HTMLElement;
const sqlToggleIcon = document.getElementById("sqlToggleIcon") as HTMLElement;
const ageMinInput = document.getElementById("ageMin") as HTMLInputElement;
const ageMaxInput = document.getElementById("ageMax") as HTMLInputElement;
const genderRadios = document.querySelectorAll<HTMLInputElement>('input[name="gender"]');
const icdInput = document.getElementById("icdInput") as HTMLInputElement;
const icdTags = document.getElementById("icdTags") as HTMLElement;
const icdMatchModeRadios = document.querySelectorAll<HTMLInputElement>('input[name="icdMatchMode"]');
const icuStayRadios = document.querySelectorAll<HTMLInputElement>('input[name="icuStay"]');
const mortalityRadios = document.querySelectorAll<HTMLInputElement>('input[name="mortality"]');
const fullscreenBtn = document.getElementById("fullscreenBtn") as HTMLButtonElement;
const fullscreenIcon = document.getElementById("fullscreenIcon") as SVGElement;

// Types
interface CohortResult {
  patient_count: number;
  admission_count: number;
  icu_stay_count?: number;
  demographics: {
    age: Record<string, number>;
    gender: Record<string, number>;
  };
  sql: string;
}

// State
let debounceTimer: number | null = null;
let sqlVisible = false;
let icdCodes: string[] = [];
let currentDisplayMode: "inline" | "fullscreen" = "inline";
let lastResult: CohortResult | null = null;
let previousCounts = { patients: 0, admissions: 0, icuStays: 0 };
let baselinePatientCount: number | null = null;

// Phase 4: Request lifecycle management
let currentRequestId = 0; // Monotonically increasing request ID for ordering
let isVisible = true; // Track visibility for resource management
let pendingRefresh = false; // Queue refresh when invisible

// DOM element for percentage
const countPercentage = document.getElementById("countPercentage") as HTMLElement;

// --- Utility Functions ---

function showLoading(): void {
  loadingOverlay.classList.remove("hidden");
  patientCount.classList.add("loading");
}

function hideLoading(): void {
  loadingOverlay.classList.add("hidden");
  patientCount.classList.remove("loading");
}

function showError(message: string): void {
  errorMessage.textContent = message;
  errorMessage.classList.add("visible");
}

function hideError(): void {
  errorMessage.classList.remove("visible");
}

function formatNumber(n: number): string {
  return n.toLocaleString();
}

/**
 * Animate a number from one value to another with easing
 */
function animateNumber(
  element: HTMLElement,
  from: number,
  to: number,
  duration: number = 300
): void {
  const startTime = performance.now();
  const diff = to - from;

  // Skip animation if no change or initial load
  if (diff === 0 || from === 0) {
    element.textContent = formatNumber(to);
    return;
  }

  // Add pulse animation class
  element.classList.add("count-pulse");

  function update(currentTime: number) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);

    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(from + diff * eased);

    element.textContent = formatNumber(current);

    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.classList.remove("count-pulse");
    }
  }

  requestAnimationFrame(update);
}

/**
 * Update model context with current cohort state for LLM awareness
 */
async function updateModelContextWithCohort(
  criteria: Record<string, unknown>,
  result: CohortResult
): Promise<void> {
  const criteriaLines: string[] = [];

  if (criteria.age_min !== undefined || criteria.age_max !== undefined) {
    const min = criteria.age_min ?? "any";
    const max = criteria.age_max ?? "any";
    criteriaLines.push(`- Age: ${min} to ${max}`);
  }
  if (criteria.gender) {
    criteriaLines.push(`- Gender: ${criteria.gender === "M" ? "Male" : "Female"}`);
  }
  if (criteria.icd_codes && Array.isArray(criteria.icd_codes) && criteria.icd_codes.length > 0) {
    const matchMode = criteria.icd_match_all ? "all (AND)" : "any (OR)";
    criteriaLines.push(`- ICD codes (${matchMode}): ${(criteria.icd_codes as string[]).join(", ")}`);
  }
  if (criteria.has_icu_stay !== undefined) {
    criteriaLines.push(`- ICU stay: ${criteria.has_icu_stay ? "Yes" : "No"}`);
  }
  if (criteria.in_hospital_mortality !== undefined) {
    criteriaLines.push(`- In-hospital mortality: ${criteria.in_hospital_mortality ? "Yes (deceased)" : "No (survivors)"}`);
  }

  const icuStayLine = result.icu_stay_count !== undefined
    ? `\n**ICU Stays:** ${formatNumber(result.icu_stay_count)}`
    : "";

  const markdown = `---
patient-count: ${result.patient_count}
admission-count: ${result.admission_count}${result.icu_stay_count !== undefined ? `\nicu-stay-count: ${result.icu_stay_count}` : ""}
---

Current cohort selection in M4 Cohort Builder:

**Patients:** ${formatNumber(result.patient_count)}
**Admissions:** ${formatNumber(result.admission_count)}${icuStayLine}

${criteriaLines.length > 0 ? "**Applied filters:**\n" + criteriaLines.join("\n") : "**Filters:** None (all patients)"}`;

  try {
    await app.updateModelContext({
      content: [{ type: "text", text: markdown }],
    });
  } catch {
    // Silently ignore if host doesn't support updateModelContext
  }
}

/**
 * Toggle fullscreen mode
 */
async function toggleFullscreen(): Promise<void> {
  const ctx = app.getHostContext();
  const newMode = currentDisplayMode === "inline" ? "fullscreen" : "inline";

  if (ctx?.availableDisplayModes?.includes(newMode)) {
    try {
      const result = await app.requestDisplayMode({ mode: newMode });
      currentDisplayMode = result.mode as "inline" | "fullscreen";
      updateFullscreenUI();
    } catch {
      // Host denied the request
    }
  }
}

/**
 * Update UI based on current fullscreen state
 */
function updateFullscreenUI(): void {
  const isFullscreen = currentDisplayMode === "fullscreen";
  document.body.classList.toggle("fullscreen", isFullscreen);

  // Update icon to show appropriate action
  if (isFullscreen) {
    // Show minimize icon
    fullscreenIcon.innerHTML = '<path d="M4 14h6m0 0v6m0-6L3 21M20 10h-6m0 0V4m0 6l7-7"/>';
  } else {
    // Show expand icon
    fullscreenIcon.innerHTML = '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>';
  }
}

function updateDisplay(result: CohortResult): void {
  // Store baseline on first load (when no filters are applied)
  if (baselinePatientCount === null) {
    baselinePatientCount = result.patient_count;
  }

  // Update counts with animation
  animateNumber(patientCount, previousCounts.patients, result.patient_count);
  animateNumber(patientCountStat, previousCounts.patients, result.patient_count);
  animateNumber(admissionCountStat, previousCounts.admissions, result.admission_count);

  // Update ICU stay count (only shown when ICU filter is active)
  if (result.icu_stay_count !== undefined && icuStayStatCard && icuStayCountStat) {
    icuStayStatCard.style.display = "block";
    animateNumber(icuStayCountStat, previousCounts.icuStays, result.icu_stay_count);
  } else if (icuStayStatCard) {
    icuStayStatCard.style.display = "none";
  }

  // Update percentage display
  if (baselinePatientCount > 0) {
    const percentage = (result.patient_count / baselinePatientCount) * 100;
    countPercentage.textContent = `${percentage.toFixed(1)}%`;
    countPercentage.style.display = "inline";
  } else {
    countPercentage.style.display = "none";
  }

  // Store current counts for next animation
  previousCounts = {
    patients: result.patient_count,
    admissions: result.admission_count,
    icuStays: result.icu_stay_count ?? 0,
  };

  // Store result for model context updates
  lastResult = result;

  // Update age chart
  const ageBuckets = [
    "0-19",
    "20-29",
    "30-39",
    "40-49",
    "50-59",
    "60-69",
    "70-79",
    "80-89",
    "90+",
  ];
  const maxAge = Math.max(...Object.values(result.demographics.age), 1);

  ageChart.innerHTML = ageBuckets
    .map((bucket) => {
      const count = result.demographics.age[bucket] || 0;
      const percentage = (count / maxAge) * 100;
      return `
        <div class="bar-row">
          <span class="bar-label">${bucket}</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${percentage}%"></div>
          </div>
          <span class="bar-value">${formatNumber(count)}</span>
        </div>
      `;
    })
    .join("");

  // Update gender chart
  const genders = ["F", "M"];
  const genderLabels: Record<string, string> = { F: "Female", M: "Male" };
  const maxGender = Math.max(...Object.values(result.demographics.gender), 1);

  genderChart.innerHTML = genders
    .map((g) => {
      const count = result.demographics.gender[g] || 0;
      const percentage = (count / maxGender) * 100;
      return `
        <div class="bar-row">
          <span class="bar-label">${genderLabels[g]}</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${percentage}%"></div>
          </div>
          <span class="bar-value">${formatNumber(count)}</span>
        </div>
      `;
    })
    .join("");

  // Update SQL preview
  sqlCode.textContent = result.sql;
}

function getCriteriaFromForm(): Record<string, unknown> {
  const criteria: Record<string, unknown> = {};

  const ageMin = ageMinInput.value ? parseInt(ageMinInput.value, 10) : null;
  const ageMax = ageMaxInput.value ? parseInt(ageMaxInput.value, 10) : null;

  if (ageMin !== null && !isNaN(ageMin)) {
    criteria.age_min = ageMin;
  }
  if (ageMax !== null && !isNaN(ageMax)) {
    criteria.age_max = ageMax;
  }

  const selectedGender = document.querySelector<HTMLInputElement>(
    'input[name="gender"]:checked'
  );
  if (selectedGender && selectedGender.value) {
    criteria.gender = selectedGender.value;
  }

  // ICD codes
  if (icdCodes.length > 0) {
    criteria.icd_codes = [...icdCodes];

    // ICD match mode (AND/OR)
    const selectedMatchMode = document.querySelector<HTMLInputElement>(
      'input[name="icdMatchMode"]:checked'
    );
    if (selectedMatchMode && selectedMatchMode.value === "all") {
      criteria.icd_match_all = true;
    }
  }

  // ICU stay
  const selectedIcuStay = document.querySelector<HTMLInputElement>(
    'input[name="icuStay"]:checked'
  );
  if (selectedIcuStay && selectedIcuStay.value) {
    criteria.has_icu_stay = selectedIcuStay.value === "true";
  }

  // In-hospital mortality
  const selectedMortality = document.querySelector<HTMLInputElement>(
    'input[name="mortality"]:checked'
  );
  if (selectedMortality && selectedMortality.value) {
    criteria.in_hospital_mortality = selectedMortality.value === "true";
  }

  return criteria;
}

// --- ICD Tag Management ---

function renderIcdTags(): void {
  icdTags.innerHTML = icdCodes
    .map(
      (code, index) => `
        <span class="tag">
          ${code}
          <button class="tag-remove" data-index="${index}">&times;</button>
        </span>
      `
    )
    .join("");

  // Add click handlers for remove buttons
  icdTags.querySelectorAll(".tag-remove").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const index = parseInt((e.target as HTMLElement).dataset.index || "0", 10);
      icdCodes.splice(index, 1);
      renderIcdTags();
      onCriteriaChange();
    });
  });
}

function addIcdCode(code: string): void {
  // Normalize: uppercase, trim
  const normalized = code.trim().toUpperCase();

  // Validate format (alphanumeric and dots only)
  if (!/^[A-Z0-9.]+$/.test(normalized)) {
    return;
  }

  // Avoid duplicates
  if (!icdCodes.includes(normalized)) {
    icdCodes.push(normalized);
    renderIcdTags();
    onCriteriaChange();
  }
}

/**
 * Client-side validation for age range
 * Returns error message if invalid, null if valid
 */
function validateAgeRange(): string | null {
  const ageMin = ageMinInput.value ? parseInt(ageMinInput.value, 10) : null;
  const ageMax = ageMaxInput.value ? parseInt(ageMaxInput.value, 10) : null;

  if (ageMin !== null && !isNaN(ageMin)) {
    if (ageMin < 0 || ageMin > 130) {
      return "Minimum age must be between 0 and 130";
    }
  }
  if (ageMax !== null && !isNaN(ageMax)) {
    if (ageMax < 0 || ageMax > 130) {
      return "Maximum age must be between 0 and 130";
    }
  }
  if (ageMin !== null && ageMax !== null && !isNaN(ageMin) && !isNaN(ageMax)) {
    if (ageMin > ageMax) {
      return "Minimum age cannot be greater than maximum age";
    }
  }
  return null;
}

async function refreshCohort(): Promise<void> {
  // Phase 4: If not visible, queue refresh for when we become visible
  if (!isVisible) {
    pendingRefresh = true;
    return;
  }

  // Phase 4: Client-side validation before sending request
  const validationError = validateAgeRange();
  if (validationError) {
    showError(validationError);
    return;
  }

  showLoading();
  hideError();

  // Phase 4: Track request ID for ordering - ignore stale responses
  currentRequestId++;
  const thisRequestId = currentRequestId;

  try {
    const criteria = getCriteriaFromForm();
    const result = await app.callServerTool({
      name: "query_cohort",
      arguments: criteria,
    });

    // Phase 4: Ignore response if a newer request has been made
    if (thisRequestId !== currentRequestId) {
      return; // Stale response, discard
    }

    // Parse the result - it comes as content array with text
    const textContent = result.content?.find(
      (c: { type: string }) => c.type === "text"
    );
    if (textContent && "text" in textContent) {
      const data = JSON.parse(textContent.text as string);

      // Check for error response
      if (data.error) {
        showError(data.error);
        return;
      }

      const cohortResult = data as CohortResult;
      updateDisplay(cohortResult);

      // Update model context so LLM knows current cohort state
      await updateModelContextWithCohort(criteria, cohortResult);
    }
  } catch (error) {
    // Phase 4: Ignore errors from stale requests
    if (thisRequestId !== currentRequestId) {
      return;
    }
    const message = error instanceof Error ? error.message : "Query failed";
    showError(message);
  } finally {
    // Phase 4: Only hide loading if this is still the current request
    if (thisRequestId === currentRequestId) {
      hideLoading();
    }
  }
}

function onCriteriaChange(): void {
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = window.setTimeout(refreshCohort, 300);
}

// --- MCP App Handlers ---

// Handle initial tool input (called when cohort_builder is invoked)
app.ontoolinput = () => {
  showLoading();
};

// Handle tool result (initial data from cohort_builder)
app.ontoolresult = () => {
  hideLoading();
  // Trigger initial query to get cohort data
  refreshCohort();
};

/**
 * Detect system color scheme preference
 */
function getSystemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Apply host context styling (theme, CSS variables, fonts, safe areas)
 * Uses SDK helpers to properly set data-theme, color-scheme, and CSS variables
 */
function applyHostContext(ctx: McpUiHostContext): void {
  // Apply theme - SDK sets both data-theme and color-scheme
  if (ctx.theme) {
    applyDocumentTheme(ctx.theme);
  }

  // Apply host CSS variables if provided
  if (ctx.styles?.variables) {
    applyHostStyleVariables(ctx.styles.variables);
  }

  // Apply host fonts if provided
  if (ctx.styles?.css?.fonts) {
    applyHostFonts(ctx.styles.css.fonts);
  }

  // Apply safe area insets
  if (ctx.safeAreaInsets) {
    const { top, right, bottom, left } = ctx.safeAreaInsets;
    document.body.style.padding = `${top}px ${right}px ${bottom}px ${left}px`;
  }

  // Handle display mode changes
  if (ctx.displayMode) {
    currentDisplayMode = ctx.displayMode as "inline" | "fullscreen";
    updateFullscreenUI();
  }

  // Show/hide fullscreen button based on availability
  if (ctx.availableDisplayModes) {
    const canFullscreen = ctx.availableDisplayModes.includes("fullscreen");
    fullscreenBtn.style.display = canFullscreen ? "block" : "none";
  }
}

// Handle host context changes (theme, safe area, display modes, etc.)
app.onhostcontextchanged = (ctx) => {
  applyHostContext(ctx);
};

// Handle teardown (cleanup)
app.onteardown = async () => {
  // Cancel pending debounce
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer);
  }
  // Phase 4: Cancel any in-flight requests by incrementing request ID
  currentRequestId++;
  // Clear pending refresh flag
  pendingRefresh = false;
  return {};
};

// --- Event Listeners ---

// Age inputs
ageMinInput.addEventListener("input", onCriteriaChange);
ageMaxInput.addEventListener("input", onCriteriaChange);

// Gender radio buttons
genderRadios.forEach((radio) => {
  radio.addEventListener("change", onCriteriaChange);
});

// ICD match mode radio buttons
icdMatchModeRadios.forEach((radio) => {
  radio.addEventListener("change", onCriteriaChange);
});

// ICU stay radio buttons
icuStayRadios.forEach((radio) => {
  radio.addEventListener("change", onCriteriaChange);
});

// Mortality radio buttons
mortalityRadios.forEach((radio) => {
  radio.addEventListener("change", onCriteriaChange);
});

// ICD code input
icdInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    if (icdInput.value.trim()) {
      addIcdCode(icdInput.value);
      icdInput.value = "";
    }
  }
});

// Set default values
const allGenderRadio = document.querySelector<HTMLInputElement>(
  'input[name="gender"][value=""]'
);
if (allGenderRadio) {
  allGenderRadio.checked = true;
}

const anyIcuRadio = document.querySelector<HTMLInputElement>(
  'input[name="icuStay"][value=""]'
);
if (anyIcuRadio) {
  anyIcuRadio.checked = true;
}

const anyMortalityRadio = document.querySelector<HTMLInputElement>(
  'input[name="mortality"][value=""]'
);
if (anyMortalityRadio) {
  anyMortalityRadio.checked = true;
}

// SQL toggle
sqlToggle.addEventListener("click", () => {
  sqlVisible = !sqlVisible;
  sqlCode.classList.toggle("visible", sqlVisible);
  sqlToggleIcon.textContent = sqlVisible ? "−" : "+";
  sqlToggle.innerHTML = `<span id="sqlToggleIcon">${sqlVisible ? "−" : "+"}</span> ${sqlVisible ? "Hide" : "Show"} SQL`;
});

// Fullscreen toggle
fullscreenBtn.addEventListener("click", toggleFullscreen);

// Listen for system color scheme changes and reapply theme
// Only applies if host hasn't set an explicit theme
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  const ctx = app.getHostContext();
  // If host provides no theme, use system preference
  if (!ctx?.theme) {
    applyDocumentTheme(getSystemTheme());
  }
});

// --- Phase 4: Visibility-based resource management ---

/**
 * Set up IntersectionObserver to pause queries when the app scrolls out of view.
 * This conserves resources when the app is not visible in a scrollable conversation.
 */
function setupVisibilityObserver(): void {
  // Use IntersectionObserver if available (modern browsers)
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const wasVisible = isVisible;
          isVisible = entry.isIntersecting;

          // If becoming visible and we have a pending refresh, execute it
          if (!wasVisible && isVisible && pendingRefresh) {
            pendingRefresh = false;
            refreshCohort();
          }
        });
      },
      {
        // Consider visible if any part of the app is in the viewport
        threshold: 0,
        // Small margin to trigger slightly before fully out of view
        rootMargin: "50px",
      }
    );

    // Observe the document body (the root of our app)
    observer.observe(document.body);
  }

  // Also handle page visibility (tab switching)
  document.addEventListener("visibilitychange", () => {
    const wasVisible = isVisible;
    isVisible = document.visibilityState === "visible";

    // If becoming visible and we have a pending refresh, execute it
    if (!wasVisible && isVisible && pendingRefresh) {
      pendingRefresh = false;
      refreshCohort();
    }
  });
}

// --- Initialize ---
// Apply system theme immediately (before host context is received)
applyDocumentTheme(getSystemTheme());

// Set up visibility observer for resource management
setupVisibilityObserver();

// Connect to host, then apply host context (including theme)
app.connect().then(() => {
  const ctx = app.getHostContext();
  if (ctx) {
    applyHostContext(ctx);
  }
});
