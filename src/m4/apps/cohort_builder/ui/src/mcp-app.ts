/**
 * M4 Cohort Builder MCP App
 *
 * Interactive cohort filtering UI that runs in MCP Apps-enabled hosts.
 * Uses the @modelcontextprotocol/ext-apps SDK for host communication.
 */

import { App } from "@modelcontextprotocol/ext-apps";

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
const ageChart = document.getElementById("ageChart") as HTMLElement;
const genderChart = document.getElementById("genderChart") as HTMLElement;
const sqlCode = document.getElementById("sqlCode") as HTMLElement;
const sqlToggle = document.getElementById("sqlToggle") as HTMLElement;
const sqlToggleIcon = document.getElementById("sqlToggleIcon") as HTMLElement;
const ageMinInput = document.getElementById("ageMin") as HTMLInputElement;
const ageMaxInput = document.getElementById("ageMax") as HTMLInputElement;
const genderRadios = document.querySelectorAll<HTMLInputElement>('input[name="gender"]');

// State
let debounceTimer: number | null = null;
let sqlVisible = false;

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

interface CohortResult {
  patient_count: number;
  admission_count: number;
  demographics: {
    age: Record<string, number>;
    gender: Record<string, number>;
  };
  sql: string;
}

function updateDisplay(result: CohortResult): void {
  // Update counts
  patientCount.textContent = formatNumber(result.patient_count);
  patientCountStat.textContent = formatNumber(result.patient_count);
  admissionCountStat.textContent = formatNumber(result.admission_count);

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

  return criteria;
}

async function refreshCohort(): Promise<void> {
  showLoading();
  hideError();

  try {
    const criteria = getCriteriaFromForm();
    const result = await app.callServerTool({
      name: "query_cohort",
      arguments: criteria,
    });

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

      updateDisplay(data as CohortResult);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Query failed";
    showError(message);
  } finally {
    hideLoading();
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

// Handle host context changes (theme, safe area, etc.)
app.onhostcontextchanged = (ctx) => {
  // Apply host theme via CSS variables
  if (ctx.theme === "dark") {
    document.documentElement.style.setProperty("--color-background", "#1a1a1a");
    document.documentElement.style.setProperty("--color-background-secondary", "#2a2a2a");
    document.documentElement.style.setProperty("--color-text-primary", "#ffffff");
    document.documentElement.style.setProperty("--color-text-secondary", "#a0a0a0");
    document.documentElement.style.setProperty("--color-border", "#404040");
  }

  // Apply host CSS variables if provided
  if (ctx.styles?.variables) {
    for (const [key, value] of Object.entries(ctx.styles.variables)) {
      document.documentElement.style.setProperty(key, value as string);
    }
  }

  // Apply safe area insets
  if (ctx.safeAreaInsets) {
    const { top, right, bottom, left } = ctx.safeAreaInsets;
    document.body.style.padding = `${top}px ${right}px ${bottom}px ${left}px`;
  }
};

// Handle teardown (cleanup)
app.onteardown = async () => {
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer);
  }
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

// Set default gender to "All"
const allGenderRadio = document.querySelector<HTMLInputElement>(
  'input[name="gender"][value=""]'
);
if (allGenderRadio) {
  allGenderRadio.checked = true;
}

// SQL toggle
sqlToggle.addEventListener("click", () => {
  sqlVisible = !sqlVisible;
  sqlCode.classList.toggle("visible", sqlVisible);
  sqlToggleIcon.textContent = sqlVisible ? "−" : "+";
  sqlToggle.innerHTML = `<span id="sqlToggleIcon">${sqlVisible ? "−" : "+"}</span> ${sqlVisible ? "Hide" : "Show"} SQL`;
});

// --- Connect to Host ---
app.connect();
