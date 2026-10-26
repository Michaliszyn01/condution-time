document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector("[data-history-page]");
  if (!page) return;

  const apiBase = page.dataset.apiBase;
  const filters = page.querySelector("[data-history-filters]");
  const categorySelect = page.querySelector("#history-category");
  const periodSelect = page.querySelector("#history-period");
  const statusField = page.querySelector("[data-session-status-filter]");
  const customDates = page.querySelector("[data-custom-dates]");
  const startDate = page.querySelector("#history-start");
  const endDate = page.querySelector("#history-end");
  const toast = page.querySelector("[data-history-toast]");
  const detailBackdrop = document.querySelector("[data-detail-modal]");
  const detailDialog = detailBackdrop.querySelector(".history-modal");
  const editBackdrop = document.querySelector("[data-edit-modal]");
  const editDialog = editBackdrop.querySelector(".history-modal");
  const editForm = editBackdrop.querySelector("[data-edit-form]");
  const editError = editBackdrop.querySelector("[data-edit-error]");
  const deleteBackdrop = document.querySelector("[data-delete-modal]");
  const deleteDialog = deleteBackdrop.querySelector(".history-modal");

  let activeRecord = null;
  let lastFocusedElement = null;

  const options = {
    focus_quality: ["Baixa", "Regular", "Boa", "Muito boa", "Excelente"],
    record_origin: ["Estudo manual", "Sessão monitorada", "Outro"],
    training_type: [
      "Musculação", "Corrida", "Caminhada", "Natação", "Ciclismo",
      "Esporte", "Mobilidade", "Outro"
    ],
    perceived_performance: ["Ruim", "Regular", "Bom", "Muito bom", "Excelente"],
    discomfort_level: ["Nenhum", "Leve", "Moderado", "Forte"],
    perceived_quality_sleep: ["Péssima", "Ruim", "Regular", "Boa", "Excelente"],
    woke_restored: ["Sim", "Parcialmente", "Não"],
    meal_type: ["Café da manhã", "Almoço", "Lanche", "Jantar", "Ceia", "Outra"],
    trinary: ["Sim", "Não", "Não sei"],
    perceived_quality_meal: ["Muito ruim", "Ruim", "Regular", "Boa", "Excelente"],
    unit: ["ml", "L"],
  };

  const schemas = {
    study: [
      ["record_date", "Data", "date", true],
      ["subject", "Matéria", "text", true, 80],
      ["topic", "Assunto", "text", true, 150],
      ["duration_minutes", "Duração em minutos", "number", true, null, 1],
      ["questions_count", "Quantidade de questões", "number", false, null, 0],
      ["correct_answers", "Quantidade de acertos", "number", false, null, 0],
      ["focus_quality", "Qualidade do foco", "select", true, options.focus_quality],
      ["learned_text", "O que aprendeu?", "textarea", false, 2000],
      ["difficulty_text", "Dificuldade encontrada", "textarea", false, 2000],
      ["record_origin", "Origem do registro", "select", true, options.record_origin],
    ],
    training: [
      ["record_date", "Data", "date", true],
      ["training_type", "Tipo de treino", "select", true, options.training_type],
      ["activity_name", "Atividade", "text", true, 150],
      ["duration_minutes", "Duração em minutos", "number", true, null, 1],
      ["intensity", "Intensidade", "number", true, null, 1, 10],
      ["perceived_performance", "Desempenho percebido", "select", true, options.perceived_performance],
      ["exercises_text", "Exercícios", "textarea", false, 2000],
      ["discomfort_level", "Dor ou desconforto", "select", true, options.discomfort_level],
      ["discomfort_location", "Local do desconforto", "text", false, 150],
      ["notes", "Observações", "textarea", false, 2000],
    ],
    sleep: [
      ["record_date", "Data de referência", "date", true],
      ["sleep_start", "Horário em que dormiu", "time", true],
      ["sleep_end", "Horário em que acordou", "time", true],
      ["perceived_quality", "Qualidade percebida", "select", true, options.perceived_quality_sleep],
      ["awakenings_count", "Quantidade de interrupções", "number", true, null, 0],
      ["woke_restored", "Acordou descansado?", "select", true, options.woke_restored],
      ["notes", "Observações", "textarea", false, 2000],
      ["record_origin", "Origem do registro", "hidden", true],
    ],
    meal: [
      ["record_date", "Data", "date", true],
      ["meal_type", "Tipo de refeição", "select", true, options.meal_type],
      ["meal_time", "Horário", "time", true],
      ["foods_text", "Alimentos", "textarea", true, 2000],
      ["approximate_amount", "Quantidade aproximada", "text", false, 500],
      ["has_protein", "Possui proteína?", "select", true, options.trinary],
      ["has_fruits_or_vegetables", "Possui frutas ou verduras?", "select", true, options.trinary],
      ["perceived_quality", "Qualidade percebida", "select", true, options.perceived_quality_meal],
      ["notes", "Observações", "textarea", false, 2000],
    ],
    hydration: [
      ["record_date", "Data", "date", true],
      ["amount", "Quantidade", "number", true, null, 0.001, 20000, "any"],
      ["unit", "Unidade", "select", true, options.unit],
      ["consumed_at", "Horário", "time", true],
      ["notes", "Observações", "textarea", false, 2000],
    ],
  };

  function updateConditionalFilters() {
    statusField.hidden = !["all", "session"].includes(categorySelect.value);
    const isCustom = periodSelect.value === "custom";
    customDates.hidden = !isCustom;
    startDate.required = isCustom;
    endDate.required = isCustom;
  }

  function showToast(text, tone = "success") {
    toast.textContent = text;
    toast.dataset.tone = tone;
    toast.hidden = false;
  }

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body ? {"Content-Type": "application/json"} : {}),
        ...(options.headers || {}),
      },
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(result.message || "Não foi possível concluir a ação.");
      error.errors = result.errors || {};
      throw error;
    }
    return result;
  }

  function openModal(backdrop, dialog) {
    lastFocusedElement = document.activeElement;
    backdrop.hidden = false;
    document.body.classList.add("history-modal-open");
    dialog.focus();
  }

  function closeModal(backdrop) {
    backdrop.hidden = true;
    if (![detailBackdrop, editBackdrop, deleteBackdrop].some((item) => !item.hidden)) {
      document.body.classList.remove("history-modal-open");
    }
    if (lastFocusedElement instanceof HTMLElement) lastFocusedElement.focus();
  }

  function renderDetails(record) {
    activeRecord = {
      type: record.record_type,
      id: record.id,
      title: record.title,
      editable: record.editable,
      deletable: record.deletable,
    };
    detailBackdrop.querySelector("[data-detail-category]").textContent =
      record.record_type === "session" ? "Sessão" : "Registro";
    detailBackdrop.querySelector("[data-detail-title]").textContent = record.title;
    const grid = detailBackdrop.querySelector("[data-detail-fields]");
    grid.replaceChildren();
    record.details.forEach((detail) => {
      const wrapper = document.createElement("dl");
      wrapper.className = "history-detail-field";
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = detail.label;
      description.textContent = detail.value;
      wrapper.append(term, description);
      grid.append(wrapper);
    });
    detailBackdrop.querySelector("[data-edit-record]").hidden = !record.editable;
    detailBackdrop.querySelector("[data-delete-record]").hidden = !record.deletable;
    detailBackdrop.querySelector("[data-session-readonly]").hidden =
      record.record_type !== "session";
  }

  async function openRecordDetail(recordType, recordId, button = null) {
    if (button) button.disabled = true;
    try {
      const result = await request(
        `${apiBase}/${recordType}/${recordId}`
      );
      renderDetails(result.record);
      openModal(detailBackdrop, detailDialog);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      if (button) button.disabled = false;
    }
  }

  function openDetails(button) {
    const item = button.closest("[data-history-item]");
    return openRecordDetail(
      item.dataset.recordType,
      item.dataset.recordId,
      button
    );
  }

  function fieldElement(config, value) {
    const [name, label, type, required, extra, minimum, maximum, step] = config;
    if (type === "hidden") {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value ?? "";
      return input;
    }
    const wrapper = document.createElement("div");
    wrapper.className = `registration-field${type === "textarea" ? " registration-field--wide" : ""}`;
    const labelElement = document.createElement("label");
    const id = `history-edit-${name}`;
    labelElement.htmlFor = id;
    labelElement.textContent = label;
    let control;
    if (type === "select") {
      control = document.createElement("select");
      extra.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        option.selected = optionValue === value;
        control.append(option);
      });
    } else if (type === "textarea") {
      control = document.createElement("textarea");
      control.rows = 3;
      control.maxLength = extra || 2000;
      control.value = value ?? "";
    } else {
      control = document.createElement("input");
      control.type = type;
      control.value = value ?? "";
      if (extra) control.maxLength = extra;
      if (minimum != null) control.min = minimum;
      if (maximum != null) control.max = maximum;
      if (step) control.step = step;
    }
    control.id = id;
    control.name = name;
    control.required = Boolean(required);
    wrapper.append(labelElement, control);
    return wrapper;
  }

  function buildEditForm(record) {
    editForm.replaceChildren();
    editForm.id = "history-dynamic-form";
    const schema = schemas[record.record_type] || [];
    schema.forEach((config) => {
      editForm.append(fieldElement(config, record.data[config[0]]));
    });
    editError.hidden = true;
  }

  async function openEdit() {
    if (!activeRecord?.editable) return;
    try {
      const result = await request(
        `${apiBase}/${activeRecord.type}/${activeRecord.id}`
      );
      buildEditForm(result.record);
      closeModal(detailBackdrop);
      openModal(editBackdrop, editDialog);
      editForm.querySelector("input:not([type=hidden]), select, textarea")?.focus();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function saveEdit(event) {
    event.preventDefault();
    if (!editForm.reportValidity() || !activeRecord) return;
    const saveButton = editBackdrop.querySelector("[data-edit-save]");
    saveButton.disabled = true;
    editError.hidden = true;
    const payload = Object.fromEntries(new FormData(editForm).entries());
    try {
      const result = await request(
        `${apiBase}/${activeRecord.type}/${activeRecord.id}`,
        {method: "PATCH", body: JSON.stringify(payload)}
      );
      showToast(result.message);
      closeModal(editBackdrop);
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      editError.textContent =
        Object.values(error.errors || {})[0] || error.message;
      editError.hidden = false;
      editForm.querySelector(`[name="${Object.keys(error.errors || {})[0]}"]`)?.focus();
    } finally {
      saveButton.disabled = false;
    }
  }

  function openDelete() {
    if (!activeRecord?.deletable) return;
    deleteBackdrop.querySelector("[data-delete-title]").textContent = activeRecord.title;
    closeModal(detailBackdrop);
    openModal(deleteBackdrop, deleteDialog);
  }

  async function confirmDelete() {
    if (!activeRecord?.deletable) return;
    const button = deleteBackdrop.querySelector("[data-delete-confirm]");
    button.disabled = true;
    try {
      const result = await request(
        `${apiBase}/${activeRecord.type}/${activeRecord.id}`,
        {method: "DELETE"}
      );
      showToast(result.message);
      closeModal(deleteBackdrop);
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  function trapFocus(event, backdrop, dialog, canEscape = true) {
    if (event.key === "Escape" && canEscape) {
      event.preventDefault();
      closeModal(backdrop);
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [...dialog.querySelectorAll(
      'button:not([disabled]):not([hidden]), [href], input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )].filter((element) => element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  categorySelect.addEventListener("change", updateConditionalFilters);
  periodSelect.addEventListener("change", updateConditionalFilters);
  filters.addEventListener("submit", (event) => {
    if (periodSelect.value === "custom" && startDate.value > endDate.value) {
      event.preventDefault();
      showToast("A data inicial não pode ser posterior à final.", "error");
      startDate.focus();
    }
  });
  page.querySelectorAll("[data-record-detail]").forEach((button) => {
    button.addEventListener("click", () => openDetails(button));
  });
  detailBackdrop.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(detailBackdrop));
  });
  detailBackdrop.querySelector("[data-edit-record]").addEventListener("click", openEdit);
  detailBackdrop.querySelector("[data-delete-record]").addEventListener("click", openDelete);
  editBackdrop.querySelectorAll("[data-edit-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(editBackdrop));
  });
  editForm.addEventListener("submit", saveEdit);
  deleteBackdrop.querySelectorAll("[data-delete-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(deleteBackdrop));
  });
  deleteBackdrop.querySelector("[data-delete-confirm]").addEventListener("click", confirmDelete);
  [
    [detailBackdrop, detailDialog, true],
    [editBackdrop, editDialog, true],
    [deleteBackdrop, deleteDialog, true],
  ].forEach(([backdrop, dialog, canEscape]) => {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeModal(backdrop);
    });
    dialog.addEventListener("keydown", (event) =>
      trapFocus(event, backdrop, dialog, canEscape)
    );
  });
  updateConditionalFilters();
  const requestedRecord = new URLSearchParams(window.location.search).get("registro");
  if (requestedRecord && /^[a-z]+:\d+$/.test(requestedRecord)) {
    const [recordType, recordId] = requestedRecord.split(":");
    openRecordDetail(recordType, recordId);
  }
});
