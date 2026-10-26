document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector("[data-registration-page]");
  if (!page) return;

  const categoriesState = page.querySelector('[data-registration-state="categories"]');
  const formState = page.querySelector('[data-registration-state="form"]');
  const successState = page.querySelector("[data-register-success]");
  const forms = [...page.querySelectorAll("[data-register-form]")];
  const headerTitle = document.querySelector(".topbar-copy h1");
  const headerSubtitle = document.querySelector(".topbar-copy > p:last-child");
  const sideCategory = page.querySelector("[data-side-category]");
  const sideStatus = page.querySelector("[data-required-status]");
  const liveSummary = page.querySelector("[data-live-summary]");
  const successCategory = page.querySelector("[data-success-category]");
  const successCategoryMeta = page.querySelector("[data-success-category-meta]");
  const successTitle = page.querySelector("[data-success-title]");
  const successSummary = page.querySelector("[data-success-summary]");
  const successTime = page.querySelector("[data-success-time]");
  const successCategoryLink = page.querySelector("[data-success-category-link]");
  const toast = page.querySelector("[data-register-toast]");
  const dateBanner = page.querySelector("[data-registering-date]");
  const watchModal = page.querySelector("[data-watch-modal]");
  const watchList = page.querySelector("[data-watch-records]");
  const watchError = page.querySelector("[data-watch-error]");
  let currentCategory = null;
  let toastTimer = null;
  let watchKind = null;

  const categoryData = {
    study: {
      label: "Estudo",
      pageTitle: "Registrar estudo",
      subtitle: "Adicione uma atividade de estudo que já aconteceu.",
      successTitle: "Estudo registrado com sucesso"
    },
    sleep: {
      label: "Sono",
      pageTitle: "Registrar sono",
      subtitle: "Adicione uma noite de sono e como você acordou.",
      successTitle: "Sono registrado com sucesso"
    },
    training: {
      label: "Treino",
      pageTitle: "Registrar treino",
      subtitle: "Adicione uma atividade física que já aconteceu.",
      successTitle: "Treino registrado com sucesso"
    },
    nutrition: {
      label: "Alimentação",
      pageTitle: "Registrar alimentação",
      subtitle: "Adicione uma refeição ou um registro de hidratação.",
      successTitle: "Registro de alimentação adicionado"
    }
  };

  function setHeader(title, subtitle) {
    if (headerTitle) headerTitle.textContent = title;
    if (headerSubtitle) headerSubtitle.textContent = subtitle;
  }

  function hideAllStates() {
    categoriesState.hidden = true;
    formState.hidden = true;
    successState.hidden = true;
  }

  function activeForm() {
    return forms.find((form) => form.dataset.registerForm === currentCategory);
  }

  function selectValue(form, name) {
    return form.querySelector(`[name="${name}"]:checked`)?.value || "";
  }

  function numericValue(form, name) {
    return Number(form.elements[name]?.value || 0);
  }

  function optionalNumericValue(form, name) {
    const value = form.elements[name]?.value;
    return value === "" || value == null ? null : Number(value);
  }

  function localDateISO() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatDuration(totalMinutes) {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (!hours) return `${minutes} min`;
    if (!minutes) return `${hours}h`;
    return `${hours}h ${minutes}min`;
  }

  function durationFromFields(form) {
    return (
      numericValue(form, `${currentCategory}_hours`) * 60 +
      numericValue(form, `${currentCategory}_minutes`)
    );
  }

  function sleepMinutes(form) {
    const start = form.elements.sleep_start.value;
    const end = form.elements.sleep_end.value;
    if (!start || !end) return 0;
    const [startHours, startMinutes] = start.split(":").map(Number);
    const [endHours, endMinutes] = end.split(":").map(Number);
    const startTotal = startHours * 60 + startMinutes;
    let endTotal = endHours * 60 + endMinutes;
    if (endTotal <= startTotal) endTotal += 24 * 60;
    return endTotal - startTotal;
  }

  function intensityLabel(value) {
    if (value <= 3) return "leve";
    if (value <= 6) return "moderada";
    if (value <= 8) return "alta";
    return "muito alta";
  }

  function updateSleepDuration(form) {
    const output = form.querySelector("[data-sleep-duration]");
    if (output) output.textContent = formatDuration(sleepMinutes(form));
  }

  function updateTrainingFields(form) {
    const range = form.elements.training_intensity;
    const value = Number(range.value);
    form.querySelector("[data-intensity-value]").textContent = String(value);
    form.querySelector("[data-intensity-label]").textContent = intensityLabel(value);

    const discomfort = selectValue(form, "training_discomfort");
    const conditional = form.querySelector("[data-conditional-field]");
    const location = form.elements.training_discomfort_location;
    const shouldShow = discomfort !== "Nenhum";
    conditional.hidden = !shouldShow;
    location.required = shouldShow;
    if (!shouldShow) {
      location.value = "";
      clearFieldError(location);
    }
  }

  function updateNutritionMode(form) {
    const mode = selectValue(form, "nutrition_mode");
    const mealPanel = form.querySelector('[data-nutrition-panel="meal"]');
    const hydrationPanel = form.querySelector('[data-nutrition-panel="hydration"]');
    const mealActive = mode === "Refeição";
    mealPanel.hidden = !mealActive;
    hydrationPanel.hidden = mealActive;
    form.querySelector("[data-nutrition-submit-label]").textContent =
      mealActive ? "Registrar refeição" : "Registrar hidratação";
  }

  function buildSummary(form) {
    if (currentCategory === "study") {
      const subject = form.elements.study_subject.value;
      const topic = form.elements.study_topic.value.trim() || "Assunto não informado";
      return `${subject} • ${topic} • ${formatDuration(durationFromFields(form))}`;
    }
    if (currentCategory === "sleep") {
      const quality = selectValue(form, "sleep_quality").toLowerCase();
      return `${formatDuration(sleepMinutes(form))} • Qualidade ${quality}`;
    }
    if (currentCategory === "training") {
      const activity = form.elements.training_name.value.trim() || "Atividade não informada";
      const intensity = intensityLabel(Number(form.elements.training_intensity.value));
      return `${activity} • ${formatDuration(durationFromFields(form))} • Intensidade ${intensity}`;
    }

    const mode = selectValue(form, "nutrition_mode");
    if (mode === "Hidratação") {
      const amount = form.elements.water_amount.value || "0";
      return `Hidratação • ${amount} ${form.elements.water_unit.value}`;
    }
    const foods = form.elements.meal_foods.value.trim() || "Alimentos não informados";
    return `${form.elements.meal_type.value} • ${foods}`;
  }

  function updatePreview() {
    const form = activeForm();
    if (!form) return;
    if (currentCategory === "sleep") updateSleepDuration(form);
    if (currentCategory === "training") updateTrainingFields(form);
    if (currentCategory === "nutrition") updateNutritionMode(form);
    liveSummary.textContent = buildSummary(form);
    sideStatus.textContent = "Revise e confirme os dados";
  }

  function clearFieldError(field) {
    field.removeAttribute("aria-invalid");
    const describedBy = field.getAttribute("aria-describedby");
    if (describedBy) {
      describedBy.split(" ").forEach((id) => {
        const message = document.getElementById(id);
        if (message?.matches("[data-field-error]")) message.hidden = true;
      });
    }
  }

  function showFieldError(field, errorElement) {
    field.setAttribute("aria-invalid", "true");
    if (errorElement) errorElement.hidden = false;
  }

  function validateDuration(form) {
    const total = durationFromFields(form);
    const fieldset = form.querySelector(".registration-duration");
    const error = fieldset.querySelector("[data-duration-error]");
    const hours = fieldset.querySelector("[data-duration-hours]");
    const minutes = fieldset.querySelector("[data-duration-minutes]");
    const valid = total > 0 && numericValue(form, `${currentCategory}_minutes`) <= 59;
    error.hidden = valid;
    [hours, minutes].forEach((field) => {
      if (valid) field.removeAttribute("aria-invalid");
      else field.setAttribute("aria-invalid", "true");
    });
    return valid;
  }

  function validateStudy(form) {
    let valid = validateDuration(form);
    const topic = form.elements.study_topic;
    const topicError = document.getElementById("study-topic-error");
    if (!topic.value.trim()) {
      showFieldError(topic, topicError);
      valid = false;
    }
    const questions = numericValue(form, "study_questions");
    const correct = numericValue(form, "study_correct");
    const correctField = form.elements.study_correct;
    const correctError = document.getElementById("study-correct-error");
    if (questions < 0 || correct < 0 || correct > questions) {
      showFieldError(correctField, correctError);
      valid = false;
    }
    return valid;
  }

  function validateSleep(form) {
    const required = [
      form.elements.sleep_date,
      form.elements.sleep_start,
      form.elements.sleep_end
    ];
    const valid = required.every((field) => field.value) && sleepMinutes(form) > 0;
    form.querySelector("[data-form-error]").hidden = valid;
    required.forEach((field) => {
      if (field.value) field.removeAttribute("aria-invalid");
      else field.setAttribute("aria-invalid", "true");
    });
    return valid;
  }

  function validateTraining(form) {
    let valid = validateDuration(form);
    const name = form.elements.training_name;
    if (!name.value.trim()) {
      showFieldError(name, document.getElementById("training-name-error"));
      valid = false;
    }
    const location = form.elements.training_discomfort_location;
    if (location.required && !location.value.trim()) {
      showFieldError(location, document.getElementById("training-discomfort-location-error"));
      valid = false;
    }
    return valid;
  }

  function validateNutrition(form) {
    if (selectValue(form, "nutrition_mode") === "Hidratação") {
      const water = form.elements.water_amount;
      const valid = Number(water.value) > 0;
      if (!valid) showFieldError(water, document.getElementById("water-amount-error"));
      return valid;
    }
    const foods = form.elements.meal_foods;
    const valid = Boolean(foods.value.trim());
    if (!valid) showFieldError(foods, document.getElementById("meal-foods-error"));
    return valid;
  }

  function validateForm(form) {
    form.querySelectorAll("[aria-invalid]").forEach((field) => clearFieldError(field));
    const dateField = form.elements[`${currentCategory}_date`] ||
      (currentCategory === "nutrition" ? form.elements.nutrition_date : null);
    const dateValid = dateField && dateField.value && dateField.value <= localDateISO();
    if (!dateValid && dateField) dateField.setAttribute("aria-invalid", "true");
    let categoryValid;
    if (currentCategory === "study") categoryValid = validateStudy(form);
    else if (currentCategory === "sleep") categoryValid = validateSleep(form);
    else if (currentCategory === "training") categoryValid = validateTraining(form);
    else categoryValid = validateNutrition(form);
    return Boolean(dateValid && categoryValid);
  }

  function buildPayload(form) {
    if (currentCategory === "study") {
      return {
        record_date: form.elements.study_date.value,
        subject: form.elements.study_subject.value,
        topic: form.elements.study_topic.value,
        duration_minutes: durationFromFields(form),
        questions_count: optionalNumericValue(form, "study_questions"),
        correct_answers: optionalNumericValue(form, "study_correct"),
        focus_quality: selectValue(form, "study_focus"),
        learned_text: form.elements.study_learned.value,
        difficulty_text: form.elements.study_difficulty.value,
        record_origin: selectValue(form, "study_origin")
      };
    }
    if (currentCategory === "sleep") {
      if (form.elements.watch_record_id?.value) {
        return {
          perceived_quality: selectValue(form, "sleep_quality"),
          woke_restored: selectValue(form, "sleep_rested"),
          notes: form.elements.sleep_notes.value
        };
      }
      return {
        record_date: form.elements.sleep_date.value,
        sleep_start: form.elements.sleep_start.value,
        sleep_end: form.elements.sleep_end.value,
        perceived_quality: selectValue(form, "sleep_quality"),
        awakenings_count: numericValue(form, "sleep_awakenings"),
        woke_restored: selectValue(form, "sleep_rested"),
        notes: form.elements.sleep_notes.value,
        record_origin: selectValue(form, "sleep_origin")
      };
    }
    if (currentCategory === "training") {
      if (form.elements.watch_record_id?.value) {
        return {
          intensity: numericValue(form, "training_intensity"),
          perceived_performance: selectValue(form, "training_performance"),
          exercises_text: form.elements.training_exercises.value,
          discomfort_level: selectValue(form, "training_discomfort"),
          discomfort_location: form.elements.training_discomfort_location.value,
          notes: form.elements.training_notes.value
        };
      }
      return {
        record_date: form.elements.training_date.value,
        training_type: form.elements.training_type.value,
        activity_name: form.elements.training_name.value,
        duration_minutes: durationFromFields(form),
        intensity: numericValue(form, "training_intensity"),
        perceived_performance: selectValue(form, "training_performance"),
        exercises_text: form.elements.training_exercises.value,
        discomfort_level: selectValue(form, "training_discomfort"),
        discomfort_location: form.elements.training_discomfort_location.value,
        notes: form.elements.training_notes.value
      };
    }
    if (selectValue(form, "nutrition_mode") === "Hidratação") {
      return {
        record_date: form.elements.nutrition_date.value,
        amount: form.elements.water_amount.value,
        unit: form.elements.water_unit.value,
        consumed_at: form.elements.water_time.value,
        notes: form.elements.water_notes.value
      };
    }
    return {
      record_date: form.elements.nutrition_date.value,
      meal_type: form.elements.meal_type.value,
      meal_time: form.elements.meal_time.value,
      foods_text: form.elements.meal_foods.value,
      approximate_amount: form.elements.meal_amount.value,
      has_protein: selectValue(form, "meal_protein"),
      has_fruits_or_vegetables: selectValue(form, "meal_produce"),
      perceived_quality: selectValue(form, "meal_quality"),
      notes: form.elements.meal_notes.value
    };
  }

  function recordEndpoint(form) {
    const watchId = form.elements.watch_record_id?.value;
    if (watchId && ["training", "sleep"].includes(currentCategory)) {
      return `/api/records/watch/${currentCategory}/${watchId}`;
    }
    if (currentCategory !== "nutrition") {
      return `/api/records/${currentCategory}`;
    }
    return selectValue(form, "nutrition_mode") === "Hidratação"
      ? "/api/records/hydration"
      : "/api/records/meal";
  }

  function updateCategoryStatuses(counts) {
    page.querySelectorAll("[data-register-category]").forEach((button) => {
      const category = button.dataset.registerCategory;
      const count = Number(counts[category] || 0);
      const badge = button.querySelector(".badge");
      if (!badge) return;
      if (category === "sleep" && count === 0) {
        badge.textContent = "Ainda não registrado";
      } else if (count === 0) {
        badge.textContent = "Nenhum registro nesta data";
      } else if (count === 1) {
        badge.textContent = "1 registro nesta data";
      } else {
        badge.textContent = `${count} registros nesta data`;
      }
    });
  }

  function showServerError(form, result) {
    const fieldIds = {
      record_date:
        currentCategory === "sleep" ? "sleep-date" :
        currentCategory === "study" ? "study-date" :
        currentCategory === "training" ? "training-date" :
        "nutrition-date",
      subject: "study-subject",
      topic: "study-topic",
      duration_minutes:
        currentCategory === "study" ? "study_minutes" : "training_minutes",
      questions_count: "study-questions",
      correct_answers: "study-correct",
      sleep_start: "sleep-start",
      sleep_end: "sleep-end",
      awakenings_count: "sleep-awakenings",
      training_type: "training-type",
      activity_name: "training-name",
      intensity: "training-intensity",
      discomfort_location: "training-discomfort-location",
      meal_type: "meal-type",
      meal_time: "meal-time",
      foods_text: "meal-foods",
      amount: "water-amount",
      consumed_at: "water-time"
    };
    const errors = result.errors || {};
    const firstEntry = Object.entries(errors)[0];
    const message = firstEntry?.[1] || result.message ||
      "Não foi possível salvar o registro. Verifique os campos e tente novamente.";
    sideStatus.textContent = message;

    const fieldId = firstEntry ? fieldIds[firstEntry[0]] : null;
    const field = fieldId ? document.getElementById(fieldId) : null;
    if (field) {
      field.setAttribute("aria-invalid", "true");
      field.focus();
    } else {
      form.querySelector("input, select, textarea")?.focus();
    }
  }

  async function saveRecord(form) {
    const watchId = form.elements.watch_record_id?.value;
    const response = await fetch(recordEndpoint(form), {
      method: watchId ? "PATCH" : "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(buildPayload(form))
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      showServerError(form, result);
      return null;
    }
    updateCategoryStatuses(result.daily_counts || {});
    return result;
  }

  function showCategories() {
    currentCategory = null;
    hideAllStates();
    categoriesState.hidden = false;
    forms.forEach((form) => {
      form.hidden = true;
    });
    setHeader(
      "Registrar atividade",
      "Escolha uma categoria para adicionar informações ao seu dia."
    );
    categoriesState.querySelector("[data-register-category]")?.focus();
  }

  function openCategory(button) {
    currentCategory = button.dataset.registerCategory;
    const details = categoryData[currentCategory];
    hideAllStates();
    formState.hidden = false;
    forms.forEach((form) => {
      form.hidden = form.dataset.registerForm !== currentCategory;
    });
    sideCategory.textContent = details.label;
    successCategoryLink.href = button.dataset.categoryUrl;
    setHeader(details.pageTitle, details.subtitle);
    updatePreview();
    activeForm().querySelector("input, select, textarea")?.focus();
  }

  function formatSelectedDate(value) {
    if (!value || value === localDateISO()) return "Hoje";
    return new Intl.DateTimeFormat("pt-BR", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC"
    }).format(new Date(`${value}T12:00:00Z`));
  }

  function updateDateBanner(value) {
    if (dateBanner) dateBanner.textContent = formatSelectedDate(value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function watchMetric(label, value) {
    if (value == null || value === "") return "";
    return `<span><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong></span>`;
  }

  function renderWatchRecord(record) {
    const training = watchKind === "training";
    const stageMetrics = !training
      ? record.stages.items.map((item) => watchMetric(item.label, item.duration)).join("")
      : "";
    const metrics = training
      ? [
          watchMetric("Início", record.started_at || "—"),
          watchMetric("Fim", record.ended_at || "—"),
          watchMetric("Duração", record.duration),
          watchMetric("Distância", record.distance_km == null ? null : `${record.distance_km} km`),
          watchMetric("Calorias", record.calories == null ? null : `${record.calories} kcal`),
          watchMetric("FC média", record.average_heart_rate == null ? null : `${record.average_heart_rate} bpm`),
          watchMetric("FC máxima", record.maximum_heart_rate == null ? null : `${record.maximum_heart_rate} bpm`),
          watchMetric("Passos", record.steps)
        ].join("")
      : [
          watchMetric("Dormiu", record.sleep_start),
          watchMetric("Acordou", record.sleep_end),
          watchMetric("Duração", record.duration),
          watchMetric("Despertares", record.awakenings_count),
          watchMetric("FC média", record.average_heart_rate == null ? null : `${record.average_heart_rate} bpm`),
          watchMetric("Oxigenação", record.average_spo2 == null ? null : `${record.average_spo2}%`),
          stageMetrics
        ].join("");
    const title = training ? record.training_type_label : `Sono de ${record.date_label}`;
    const detail = training
      ? record.activity_name
      : "Os estágios são exibidos sem forçar a soma com a duração total.";
    return `
      <article class="watch-record-card" data-watch-record-id="${record.id}">
        <header>
          <div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(record.date_label)} · ${escapeHtml(record.origin)}</span></div>
          <span class="badge">${escapeHtml(record.status_label || "Disponível")}</span>
        </header>
        <div class="watch-metrics">${metrics}</div>
        <details><summary>Ver detalhes</summary><p>${escapeHtml(detail)}</p></details>
        <div class="watch-record-actions">
          <button class="button button--primary" type="button" data-use-watch="${record.id}">Usar este ${training ? "treino" : "sono"}</button>
          <button class="button button--secondary" type="button" data-ignore-watch="${record.id}">Ignorar sugestão</button>
        </div>
      </article>`;
  }

  function applyWatchRecord(record) {
    const form = forms.find((item) => item.dataset.registerForm === watchKind);
    form.elements.watch_record_id.value = record.id;
    if (watchKind === "training") {
      form.elements.training_date.value = record.record_date;
      form.elements.training_type.value = record.training_type;
      form.elements.training_name.value = record.activity_name;
      form.elements.training_hours.value = Math.floor(record.duration_minutes / 60);
      form.elements.training_minutes.value = record.duration_minutes % 60;
      [
        form.elements.training_date,
        form.elements.training_type,
        form.elements.training_name,
        form.elements.training_hours,
        form.elements.training_minutes
      ].forEach((field) => field.classList.add("is-watch-filled"));
    } else {
      form.elements.sleep_date.value = record.record_date;
      form.elements.sleep_start.value = record.sleep_start;
      form.elements.sleep_end.value = record.sleep_end;
      form.elements.sleep_awakenings.value = record.awakenings_count;
      [
        form.elements.sleep_date,
        form.elements.sleep_start,
        form.elements.sleep_end,
        form.elements.sleep_awakenings
      ].forEach((field) => field.classList.add("is-watch-filled"));
    }
    updateDateBanner(record.record_date);
    updatePreview();
    watchModal.hidden = true;
    sideStatus.textContent = watchKind === "sleep"
      ? "Dados objetivos importados do Galaxy Watch. Complete como você se sentiu."
      : "Campos objetivos preenchidos pelo Galaxy Watch.";
  }

  async function loadWatchSuggestions(kind) {
    watchKind = kind;
    watchError.hidden = true;
    watchList.innerHTML = "<p>Carregando registros importados...</p>";
    watchModal.hidden = false;
    watchModal.querySelector("[data-watch-title]").textContent =
      kind === "training" ? "Treinos do relógio" : "Sono do relógio";
    watchModal.querySelector("[data-watch-guidance]").textContent =
      kind === "training"
        ? "Escolha um treino e complete apenas sua percepção."
        : "Dados objetivos importados do Galaxy Watch. Complete como você se sentiu.";
    watchModal.querySelector(".watch-modal").focus();
    try {
      const response = await fetch(`/api/records/watch/${kind}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.message);
      watchList.innerHTML = result.records.length
        ? result.records.map(renderWatchRecord).join("")
        : "<p>Nenhum registro do relógio está aguardando complemento.</p>";
      watchList.querySelectorAll("[data-use-watch]").forEach((button) => {
        button.addEventListener("click", () => {
          const record = result.records.find(
            (item) => item.id === Number(button.dataset.useWatch)
          );
          if (record) applyWatchRecord(record);
        });
      });
      watchList.querySelectorAll("[data-ignore-watch]").forEach((button) => {
        button.addEventListener("click", async () => {
          const response = await fetch(
            `/api/records/watch/${kind}/${button.dataset.ignoreWatch}/ignore`,
            { method: "POST" }
          );
          if (response.ok) button.closest(".watch-record-card").remove();
        });
      });
    } catch (error) {
      watchList.innerHTML = "";
      watchError.textContent =
        error.message || "Não foi possível carregar os dados do relógio.";
      watchError.hidden = false;
    }
  }

  function resetCurrentForm() {
    const form = activeForm();
    if (!form) return;
    form.reset();
    form.querySelectorAll("[aria-invalid]").forEach((field) => clearFieldError(field));
    form.querySelectorAll(".registration-error").forEach((message) => {
      message.hidden = true;
    });
    updatePreview();
  }

  function showSuccess(form, savedRecord) {
    const label = categoryData[currentCategory].label;
    const summary = buildSummary(form);
    hideAllStates();
    successState.hidden = false;
    successCategory.textContent = label;
    successCategoryMeta.textContent = label;
    successTitle.textContent = categoryData[currentCategory].successTitle;
    successSummary.textContent = summary;
    const savedAt = savedRecord?.created_at
      ? new Date(savedRecord.created_at)
      : new Date();
    successTime.textContent = new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit"
    }).format(savedAt);
    setHeader("Registro concluído", "Os dados foram salvos com segurança.");

    toast.querySelector("span").textContent = "Registro salvo com sucesso.";
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 3600);
    successTitle.focus?.();
  }

  page.querySelectorAll("[data-register-category]").forEach((button) => {
    button.addEventListener("click", () => openCategory(button));
  });

  const categoryAliases = {
    estudo: "study",
    sono: "sleep",
    treino: "training",
    alimentacao: "nutrition"
  };
  const requestedCategoryParam =
    new URLSearchParams(window.location.search).get("categoria");
  const requestedCategory =
    categoryAliases[requestedCategoryParam] || requestedCategoryParam;
  const requestedButton = requestedCategory
    ? page.querySelector(`[data-register-category="${requestedCategory}"]`)
    : null;
  if (requestedButton) {
    openCategory(requestedButton);
  }

  page.querySelector("[data-back-categories]").addEventListener("click", showCategories);
  page.querySelectorAll("[data-register-cancel]").forEach((button) => {
    button.addEventListener("click", showCategories);
  });

  forms.forEach((form) => {
    form.addEventListener("input", updatePreview);
    form.addEventListener("change", updatePreview);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!validateForm(form)) {
        form.querySelector('[aria-invalid="true"]')?.focus();
        sideStatus.textContent = "Revise os campos destacados";
        return;
      }
      const submitButton = form.querySelector('button[type="submit"]');
      submitButton.disabled = true;
      sideStatus.textContent = "Salvando registro...";
      try {
        const result = await saveRecord(form);
        if (result) {
          showSuccess(form, result.record);
        }
      } catch {
        showServerError(form, {
          message: (
            "Não foi possível salvar o registro. " +
            "Verifique sua conexão local e tente novamente."
          )
        });
      } finally {
        submitButton.disabled = false;
      }
    });
  });

  page.querySelectorAll('input[type="date"]').forEach((field) => {
    field.addEventListener("change", () => updateDateBanner(field.value));
  });
  page.querySelectorAll("[data-open-watch]").forEach((button) => {
    button.addEventListener("click", () => {
      loadWatchSuggestions(button.dataset.openWatch);
    });
  });
  page.querySelectorAll("[data-close-watch]").forEach((button) => {
    button.addEventListener("click", () => {
      watchModal.hidden = true;
    });
  });
  watchModal?.addEventListener("click", (event) => {
    if (event.target === watchModal) watchModal.hidden = true;
  });

  page.querySelector("[data-register-another]").addEventListener("click", () => {
    hideAllStates();
    formState.hidden = false;
    forms.forEach((form) => {
      form.hidden = form.dataset.registerForm !== currentCategory;
    });
    resetCurrentForm();
    setHeader(
      categoryData[currentCategory].pageTitle,
      categoryData[currentCategory].subtitle
    );
    activeForm().querySelector("input, select, textarea")?.focus();
  });
});
