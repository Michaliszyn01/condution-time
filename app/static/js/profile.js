(() => {
  const page = document.querySelector("[data-profile-page]");
  if (!page) return;

  const selector = document.querySelector("#profile-period");
  selector?.addEventListener("change", () => {
    const url = new URL(window.location.href);
    url.searchParams.set("period", selector.value);
    url.searchParams.set("tab", page.dataset.tab);
    window.location.assign(url.toString());
  });

  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((tab, index) => {
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let target = index;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") target = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      tabs[target].focus();
      if (event.key === "Home" || event.key === "End") window.location.assign(tabs[target].href);
    });
  });

  let returnFocus = null;
  document.querySelectorAll("[data-open-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.openModal);
      if (!dialog) return;
      returnFocus = button;
      dialog.showModal();
      dialog.querySelector("input, textarea, button")?.focus();
    });
  });
  document.querySelectorAll(".profile-dialog").forEach((dialog) => {
    dialog.addEventListener("close", () => returnFocus?.focus());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.querySelectorAll("[data-close-modal]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const focusable = [...dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]')];
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
    });
  });

  document.querySelectorAll("[data-profile-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const feedback = form.querySelector("[data-form-feedback]");
      const payload = Object.fromEntries(new FormData(form));
      Object.keys(payload).forEach((key) => {
        if (payload[key] === "") payload[key] = null;
      });
      feedback.classList.remove("is-error");
      feedback.textContent = "Salvando...";
      try {
        const response = await fetch(form.dataset.endpoint, {
          method: "PATCH",
          headers: {"Content-Type": "application/json", "Accept": "application/json"},
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        feedback.textContent = result.message;
        feedback.classList.toggle("is-error", !response.ok);
        if (!response.ok) return;
        if (result.profile) {
          document.querySelector("[data-profile-name]").textContent = result.profile.name;
          document.querySelector("[data-profile-avatar]").textContent = result.profile.initials;
          document.querySelector(".profile-summary strong")?.replaceChildren(result.profile.name);
          document.querySelector(".profile-summary .avatar")?.replaceChildren(result.profile.initials);
        }
        if (form.dataset.endpoint.endsWith("/goals")) {
          window.setTimeout(() => window.location.reload(), 250);
        } else {
          window.setTimeout(() => form.closest("dialog")?.close(), 350);
        }
      } catch {
        feedback.textContent = "Não foi possível salvar. Tente novamente.";
        feedback.classList.add("is-error");
      }
    });
  });

  const raw = document.querySelector("#profile-chart-data");
  if (!raw || !window.Chart) return;
  const data = JSON.parse(raw.textContent);
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {labels: {usePointStyle: true, boxWidth: 8}},
      tooltip: {displayColors: true}
    },
    scales: {
      x: {grid: {display: false}},
      y: {beginAtZero: true, grid: {color: "rgba(148,163,184,.18)"}}
    }
  };
  const tab = page.dataset.tab;
  let canvas;
  let config;
  if (tab === "overview") {
    canvas = document.querySelector("#profile-overview-chart");
    config = {
      type: "bar",
      data: {labels: data.labels, datasets: [
        {label: "Período atual", data: data.current, backgroundColor: "#246bfd", borderRadius: 5},
        {label: "Período anterior", data: data.previous, backgroundColor: "#cbdcff", borderRadius: 5}
      ]},
      options: {...baseOptions, scales: {...baseOptions.scales, y: {...baseOptions.scales.y, max: 100, ticks: {callback: (value) => `${value}%`}}}}
    };
  } else if (tab === "study") {
    canvas = document.querySelector("#profile-study-chart");
    config = {type: "bar", data, options: {...baseOptions, scales: {x: {...baseOptions.scales.x, stacked: true}, y: {...baseOptions.scales.y, stacked: true}}}};
  } else if (tab === "health") {
    canvas = document.querySelector("#profile-health-chart");
    config = {type: "line", data: {labels: data.map((item) => item.date), datasets: [
      {label: "Medição", data: data.map((item) => item.weight), borderColor: "#94a3b8", backgroundColor: "#94a3b8", pointRadius: 3, showLine: false},
      {label: "Média móvel", data: data.map((item) => item.rolling), borderColor: "#246bfd", backgroundColor: "rgba(36,107,253,.12)", tension: .3, fill: true, pointRadius: 1}
    ]}, options: baseOptions};
  } else if (tab === "training") {
    canvas = document.querySelector("#profile-training-chart");
    config = {type: "bar", data: {labels: data.map((item) => item.date), datasets: [{label: "Duração (min)", data: data.map((item) => item.minutes), backgroundColor: "#7c3aed", borderRadius: 5}]}, options: baseOptions};
  } else if (tab === "sleep") {
    canvas = document.querySelector("#profile-sleep-chart");
    config = {type: "line", data: {labels: data.map((item) => item.date), datasets: [{label: "Duração (h)", data: data.map((item) => Math.round(item.minutes / 6) / 10), borderColor: "#4f46e5", backgroundColor: "rgba(79,70,229,.12)", tension: .25, fill: true}]}, options: baseOptions};
  } else if (tab === "computer") {
    canvas = document.querySelector("#profile-computer-chart");
    config = {type: "bar", data: {labels: data.map((item) => item.date), datasets: [
      {label: "Produtivo (min)", data: data.map((item) => Math.round(item.productive / 60)), backgroundColor: "#22a06b", borderRadius: 4},
      {label: "Distração (min)", data: data.map((item) => Math.round(item.distracting / 60)), backgroundColor: "#ef6b6b", borderRadius: 4}
    ]}, options: baseOptions};
  }
  if (canvas && config) new window.Chart(canvas, config);
})();
