const state = {
  view: "items",
  fileStatus: "",
  manufacturer: "Todas montadoras",
  plant: "",
  search: "",
  dateFrom: "",
  dateTo: "",
  page: 1,
  pages: 1,
  total: 0,
  items: [],
  statusTimer: null,
  searchTimer: null,
  deliveryMonth: new Date().toISOString().slice(0, 7),
  deliveryManufacturer: "Todas montadoras",
  deliveryPlant: "",
  pendingProgramInput: null,
  programAuthorizations: {},
  adminToken: "",
  adminManufacturers: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function formatNumber(value, maximumFractionDigits = 2) {
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits,
  }).format(Number(value || 0));
}

function formatLatest(raw) {
  if (!raw) return "—";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Erro HTTP ${response.status}`);
  }
  return payload;
}

function buildItemsUrl() {
  const params = new URLSearchParams({
    manufacturer: state.manufacturer,
    page: String(state.page),
  });
  if (state.plant) params.set("plant", state.plant);
  if (state.search) params.set("search", state.search);
  if (state.dateFrom) params.set("date_from", state.dateFrom);
  if (state.dateTo) params.set("date_to", state.dateTo);
  return `/api/items?${params}`;
}

async function loadItems() {
  try {
    state.view = "items";
    $("#search-input").placeholder = "Buscar item, NF, pedido ou descrição";
    $("#summary-grid").classList.remove("hidden");
    $$(".date-field").forEach((field) => field.classList.remove("hidden"));
    $("#results-head-row").innerHTML = `
      <th>Data de emissão</th><th>Nota fiscal</th><th>Item</th>
      <th>Descrição</th><th>Código cliente</th><th>Planta</th>
      <th class="numeric">Quantidade</th>
      <th>Pedido</th><th aria-label="Detalhes"></th>
    `;
    const data = await fetchJson(buildItemsUrl());
    state.items = data.items;
    state.pages = data.pagination.pages;
    state.total = data.pagination.total;
    renderPlantTabs(data.plants);
    renderSummary(data.summary);
    renderRows();
    renderPagination();
  } catch (error) {
    showEmpty(`Não foi possível carregar os dados: ${error.message}`);
  }
}

async function loadAuxiliaryFiles() {
  try {
    state.view = "files";
    $("#search-input").placeholder = "Buscar pelo nome do arquivo XML";
    $("#summary-grid").classList.add("hidden");
    $("#plant-tabs").classList.add("hidden");
    $$(".date-field").forEach((field) => field.classList.add("hidden"));
    $("#results-head-row").innerHTML = `
      <th>Arquivo XML</th><th>Categoria</th>
      <th>Indexado em</th><th class="numeric">Tamanho</th>
    `;
    const params = new URLSearchParams({
      status: state.fileStatus,
      page: String(state.page),
    });
    if (state.search) params.set("search", state.search);
    const data = await fetchJson(`/api/files?${params}`);
    state.items = data.files;
    state.pages = data.pagination.pages;
    state.total = data.pagination.total;
    renderFileRows();
    renderPagination();
  } catch (error) {
    showEmpty(`Não foi possível carregar os arquivos: ${error.message}`);
  }
}

function loadCurrentView() {
  if (state.view === "files") return loadAuxiliaryFiles();
  if (state.view === "deliveries") return loadDeliveries();
  return loadItems();
}

function renderPlantTabs(plants) {
  const tabs = $("#plant-tabs");
  const options = ["", ...plants];
  tabs.innerHTML = options.map((plant) => `
    <button class="plant-tab${plant === state.plant ? " active" : ""}"
            data-plant="${escapeHtml(plant)}">
      ${escapeHtml(plant || "Todas as plantas")}
    </button>
  `).join("");
  tabs.classList.toggle("hidden", plants.length === 0);
  bindPlantTabs();
}

function bindPlantTabs() {
  $$(".plant-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.plant = button.dataset.plant;
      state.page = 1;
      loadItems();
    });
  });
}

function renderSummary(summary) {
  $("#summary-invoices").textContent = formatNumber(summary.invoice_count, 0);
  $("#summary-items").textContent = formatNumber(summary.item_count, 0);
  $("#summary-quantity").textContent = formatNumber(summary.total_quantity, 2);
  $("#summary-latest").textContent = formatLatest(summary.latest_issue);
}

function renderRows() {
  const body = $("#results-body");
  body.innerHTML = "";
  if (!state.items.length) {
    showEmpty(
      state.manufacturer === "Volkswagen"
        ? "Ajuste os filtros ou aguarde a indexação dos XMLs."
        : "As regras desta montadora serão adicionadas na próxima etapa."
    );
    return;
  }

  hideEmpty();
  body.innerHTML = state.items.map((item, index) => `
    <tr>
      <td>${escapeHtml(item.issue_display || item.issued_at || "—")}</td>
      <td><strong>${escapeHtml(item.invoice_number || "—")}</strong></td>
      <td class="product-code">${escapeHtml(item.product_code || "—")}</td>
      <td class="description-cell" title="${escapeHtml(item.description)}">
        ${escapeHtml(item.description || "—")}
      </td>
      <td class="client-code-cell">${escapeHtml(item.client_code || "—")}</td>
      <td><span class="plant-badge">${
        state.manufacturer === "Todas montadoras"
          ? `${escapeHtml(item.manufacturer)} · ${escapeHtml(item.plant)}`
          : escapeHtml(item.plant)
      }</span></td>
      <td class="numeric"><strong>${formatNumber(item.quantity, 2)}</strong></td>
      <td>${escapeHtml(item.order_number || "—")}</td>
      <td>
        <button class="detail-button" data-index="${index}" title="Ver detalhes">
          <span class="detail-glyph" aria-hidden="true">i</span>
        </button>
      </td>
    </tr>
  `).join("");

  $$(".detail-button").forEach((button) => {
    button.addEventListener("click", () => {
      openDetails(state.items[Number(button.dataset.index)]);
    });
  });
  refreshIcons();
}

function renderFileRows() {
  const body = $("#results-body");
  if (!state.items.length) {
    showEmpty("Nenhum arquivo encontrado nesta categoria.");
    return;
  }
  hideEmpty();
  const category = state.fileStatus === "cancelled"
    ? "Cancelado"
    : "Carta de correção";
  body.innerHTML = state.items.map((file) => `
    <tr>
      <td class="product-code">${escapeHtml(file.name)}</td>
      <td><span class="plant-badge">${category}</span></td>
      <td>${escapeHtml(file.processed_at || "—")}</td>
      <td class="numeric">${formatNumber(file.size / 1024, 1)} KB</td>
    </tr>
  `).join("");
}

function showEmpty(message) {
  $("#results-body").innerHTML = "";
  $("#empty-message").textContent = message;
  $("#empty-state").classList.remove("hidden");
}

function hideEmpty() {
  $("#empty-state").classList.add("hidden");
}

function renderPagination() {
  const start = state.total ? ((state.page - 1) * 100) + 1 : 0;
  const end = Math.min(state.page * 100, state.total);
  $("#pagination-label").textContent =
    `${formatNumber(start, 0)}–${formatNumber(end, 0)} de ${formatNumber(state.total, 0)} resultados`;
  $("#page-label").textContent = `Página ${state.page} de ${state.pages}`;
  $("#previous-page").disabled = state.page <= 1;
  $("#next-page").disabled = state.page >= state.pages;
}

function openDetails(item) {
  $("#detail-title").textContent = item.product_code || "Item sem código";
  $("#detail-invoice").textContent = item.invoice_number || "—";
  $("#detail-plant").textContent = item.plant || "—";
  $("#detail-quantity").textContent =
    `${formatNumber(item.quantity, 2)} ${item.commercial_unit || ""}`.trim();
  $("#detail-source").textContent = item.source_name || "—";

  const fields = [
    ["Descrição", item.description],
    ["Código do cliente", item.client_code],
    ["Número da fatura", item.billing_number],
    ["Data de emissão", item.issued_at],
    ["Item na NF", item.n_item],
    ["CFOP", item.cfop],
    ["NCM", item.ncm],
    ["Código de benefício", item.benefit_code],
    ["EAN", item.ean],
    ["Unidade comercial", item.commercial_unit],
    ["Quantidade comercial", item.quantity_raw],
    ["Valor unitário", item.unit_value],
    ["Valor do produto", item.product_value],
    ["EAN tributável", item.tax_ean],
    ["Unidade tributável", item.tax_unit],
    ["Quantidade tributável", item.tax_quantity],
    ["Valor unitário tributável", item.tax_unit_value],
    ["Indicador total", item.total_indicator],
    ["Pedido", item.order_number],
    ["Item do pedido", item.order_item],
    ["Chave de acesso", item.access_key],
  ];

  $("#detail-grid").innerHTML = fields.map(([label, value]) => `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value || "—")}</dd>
    </div>
  `).join("");

  $("#detail-dialog").showModal();
  refreshIcons();
}

async function pollStatus() {
  try {
    const status = await fetchJson("/api/status");
    $("#menu-cancelled-count").textContent =
      formatNumber(status.index?.cancelled_files, 0);
    $("#menu-correction-count").textContent =
      formatNumber(status.index?.correction_files, 0);
    const sync = $("#sync-state");
    sync.classList.toggle("ready", status.phase === "done" || status.phase === "idle");
    sync.classList.toggle("error", status.phase === "error");
    $("#sync-label").textContent = status.running
      ? "Atualizando XMLs"
      : status.phase === "error" ? "Falha na atualização" : "Índice atualizado";
    $("#sync-detail").textContent = status.message;
    $("#refresh-button").disabled = status.running;

    const missingAlert = $("#missing-invoices-alert");
    const missingInvoices = status.missing_invoices || [];
    const hasMissing = Number(status.missing_total || 0) > 0;
    missingAlert.classList.toggle("hidden", !hasMissing);
    missingAlert.classList.toggle("recovering", Boolean(status.recovery_running));
    if (hasMissing) {
      $("#missing-alert-title").textContent = status.recovery_running
        ? "Recuperando XMLs no Datasul"
        : status.datasul_available
          ? "Notas fiscais sem XML na pasta"
          : "Datasul Interactive não está aberto";
      $("#missing-alert-message").textContent = status.recovery_message;
      $("#missing-invoice-list").innerHTML = missingInvoices
        .map((number) => `<strong>${escapeHtml(number)}</strong>`)
        .join("");
      if (Number(status.missing_total) > missingInvoices.length) {
        $("#missing-invoice-list").insertAdjacentHTML(
          "beforeend",
          `<span>+${formatNumber(status.missing_total - missingInvoices.length, 0)} notas</span>`
        );
      }
      $("#missing-retry").disabled = Boolean(status.recovery_running);
      refreshIcons();
    }

    const progressPanel = $("#progress-panel");
    if (status.running && status.files_pending) {
      progressPanel.classList.remove("hidden");
      const percent = Math.min(
        100,
        (status.files_processed / status.files_pending) * 100
      );
      $("#progress-label").textContent = status.message;
      $("#progress-count").textContent =
        `${formatNumber(status.files_processed, 0)} de ${formatNumber(status.files_pending, 0)}`;
      $("#progress-bar").style.width = `${percent}%`;
    } else {
      progressPanel.classList.add("hidden");
    }

    if (!status.running && pollStatus.wasRunning) {
      state.page = 1;
      await loadCurrentView();
    }
    pollStatus.wasRunning = status.running;
  } catch (error) {
    $("#sync-state").classList.add("error");
    $("#sync-label").textContent = "Servidor indisponível";
    $("#sync-detail").textContent = error.message;
  }
}

async function requestRefresh() {
  try {
    await fetchJson("/api/refresh", { method: "POST" });
    await pollStatus();
  } catch (error) {
    if (!error.message.includes("409")) {
      $("#sync-detail").textContent = error.message;
    }
  }
}

async function requestMissingRecovery() {
  try {
    await fetchJson("/api/recover-missing", { method: "POST" });
    await pollStatus();
  } catch (error) {
    $("#missing-alert-message").textContent = error.message;
  }
}

function setManufacturer(manufacturer) {
  state.view = "items";
  state.fileStatus = "";
  state.manufacturer = manufacturer;
  state.plant = "";
  state.page = 1;
  $("#standard-view").classList.remove("hidden");
  $("#delivery-view").classList.add("hidden");
  $("#page-title").textContent = manufacturer;
  $$(".manufacturer").forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.manufacturer === manufacturer
    );
  });
  $$(".auxiliary-option").forEach((button) => {
    button.classList.remove("active");
  });
  $("#delivery-nav").classList.remove("active");
  loadItems();
}

function openAuxiliaryCategory(status) {
  state.view = "files";
  state.fileStatus = status;
  state.page = 1;
  state.plant = "";
  $("#standard-view").classList.remove("hidden");
  $("#delivery-view").classList.add("hidden");
  const title = status === "cancelled" ? "XMLs cancelados" : "Cartas de correção";
  $("#page-title").textContent = title;
  $$(".manufacturer").forEach((button) => button.classList.remove("active"));
  $$(".auxiliary-option").forEach((button) => {
    button.classList.toggle("active", button.dataset.fileStatus === status);
  });
  loadAuxiliaryFiles();
}

function daysInMonth(month) {
  const [year, monthNumber] = month.split("-").map(Number);
  return new Date(year, monthNumber, 0).getDate();
}

function deliveryDayLabel(month, day) {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(year, monthNumber - 1, day);
  const weekday = new Intl.DateTimeFormat("pt-BR", { weekday: "short" })
    .format(date).replace(".", "");
  return `${weekday}<strong>${String(day).padStart(2, "0")}</strong>`;
}

async function loadDeliveries() {
  state.view = "deliveries";
  const params = new URLSearchParams({
    month: state.deliveryMonth,
    manufacturer: state.deliveryManufacturer,
  });
  if (state.deliveryPlant) params.set("plant", state.deliveryPlant);
  const data = await fetchJson(`/api/deliveries?${params}`);
  renderDeliveryFilters(data);
  renderDeliveryTable(data.rows);
}

function renderDeliveryFilters(data) {
  const manufacturerSelect = $("#delivery-manufacturer");
  const manufacturerOptions = ["Todas montadoras", ...data.manufacturers];
  manufacturerSelect.innerHTML = manufacturerOptions.map((name) => `
    <option value="${escapeHtml(name)}"${name === state.deliveryManufacturer ? " selected" : ""}>
      ${escapeHtml(name)}
    </option>
  `).join("");

  const plantSelect = $("#delivery-plant");
  plantSelect.innerHTML = `
    <option value="">Todas as plantas</option>
    ${data.plants.map((plant) => `
      <option value="${escapeHtml(plant)}"${plant === state.deliveryPlant ? " selected" : ""}>
        ${escapeHtml(plant)}
      </option>
    `).join("")}
  `;
}

function renderDeliveryTable(rows) {
  const dayCount = daysInMonth(state.deliveryMonth);
  const dayHeaders = Array.from({ length: dayCount }, (_, index) => `
    <th class="delivery-day">${deliveryDayLabel(state.deliveryMonth, index + 1)}</th>
  `).join("");
  $("#delivery-head").innerHTML = `
    <tr>
      <th class="sticky-col plant-col">Planta</th>
      <th class="sticky-col item-col">Item</th>
      <th class="sticky-col client-code-col">Código cliente</th>
      <th class="sticky-col description-col">Descrição</th>
      ${dayHeaders}
      <th class="total-col">Faturado</th>
      <th class="program-col">Programa</th>
      <th class="balance-col">Saldo a entregar</th>
    </tr>
  `;

  $("#delivery-empty").classList.toggle("hidden", rows.length > 0);
  $("#delivery-body").innerHTML = rows.map((row) => {
    const authorization = state.programAuthorizations[row.manufacturer] || "";
    const days = Array.from({ length: dayCount }, (_, index) => {
      const value = row.days[String(index + 1)];
      if (!value) return `<td class="delivery-cell empty"></td>`;
      const invoices = value.invoices.filter(Boolean).join(", ");
      return `
        <td class="delivery-cell has-value"
            title="NF: ${escapeHtml(invoices || "não informada")}">
          ${formatNumber(value.quantity, 2)}
        </td>
      `;
    }).join("");
    return `
      <tr>
        <td class="sticky-col plant-col">
          <strong>${escapeHtml(row.plant)}</strong>
          <span>${escapeHtml(row.manufacturer)}</span>
        </td>
        <td class="sticky-col item-col product-code">${escapeHtml(row.product_code)}</td>
        <td class="sticky-col client-code-col product-code">
          ${escapeHtml(row.client_code || "—")}
        </td>
        <td class="sticky-col description-col" title="${escapeHtml(row.description)}">
          ${escapeHtml(row.description)}
        </td>
        ${days}
        <td class="delivery-total">${formatNumber(row.total, 2)}</td>
        <td class="delivery-program">
          <input type="number" min="0" step="1" value="${row.program}"
                 ${authorization ? "" : "readonly"}
                 aria-label="Programa de ${escapeHtml(row.product_code)}"
                 title="${authorization
                   ? `Montadora ${escapeHtml(row.manufacturer)} autorizada`
                   : `Clique para autorizar ${escapeHtml(row.manufacturer)}`}"
                 data-manufacturer="${escapeHtml(row.manufacturer)}"
                 data-plant="${escapeHtml(row.plant)}"
                 data-product="${escapeHtml(row.product_code)}"
                 data-auth-token="${escapeHtml(authorization)}">
        </td>
        <td class="delivery-balance ${row.balance < 0 ? "over" : ""}">
          ${formatNumber(row.balance, 2)}
        </td>
      </tr>
    `;
  }).join("");

  $$(".delivery-program input").forEach((input) => {
    input.addEventListener("pointerdown", (event) => {
      if (!input.readOnly) return;
      event.preventDefault();
      requestProgramAuthorization(input);
    });
    input.addEventListener("click", () => {
      if (input.readOnly && !$("#pin-dialog").open) {
        requestProgramAuthorization(input);
      }
    });
    input.addEventListener("change", () => saveProgram(input));
  });
}

function requestProgramAuthorization(input) {
  if (!input.readOnly) return;
  state.pendingProgramInput = input;
  const manufacturer = input.dataset.manufacturer;
  $("#pin-input").value = "";
  $("#pin-error").textContent = "";
  $("#pin-error").classList.add("hidden");
  $("#pin-copy").textContent =
    `Informe a senha de 6 dígitos para liberar todos os Programas de ${manufacturer}.`;
  $("#pin-dialog").showModal();
  setTimeout(() => $("#pin-input").focus(), 50);
}

async function authorizeProgramChange() {
  const pin = $("#pin-input").value.trim();
  $("#pin-confirm").disabled = true;
  try {
    const authorization = await fetchJson("/api/program-auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pin,
        manufacturer: state.pendingProgramInput?.dataset.manufacturer,
      }),
    });
    const input = state.pendingProgramInput;
    if (!input || !input.isConnected) {
      $("#pin-dialog").close();
      return;
    }
    state.programAuthorizations[authorization.manufacturer] =
      authorization.token;
    if (authorization.role === "admin") {
      state.adminToken = authorization.token;
      openAdminPanel();
    }
    $$(`.delivery-program input`).forEach((candidate) => {
      if (candidate.dataset.manufacturer === authorization.manufacturer) {
        candidate.dataset.authToken = authorization.token;
        candidate.readOnly = false;
        candidate.title =
          `Montadora ${authorization.manufacturer} autorizada`;
      }
    });
    $("#pin-dialog").close();
    if (authorization.registered) {
      input.title =
        `Senha cadastrada para ${authorization.manufacturer}`;
    }
    setTimeout(() => {
      input.focus();
      input.select();
    }, 30);
  } catch (error) {
    $("#pin-error").textContent = error.message;
    $("#pin-error").classList.remove("hidden");
    $("#pin-input").select();
  } finally {
    $("#pin-confirm").disabled = false;
  }
}

async function adminRequest(action, extra = {}) {
  return fetchJson("/api/admin-passwords", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      auth_token: state.adminToken,
      ...extra,
    }),
  });
}

async function openAdminPanel() {
  $("#admin-panel").classList.remove("hidden");
  $("#admin-feedback").classList.add("hidden");
  try {
    const data = await adminRequest("list");
    state.adminManufacturers = data.manufacturers;
    $("#admin-manufacturer").innerHTML = data.manufacturers.map((item) => `
      <option value="${escapeHtml(item.name)}">
        ${escapeHtml(item.name)}
      </option>
    `).join("");
    const preferred = state.pendingProgramInput?.dataset.manufacturer;
    if (preferred && data.manufacturers.some((item) => item.name === preferred)) {
      $("#admin-manufacturer").value = preferred;
    }
    renderAdminPasswordStatus();
  } catch (error) {
    showAdminFeedback(error.message, true);
  }
  refreshIcons();
}

function renderAdminPasswordStatus() {
  const manufacturer = $("#admin-manufacturer").value;
  const item = state.adminManufacturers.find(
    (candidate) => candidate.name === manufacturer
  );
  const configured = Boolean(item?.configured);
  $("#admin-password-status").className =
    `admin-password-status ${configured ? "configured" : "not-configured"}`;
  $("#admin-password-status").innerHTML = configured
    ? `<i data-lucide="lock-keyhole"></i><span>Senha cadastrada</span>`
    : `<i data-lucide="lock-keyhole-open"></i><span>Sem senha cadastrada</span>`;
  refreshIcons();
}

function showAdminFeedback(message, isError = false) {
  const feedback = $("#admin-feedback");
  feedback.textContent = message;
  feedback.classList.remove("hidden", "error");
  feedback.classList.toggle("error", isError);
}

async function setManufacturerPassword() {
  const manufacturer = $("#admin-manufacturer").value;
  const newPin = $("#admin-new-pin").value.trim();
  try {
    const result = await adminRequest("set", {
      manufacturer,
      new_pin: newPin,
    });
    $("#admin-new-pin").value = "";
    showAdminFeedback(result.message);
    await openAdminPanel();
  } catch (error) {
    showAdminFeedback(error.message, true);
  }
}

async function clearManufacturerPassword() {
  const manufacturer = $("#admin-manufacturer").value;
  if (!window.confirm(`Limpar a senha de ${manufacturer}?`)) return;
  try {
    const result = await adminRequest("clear", { manufacturer });
    delete state.programAuthorizations[manufacturer];
    showAdminFeedback(result.message);
    await openAdminPanel();
    await loadDeliveries();
  } catch (error) {
    showAdminFeedback(error.message, true);
  }
}

async function clearAllManufacturerPasswords() {
  if (!window.confirm("Limpar as senhas de todas as montadoras?")) return;
  try {
    const result = await adminRequest("clear_all");
    state.programAuthorizations = {};
    showAdminFeedback(result.message);
    await openAdminPanel();
    await loadDeliveries();
  } catch (error) {
    showAdminFeedback(error.message, true);
  }
}

async function saveProgram(input) {
  if (input.readOnly || !input.dataset.authToken) return;
  input.disabled = true;
  try {
    await fetchJson("/api/delivery-program", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        month: state.deliveryMonth,
        manufacturer: input.dataset.manufacturer,
        plant: input.dataset.plant,
        product_code: input.dataset.product,
        quantity: input.value,
        auth_token: input.dataset.authToken,
      }),
    });
    await loadDeliveries();
  } catch (error) {
    input.disabled = false;
    input.title = error.message;
  }
}

function openDeliveries() {
  state.view = "deliveries";
  $("#standard-view").classList.add("hidden");
  $("#delivery-view").classList.remove("hidden");
  $("#page-title").textContent = "Entregas vs Pedido";
  $$(".manufacturer").forEach((button) => button.classList.remove("active"));
  $$(".auxiliary-option").forEach((button) => button.classList.remove("active"));
  $("#delivery-nav").classList.add("active");
  $("#delivery-month").value = state.deliveryMonth;
  loadDeliveries();
}

function bindEvents() {
  $$(".manufacturer").forEach((button) => {
    button.addEventListener("click", () => {
      setManufacturer(button.dataset.manufacturer);
    });
  });

  $("#auxiliary-toggle").addEventListener("click", () => {
    const expanded = $("#auxiliary-toggle").getAttribute("aria-expanded") === "true";
    $("#auxiliary-toggle").setAttribute("aria-expanded", String(!expanded));
    $("#auxiliary-menu").classList.toggle("hidden", expanded);
  });

  $$(".auxiliary-option").forEach((button) => {
    button.addEventListener("click", () => {
      openAuxiliaryCategory(button.dataset.fileStatus);
    });
  });

  $("#delivery-nav").addEventListener("click", openDeliveries);
  $("#pin-form").addEventListener("submit", (event) => {
    event.preventDefault();
    authorizeProgramChange();
  });
  $("#pin-cancel").addEventListener("click", () => {
    state.pendingProgramInput = null;
    $("#pin-dialog").close();
  });
  $("#admin-close").addEventListener("click", () => {
    $("#admin-panel").classList.add("hidden");
  });
  $("#admin-manufacturer").addEventListener(
    "change",
    renderAdminPasswordStatus
  );
  $("#admin-set-password").addEventListener(
    "click",
    setManufacturerPassword
  );
  $("#admin-clear-password").addEventListener(
    "click",
    clearManufacturerPassword
  );
  $("#admin-clear-all").addEventListener(
    "click",
    clearAllManufacturerPasswords
  );
  $("#delivery-month").addEventListener("change", (event) => {
    state.deliveryMonth = event.target.value;
    loadDeliveries();
  });
  $("#delivery-manufacturer").addEventListener("change", (event) => {
    state.deliveryManufacturer = event.target.value;
    state.deliveryPlant = "";
    loadDeliveries();
  });
  $("#delivery-plant").addEventListener("change", (event) => {
    state.deliveryPlant = event.target.value;
    loadDeliveries();
  });

  $("#search-input").addEventListener("input", (event) => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => {
      state.search = event.target.value.trim();
      state.page = 1;
      loadCurrentView();
    }, 300);
  });

  $("#date-from").addEventListener("change", (event) => {
    state.dateFrom = event.target.value;
    state.page = 1;
    loadCurrentView();
  });

  $("#date-to").addEventListener("change", (event) => {
    state.dateTo = event.target.value;
    state.page = 1;
    loadCurrentView();
  });

  $("#clear-filters").addEventListener("click", () => {
    state.search = "";
    state.dateFrom = "";
    state.dateTo = "";
    state.page = 1;
    $("#search-input").value = "";
    $("#date-from").value = "";
    $("#date-to").value = "";
    loadCurrentView();
  });

  $("#previous-page").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadCurrentView();
    }
  });

  $("#next-page").addEventListener("click", () => {
    if (state.page < state.pages) {
      state.page += 1;
      loadCurrentView();
    }
  });

  $("#refresh-button").addEventListener("click", requestRefresh);
  $("#missing-retry").addEventListener("click", requestMissingRecovery);
  $("#dialog-close").addEventListener("click", () => {
    $("#detail-dialog").close();
  });
  $("#detail-dialog").addEventListener("click", (event) => {
    if (event.target === $("#detail-dialog")) {
      $("#detail-dialog").close();
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  refreshIcons();
  await Promise.all([loadItems(), pollStatus()]);
  const statusLoop = async () => {
    await pollStatus();
    state.statusTimer = setTimeout(
      statusLoop,
      pollStatus.wasRunning ? 2000 : 10000
    );
  };
  state.statusTimer = setTimeout(statusLoop, 10000);
});
