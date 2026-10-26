document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector("[data-session-page]");
  if (!page) return;

  const ACTIVE_SESSION_KEY = "active_session_id";
  const apiBase = page.dataset.apiBase;
  const stateContent = {
    config: {
      title: "Nova sessão",
      subtitle: "Escolha seu foco e comece a transformar tempo em progresso.",
    },
    running: {
      title: "Sessão em andamento",
      subtitle: "Mantenha o foco. Seu progresso está sendo registrado.",
    },
    summary: {
      title: "Sessão concluída",
      subtitle: "Veja o que você realizou e os pontos conquistados.",
    },
  };

  const find = (selector, root = document) => root.querySelector(selector);
  const findAll = (selector, root = document) => [...root.querySelectorAll(selector)];
  const pageTitle = find(".page-title");
  const pageSubtitle = find(".page-subtitle");
  const states = findAll("[data-session-state]");
  const configForm = find("#session-config-form");
  const registrationForm = find("#session-registration-form");
  const titleInput = find("#session-title");
  const objectiveInput = find("#session-objective");
  const customDurationField = find("[data-custom-duration]");
  const customDurationInput = find("#custom-duration");
  const monitoringInput = find("#monitor-computer");
  const typeError = find("#session-type-error");
  const titleError = find("#session-title-error");
  const durationError = find("#session-duration-error");
  const pauseButton = find('[data-session-action="pause"]');
  const resumeButton = find('[data-session-action="resume"]');
  const finishButton = find('[data-session-action="open-finish"]');
  const cancelButton = find('[data-session-action="open-cancel"]');
  const resetButton = find('[data-session-action="reset"]');
  const timerDisplay = find("[data-timer-display]");
  const timerRing = find(".session-timer-ring");
  const timerProgress = find(".session-timer-progress");
  const progressCopy = find("[data-progress-copy]");
  const motivationMessage = find("[data-motivation-message]");
  const message = find("[data-session-message]");
  const saveStatus = find("[data-save-status]");
  const recoveryCard = find("[data-session-recovery]");
  const finishBackdrop = find("[data-finish-modal]");
  const finishDialog = find(".session-modal", finishBackdrop);
  const cancelBackdrop = find("[data-cancel-modal]");
  const cancelDialog = find(".session-modal", cancelBackdrop);

  let currentSession = null;
  let recoverySession = null;
  let activeState = "config";
  let timerId = null;
  let elapsedSeconds = 0;
  let targetMinutes = 50;
  let isPaused = false;
  let resumeAfterModal = false;
  let lastFocusedElement = null;

  function selectedType() {
    return find('input[name="session_type"]:checked', configForm);
  }

  function selectedDuration() {
    const selected = find('input[name="session_duration"]:checked', configForm);
    if (!selected) return 0;
    if (selected.value === "custom") {
      return Number.parseInt(customDurationInput.value, 10) || 0;
    }
    return Number.parseInt(selected.value, 10) || 0;
  }

  function setFieldError(element, input, hasError) {
    element.hidden = !hasError;
    if (input) input.setAttribute("aria-invalid", String(hasError));
  }

  function validateConfiguration() {
    const type = selectedType();
    const title = titleInput.value.trim();
    const duration = selectedDuration();
    const customSelected =
      find('input[name="session_duration"]:checked', configForm)?.value === "custom";

    setFieldError(typeError, null, !type);
    setFieldError(titleError, titleInput, !title);
    setFieldError(durationError, customSelected ? customDurationInput : null, duration <= 0);
    if (!type) {
      find('input[name="session_type"]', configForm)?.focus();
      return false;
    }
    if (!title) {
      titleInput.focus();
      return false;
    }
    if (duration <= 0) {
      if (customSelected) customDurationInput.focus();
      return false;
    }
    return true;
  }

  function showMessage(text, tone = "error") {
    message.textContent = text;
    message.dataset.tone = tone;
    message.hidden = false;
  }

  function clearMessage() {
    message.hidden = true;
    message.textContent = "";
  }

  function updateConfigurationSummary() {
    const type = selectedType();
    const categoryLabel = type?.dataset.categoryLabel || "Não definida";
    find("[data-related-category]").textContent = categoryLabel;
    find("[data-config-type]").textContent = type?.dataset.label || "Não definido";
    find("[data-config-title]").textContent = titleInput.value.trim() || "Sem título";
    find("[data-config-duration]").textContent = selectedDuration() || "—";
    find("[data-config-category]").textContent = categoryLabel;
    find("[data-config-monitoring]").textContent =
      monitoringInput.checked ? "Solicitado" : "Desativado";
  }

  function updateCustomDurationVisibility() {
    const customSelected =
      find('input[name="session_duration"]:checked', configForm)?.value === "custom";
    customDurationField.hidden = !customSelected;
    customDurationInput.disabled = !customSelected;
    if (!customSelected) setFieldError(durationError, customDurationInput, false);
  }

  function showState(state, moveFocus = true) {
    activeState = state;
    states.forEach((section) => {
      section.hidden = section.dataset.sessionState !== state;
    });
    pageTitle.textContent = stateContent[state].title;
    pageSubtitle.textContent = stateContent[state].subtitle;
    const section = states.find((item) => item.dataset.sessionState === state);
    if (moveFocus && section) {
      section.tabIndex = -1;
      section.focus({ preventScroll: true });
    }
    window.scrollTo({
      top: 0,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }

  function formatTime(totalSeconds) {
    const safe = Math.max(0, Math.floor(totalSeconds));
    const hours = Math.floor(safe / 3600);
    const minutes = Math.floor((safe % 3600) / 60);
    const seconds = safe % 60;
    if (hours) {
      return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function formatDuration(totalSeconds) {
    const safe = Math.max(0, Math.floor(totalSeconds));
    const minutes = Math.floor(safe / 60);
    const seconds = safe % 60;
    return seconds ? `${minutes} min ${seconds} s` : `${minutes} min`;
  }

  function motivation(percent) {
    if (percent >= 100) return "Meta concluída. Você pode finalizar quando quiser.";
    if (percent >= 76) return "Falta pouco para concluir.";
    if (percent >= 51) return "Você já passou da metade.";
    if (percent >= 26) return "Bom começo. Continue concentrado.";
    return "Comece com calma e encontre seu ritmo.";
  }

  function updateProgress() {
    const targetSeconds = Math.max(targetMinutes * 60, 1);
    const percent = Math.min((elapsedSeconds / targetSeconds) * 100, 100);
    const display = formatTime(elapsedSeconds);
    timerDisplay.textContent = display;
    timerDisplay.setAttribute("datetime", `PT${elapsedSeconds}S`);
    timerRing.setAttribute(
      "aria-label",
      `${display} decorridos de ${targetMinutes} minutos`
    );
    timerProgress.setAttribute("stroke-dashoffset", String(100 - percent));
    progressCopy.textContent = `${Math.floor(elapsedSeconds / 60)} de ${targetMinutes} minutos`;
    motivationMessage.textContent = motivation(percent);
  }

  function clearTimer() {
    if (timerId !== null) {
      window.clearInterval(timerId);
      timerId = null;
    }
  }

  function runTimer() {
    clearTimer();
    timerId = window.setInterval(() => {
      if (elapsedSeconds < 86400) {
        elapsedSeconds += 1;
        updateProgress();
      } else {
        clearTimer();
        showMessage("A sessão atingiu o limite de 24 horas.");
      }
    }, 1000);
  }

  async function apiRequest(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.message || "Não foi possível concluir a ação.");
      error.status = response.status;
      error.errors = data.errors || {};
      throw error;
    }
    return data;
  }

  async function pending(button, action) {
    if (button.disabled) return null;
    button.disabled = true;
    clearMessage();
    try {
      return await action();
    } catch (error) {
      showMessage(error.message);
      return null;
    } finally {
      button.disabled = false;
    }
  }

  function configureRunningView(session) {
    currentSession = session;
    targetMinutes = session.target_duration_minutes || 50;
    elapsedSeconds = session.current_elapsed_seconds ?? session.actual_duration_seconds ?? 0;
    isPaused = session.status === "paused";
    find("[data-running-title]").textContent = session.title;
    find("[data-running-category]").textContent = session.related_category_label;
    find("[data-running-duration]").textContent = targetMinutes;
    find("[data-running-objective]").textContent =
      session.objective_text || "Sessão focada sem objetivo adicional.";
    find("[data-live-focus]").textContent =
      session.focus_percentage == null ? "—" : `${session.focus_percentage}%`;
    find("[data-live-productive]").textContent =
      formatDuration(session.productive_seconds || 0);
    find("[data-live-distracted]").textContent =
      formatDuration(session.distracted_seconds || 0);
    pauseButton.hidden = isPaused;
    resumeButton.hidden = !isPaused;
    updateProgress();
  }

  function renderBonus(sessionBonus, dailyBonus) {
    if (!sessionBonus || !dailyBonus) return;
    find("[data-summary-points]").textContent = `+${sessionBonus.score} pts`;
    find("[data-summary-daily-bonus]").textContent =
      `${dailyBonus.score} / ${dailyBonus.max_score} pts no dia.`;
    find("[data-point-total-badge]").textContent =
      `${sessionBonus.score} / ${sessionBonus.max_score} pts`;
    const list = find("[data-point-breakdown]");
    list.replaceChildren();
    sessionBonus.breakdown.forEach((item) => {
      const row = document.createElement("li");
      const label = document.createElement("span");
      const value = document.createElement("strong");
      label.textContent = item.label;
      value.textContent = `${item.score} / ${item.max_score} pts`;
      row.append(label, value);
      list.append(row);
    });
    const total = document.createElement("li");
    total.className = "point-breakdown-total";
    const totalLabel = document.createElement("span");
    const totalValue = document.createElement("strong");
    totalLabel.textContent = "Total";
    totalValue.textContent = `${sessionBonus.score} / ${sessionBonus.max_score} pts`;
    total.append(totalLabel, totalValue);
    list.append(total);
  }

  function configureSummaryView(session, sessionBonus, dailyBonus) {
    currentSession = session;
    find("[data-summary-title]").textContent = session.title;
    find("[data-summary-duration]").textContent =
      formatDuration(session.actual_duration_seconds || 0);
    find("[data-summary-focus]").textContent =
      session.focus_percentage == null ? "Não medido" : `${session.focus_percentage}%`;
    find("#session-did").value = session.result_text || "";
    find("#session-learned").value = session.learned_text || "";
    find("#session-difficulty").value = session.difficulty_text || "";
    findAll('input[name="session_rating"]', registrationForm).forEach((radio) => {
      radio.checked = Number(radio.value) === session.self_rating;
    });
    renderBonus(sessionBonus, dailyBonus);
  }

  async function startSession() {
    if (!validateConfiguration()) return;
    const type = selectedType();
    const payload = {
      session_type: type.value,
      title: titleInput.value.trim(),
      related_category: type.dataset.category,
      target_duration_minutes: selectedDuration(),
      computer_monitoring_enabled: monitoringInput.checked,
      objective_text: objectiveInput.value.trim(),
    };
    const submit = find('button[type="submit"]', configForm);
    const data = await pending(submit, () =>
      apiRequest(apiBase, { method: "POST", body: JSON.stringify(payload) })
    );
    if (!data) return;
    currentSession = data.session;
    localStorage.setItem(ACTIVE_SESSION_KEY, String(currentSession.id));
    recoveryCard.hidden = true;
    configureRunningView(currentSession);
    showState("running");
    runTimer();
    showMessage(data.message, "success");
  }

  async function pauseSession() {
    if (!currentSession || isPaused) return;
    const data = await pending(pauseButton, () =>
      apiRequest(`${apiBase}/${currentSession.id}/pause`, {
        method: "POST",
        body: JSON.stringify({ actual_duration_seconds: elapsedSeconds }),
      })
    );
    if (!data) return;
    clearTimer();
    configureRunningView(data.session);
    resumeButton.focus();
    showMessage(data.message, "success");
  }

  async function resumeSession() {
    if (!currentSession || !isPaused) return;
    const data = await pending(resumeButton, () =>
      apiRequest(`${apiBase}/${currentSession.id}/resume`, {
        method: "POST",
        body: "{}",
      })
    );
    if (!data) return;
    configureRunningView(data.session);
    runTimer();
    pauseButton.focus();
    showMessage(data.message, "success");
  }

  function openModal(backdrop, dialog) {
    lastFocusedElement = document.activeElement;
    resumeAfterModal = timerId !== null;
    clearTimer();
    backdrop.hidden = false;
    document.body.classList.add("session-modal-open");
    dialog.focus();
  }

  function closeModal(backdrop, shouldResume = true) {
    backdrop.hidden = true;
    document.body.classList.remove("session-modal-open");
    if (shouldResume && resumeAfterModal && activeState === "running" && !isPaused) {
      runTimer();
    }
    resumeAfterModal = false;
    if (lastFocusedElement instanceof HTMLElement) lastFocusedElement.focus();
  }

  async function finishSession() {
    if (!currentSession) return;
    const confirmButton = find("[data-modal-confirm]", finishBackdrop);
    const data = await pending(confirmButton, () =>
      apiRequest(`${apiBase}/${currentSession.id}/finish`, {
        method: "POST",
        body: JSON.stringify({
          actual_duration_seconds: elapsedSeconds,
          productive_seconds: currentSession.productive_seconds || 0,
          distracted_seconds: currentSession.distracted_seconds || 0,
        }),
      })
    );
    if (!data) return;
    clearTimer();
    closeModal(finishBackdrop, false);
    localStorage.removeItem(ACTIVE_SESSION_KEY);
    configureSummaryView(data.session, data.session_bonus, data.daily_session_bonus);
    showState("summary");
    showMessage(data.message, "success");
  }

  async function cancelSession() {
    const session = currentSession || recoverySession;
    if (!session) return;
    const confirmButton = find("[data-cancel-modal-confirm]");
    const total = currentSession
      ? elapsedSeconds
      : (session.current_elapsed_seconds ?? session.actual_duration_seconds ?? 0);
    const data = await pending(confirmButton, () =>
      apiRequest(`${apiBase}/${session.id}/cancel`, {
        method: "POST",
        body: JSON.stringify({ actual_duration_seconds: total }),
      })
    );
    if (!data) return;
    clearTimer();
    closeModal(cancelBackdrop, false);
    localStorage.removeItem(ACTIVE_SESSION_KEY);
    currentSession = null;
    recoverySession = null;
    recoveryCard.hidden = true;
    showState("config");
    showMessage(data.message, "success");
  }

  async function saveSummary() {
    if (!currentSession) return;
    const checkedRating = find('input[name="session_rating"]:checked', registrationForm);
    const payload = {
      result_text: find("#session-did").value.trim(),
      learned_text: find("#session-learned").value.trim(),
      difficulty_text: find("#session-difficulty").value.trim(),
      self_rating: checkedRating ? Number(checkedRating.value) : null,
    };
    const submit = find('button[type="submit"]', registrationForm);
    const data = await pending(submit, () =>
      apiRequest(`${apiBase}/${currentSession.id}/summary`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
    );
    if (!data) return;
    configureSummaryView(data.session, data.session_bonus, data.daily_session_bonus);
    saveStatus.hidden = false;
    saveStatus.focus?.();
    showMessage(data.message, "success");
  }

  function resetSession() {
    clearTimer();
    currentSession = null;
    elapsedSeconds = 0;
    targetMinutes = 50;
    isPaused = false;
    saveStatus.hidden = true;
    configForm.reset();
    registrationForm.reset();
    findAll(".session-checklist input").forEach((checkbox) => {
      checkbox.checked = false;
    });
    setFieldError(typeError, null, false);
    setFieldError(titleError, titleInput, false);
    setFieldError(durationError, customDurationInput, false);
    updateCustomDurationVisibility();
    updateConfigurationSummary();
    updateProgress();
    showState("config");
    clearMessage();
  }

  function showRecovery(session) {
    recoverySession = session;
    find("[data-recovery-title]").textContent = session.title;
    find("[data-recovery-status]").textContent =
      session.status === "paused" ? "está pausada." : "está em andamento.";
    recoveryCard.hidden = false;
  }

  async function loadRecovery() {
    let initial = null;
    try {
      initial = JSON.parse(find("[data-active-session]").textContent);
    } catch (_error) {
      initial = null;
    }
    const storedId = localStorage.getItem(ACTIVE_SESSION_KEY);
    try {
      if (storedId) {
        const stored = await apiRequest(`${apiBase}/${storedId}`);
        if (["running", "paused"].includes(stored.session.status)) {
          showRecovery(stored.session);
          return;
        }
        localStorage.removeItem(ACTIVE_SESSION_KEY);
      }
      const activeData = await apiRequest(`${apiBase}/active`);
      const active = activeData.active_session || initial;
      if (active) showRecovery(active);
    } catch (error) {
      if (error.status === 404) localStorage.removeItem(ACTIVE_SESSION_KEY);
      const active = initial;
      if (active) showRecovery(active);
      else showMessage("Não foi possível verificar sessões em aberto.");
    }
  }

  function continueRecovery() {
    if (!recoverySession) return;
    currentSession = recoverySession;
    localStorage.setItem(ACTIVE_SESSION_KEY, String(currentSession.id));
    recoveryCard.hidden = true;
    configureRunningView(currentSession);
    showState("running");
    if (!isPaused) runTimer();
  }

  function trapFocus(event, backdrop, dialog) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal(backdrop);
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = findAll(
      'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      dialog
    );
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

  configForm.addEventListener("submit", (event) => {
    event.preventDefault();
    startSession();
  });
  configForm.addEventListener("change", (event) => {
    if (event.target.name === "session_duration") updateCustomDurationVisibility();
    updateConfigurationSummary();
  });
  titleInput.addEventListener("input", () => {
    setFieldError(titleError, titleInput, false);
    updateConfigurationSummary();
  });
  customDurationInput.addEventListener("input", () => {
    setFieldError(durationError, customDurationInput, false);
    updateConfigurationSummary();
  });
  monitoringInput.addEventListener("change", updateConfigurationSummary);
  pauseButton.addEventListener("click", pauseSession);
  resumeButton.addEventListener("click", resumeSession);
  finishButton.addEventListener("click", () => openModal(finishBackdrop, finishDialog));
  cancelButton.addEventListener("click", () => openModal(cancelBackdrop, cancelDialog));
  resetButton.addEventListener("click", resetSession);
  findAll("[data-modal-cancel]", finishBackdrop).forEach((button) => {
    button.addEventListener("click", () => closeModal(finishBackdrop));
  });
  find("[data-modal-confirm]", finishBackdrop).addEventListener("click", finishSession);
  finishBackdrop.addEventListener("click", (event) => {
    if (event.target === finishBackdrop) closeModal(finishBackdrop);
  });
  finishDialog.addEventListener("keydown", (event) =>
    trapFocus(event, finishBackdrop, finishDialog)
  );
  findAll("[data-cancel-modal-close]", cancelBackdrop).forEach((button) => {
    button.addEventListener("click", () => closeModal(cancelBackdrop));
  });
  find("[data-cancel-modal-confirm]").addEventListener("click", cancelSession);
  cancelBackdrop.addEventListener("click", (event) => {
    if (event.target === cancelBackdrop) closeModal(cancelBackdrop);
  });
  cancelDialog.addEventListener("keydown", (event) =>
    trapFocus(event, cancelBackdrop, cancelDialog)
  );
  registrationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveSummary();
  });
  find('[data-recovery-action="continue"]').addEventListener("click", continueRecovery);
  find('[data-recovery-action="ignore"]').addEventListener("click", () => {
    recoveryCard.hidden = true;
  });
  find('[data-recovery-action="cancel"]').addEventListener("click", () => {
    currentSession = null;
    openModal(cancelBackdrop, cancelDialog);
  });

  updateCustomDurationVisibility();
  updateConfigurationSummary();
  updateProgress();
  loadRecovery();
});
