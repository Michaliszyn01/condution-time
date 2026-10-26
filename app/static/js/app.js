document.addEventListener("DOMContentLoaded", () => {
  const refreshIcons = () => {
    if (window.lucide) {
      window.lucide.createIcons({attrs: {"stroke-width": 2}});
    }
  };
  refreshIcons();

  document.querySelectorAll("[data-calendar-date]").forEach((button) => {
    button.addEventListener("click", () => {
      const url = new URL(window.location.href);
      url.searchParams.set("date", button.dataset.calendarDate);
      window.location.assign(url.toString());
    });
  });

  const header = document.querySelector("[data-global-header]");
  if (!header) return;

  const controls = [...header.querySelectorAll("[data-header-control]")];
  let activeControl = null;

  function closePopover(control = activeControl, returnFocus = true) {
    if (!control) return;
    const toggle = control.querySelector("[data-popover-toggle]");
    const popover = control.querySelector("[data-popover]");
    popover.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    activeControl = null;
    if (returnFocus) toggle.focus();
  }

  function openPopover(control) {
    if (activeControl && activeControl !== control) {
      closePopover(activeControl, false);
    }
    const toggle = control.querySelector("[data-popover-toggle]");
    const popover = control.querySelector("[data-popover]");
    popover.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    activeControl = control;
    popover.querySelector("button:not([disabled]), a, input, select")?.focus();
  }

  controls.forEach((control) => {
    const toggle = control.querySelector("[data-popover-toggle]");
    toggle.addEventListener("click", () => {
      if (activeControl === control) closePopover(control);
      else openPopover(control);
    });
    control.querySelectorAll("[data-popover-close]").forEach((button) => {
      button.addEventListener("click", () => closePopover(control));
    });
  });

  document.addEventListener("click", (event) => {
    if (activeControl && !activeControl.contains(event.target)) {
      closePopover(activeControl);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeControl) {
      event.preventDefault();
      closePopover(activeControl);
    }
  });

  const hydrationControl = header.querySelector('[data-header-control="hydration"]');
  const waterTotal = hydrationControl.querySelector("[data-water-total]");
  const waterGoal = hydrationControl.querySelector("[data-water-goal]");
  const waterPercentage = hydrationControl.querySelector("[data-water-percentage]");
  const waterProgress = hydrationControl.querySelector("[data-water-progress]");
  const waterTime = hydrationControl.querySelector("[data-water-time]");
  const waterRecent = hydrationControl.querySelector("[data-water-recent]");
  const waterFeedback = hydrationControl.querySelector("[data-water-feedback]");
  const waterForm = hydrationControl.querySelector("[data-water-custom]");
  const waterInput = waterForm.querySelector("input");

  function formatMl(value) {
    return `${Number(value).toLocaleString("pt-BR")} ml`;
  }

  function updateWaterSummary(result) {
    const visualPercentage = Math.min(Number(result.percentage), 100);
    waterTotal.textContent = formatMl(result.total_ml);
    waterGoal.textContent = formatMl(result.goal_ml);
    waterPercentage.textContent = `${Number(result.percentage).toLocaleString("pt-BR", {maximumFractionDigits: 1})}% da meta`;
    waterProgress.setAttribute("aria-valuenow", String(Math.round(visualPercentage)));
    waterProgress.querySelector("span").style.width = `${visualPercentage}%`;
    waterTime.textContent = result.current_time;
    waterRecent.replaceChildren(...result.recent_records.map((record) => {
      const item = document.createElement("li");
      const time = document.createElement("span");
      const amount = document.createElement("strong");
      time.textContent = record.consumed_at;
      amount.textContent = formatMl(record.amount_ml);
      item.append(time, amount);
      return item;
    }));
  }

  async function refreshWater() {
    const response = await fetch("/api/hydration/today", {
      headers: {"Accept": "application/json"}
    });
    if (!response.ok) throw new Error("Falha ao carregar hidratação.");
    updateWaterSummary(await response.json());
  }

  async function addWater(amount) {
    const numericAmount = Number(amount);
    if (!Number.isInteger(numericAmount) || numericAmount < 10 || numericAmount > 5000) {
      waterFeedback.dataset.tone = "error";
      waterFeedback.textContent = "Informe uma quantidade inteira entre 10 e 5.000 ml.";
      waterInput.focus();
      return;
    }
    waterFeedback.dataset.tone = "";
    waterFeedback.textContent = "Salvando...";
    try {
      const response = await fetch("/api/hydration/quick", {
        method: "POST",
        headers: {"Content-Type": "application/json", "Accept": "application/json"},
        body: JSON.stringify({amount_ml: numericAmount})
      });
      const result = await response.json();
      if (!response.ok) {
        waterFeedback.dataset.tone = "error";
        waterFeedback.textContent = result.message || "Não foi possível registrar a hidratação.";
        return;
      }
      updateWaterSummary(result);
      waterInput.value = "";
      waterFeedback.dataset.tone = "success";
      waterFeedback.textContent = `${numericAmount.toLocaleString("pt-BR")} ml registrados`;
      document.dispatchEvent(new CustomEvent("condution:hydration-updated", {detail: result}));
    } catch (_error) {
      waterFeedback.dataset.tone = "error";
      waterFeedback.textContent = "Não foi possível conectar ao aplicativo.";
    }
  }

  hydrationControl.querySelector("[data-popover-toggle]").addEventListener("click", () => {
    if (activeControl === hydrationControl) {
      refreshWater().catch(() => {
        waterFeedback.dataset.tone = "error";
        waterFeedback.textContent = "Não foi possível atualizar o total.";
      });
    }
  });
  hydrationControl.querySelectorAll("[data-water-amount]").forEach((button) => {
    button.addEventListener("click", () => addWater(button.dataset.waterAmount));
  });
  waterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addWater(waterInput.value);
  });

  const badge = header.querySelector("[data-notification-badge]");
  function updateBadge(count) {
    const numericCount = Number(count);
    badge.hidden = numericCount === 0;
    badge.textContent = numericCount > 9 ? "9+" : String(numericCount);
    badge.setAttribute("aria-label", `${numericCount} notificações não lidas`);
  }

  async function readNotification(item) {
    const response = await fetch(`/api/notifications/${item.dataset.notificationId}/read`, {
      method: "POST",
      headers: {"Accept": "application/json"}
    });
    const result = await response.json();
    if (!response.ok) return;
    item.classList.remove("is-unread");
    item.querySelector("[data-notification-read]")?.remove();
    updateBadge(result.unread_count);
  }

  document.querySelectorAll("[data-notification-read]").forEach((button) => {
    button.addEventListener("click", () => readNotification(button.closest("[data-notification-id]")));
  });
  header.querySelector("[data-notifications-read-all]").addEventListener("click", async () => {
    const response = await fetch("/api/notifications/read-all", {
      method: "POST",
      headers: {"Accept": "application/json"}
    });
    const result = await response.json();
    if (!response.ok) return;
    header.querySelectorAll(".notification-item.is-unread").forEach((item) => {
      item.classList.remove("is-unread");
      item.querySelector("[data-notification-read]")?.remove();
    });
    updateBadge(result.unread_count);
  });

  document.querySelectorAll("[data-notification-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = button.closest("[data-notification-id]");
      const response = await fetch(`/api/notifications/${item.dataset.notificationId}`, {
        method: "DELETE",
        headers: {"Accept": "application/json"}
      });
      if (response.ok) item.remove();
    });
  });

  header.querySelectorAll("[data-desktop-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const endpoint = button.dataset.desktopAction === "exit"
        ? "/api/desktop/exit"
        : "/api/desktop/open-data-folder";
      button.disabled = true;
      try {
        await fetch(endpoint, {method: "POST", headers: {"Accept": "application/json"}});
      } finally {
        if (button.dataset.desktopAction !== "exit") button.disabled = false;
      }
    });
  });

  refreshIcons();
});
