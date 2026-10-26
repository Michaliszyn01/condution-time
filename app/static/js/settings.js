(() => {
  const form = document.querySelector("#desktop-settings-form");
  if (!form) return;

  const status = document.querySelector("#desktop-status");
  const feedback = document.querySelector("#settings-feedback");
  const fields = {
    start_with_windows: document.querySelector("#start-with-windows"),
    open_at_startup: document.querySelector("#open-at-startup"),
    continue_in_tray: document.querySelector("#continue-in-tray"),
    preferred_port: document.querySelector("#preferred-port"),
    monitoring_enabled: document.querySelector("#monitoring-enabled"),
    start_monitoring_with_app: document.querySelector("#start-monitoring-with-app"),
    idle_threshold_minutes: document.querySelector("#idle-threshold-minutes"),
    sample_interval_seconds: document.querySelector("#sample-interval-seconds"),
    health_import_enabled: document.querySelector("#health-import-enabled"),
    health_import_poll_seconds: document.querySelector("#health-poll-seconds"),
    health_import_stability_seconds: document.querySelector("#health-stability-seconds"),
  };

  const setAvailable = (available) => {
    Object.values(fields).forEach((field) => { field.disabled = !available; });
    form.querySelectorAll("button").forEach((button) => { button.disabled = !available; });
    status.textContent = available ? "Aplicativo para Windows" : "Disponível apenas no aplicativo";
    status.classList.toggle("is-ready", available);
  };

  const request = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Não foi possível concluir a ação.");
    return payload;
  };

  const load = async () => {
    try {
      const settings = await request("/api/desktop/settings");
      Object.entries(fields).forEach(([name, field]) => {
        if (name === "idle_threshold_minutes") {
          field.value = Math.round(settings.idle_threshold_seconds / 60);
        } else if (field.type === "checkbox") field.checked = Boolean(settings[name]);
        else field.value = settings[name];
      });
      setAvailable(true);
      await loadHealthStatus();
    } catch (error) {
      setAvailable(false);
      feedback.textContent = error.message;
    }
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    feedback.textContent = "Salvando…";
    try {
      await request("/api/desktop/settings", {
        method: "PATCH",
        body: JSON.stringify({
          start_with_windows: fields.start_with_windows.checked,
          open_at_startup: fields.open_at_startup.checked,
          continue_in_tray: fields.continue_in_tray.checked,
          preferred_port: Number(fields.preferred_port.value),
        }),
      });
      await request("/api/computer-monitor/settings", {
        method: "PATCH",
        body: JSON.stringify({
          monitoring_enabled: fields.monitoring_enabled.checked,
          start_monitoring_with_app: fields.start_monitoring_with_app.checked,
          idle_threshold_seconds: Number(fields.idle_threshold_minutes.value) * 60,
          sample_interval_seconds: Number(fields.sample_interval_seconds.value),
        }),
      });
      await request("/api/health-import/settings", {
        method: "PATCH",
        body: JSON.stringify({
          health_import_enabled: fields.health_import_enabled.checked,
          health_import_poll_seconds: Number(fields.health_import_poll_seconds.value),
          health_import_stability_seconds: Number(fields.health_import_stability_seconds.value),
        }),
      });
      feedback.textContent = "Preferências salvas.";
      await loadHealthStatus();
    } catch (error) {
      feedback.textContent = error.message;
    }
  });

  const bindFolder = (selector, endpoint) => {
    document.querySelector(selector).addEventListener("click", async () => {
      feedback.textContent = "Abrindo pasta…";
      try {
        await request(endpoint, { method: "POST" });
        feedback.textContent = "";
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
  };

  bindFolder("#open-data-folder", "/api/desktop/open-data-folder");
  bindFolder("#open-logs-folder", "/api/desktop/open-logs-folder");

  const loadHealthStatus = async () => {
    try {
      const health = await request("/api/health-import/status");
      document.querySelector("#health-folder-label").textContent = health.folder_name
        ? `Pasta: ${health.folder_name}`
        : "Nenhuma pasta selecionada.";
      const labels = {
        connected: "conectado",
        importing: "importando",
        waiting_for_file: "aguardando arquivo",
        error: "erro",
        disabled: "desativado",
        unavailable: "indisponível",
      };
      document.querySelector("#health-import-status strong").textContent =
        `Status: ${labels[health.status] || health.status}`;
      document.querySelector("#health-import-details").textContent = [
        health.last_file ? `Último arquivo: ${health.last_file}` : null,
        health.last_import_at ? `Última importação: ${new Date(health.last_import_at).toLocaleString("pt-BR")}` : null,
        `Novos: ${health.imported_count}`,
        `Atualizados: ${health.updated_count}`,
        `Ignorados: ${health.skipped_count}`,
        health.recent_errors?.length ? `Erro recente: ${health.recent_errors.at(-1)}` : null,
      ].filter(Boolean).join(" · ");
    } catch (error) {
      document.querySelector("#health-import-status strong").textContent = "Status: indisponível";
    }
  };

  document.querySelector("#select-health-folder").addEventListener("click", async () => {
    feedback.textContent = "Aguardando seleção da pasta…";
    try {
      await request("/api/health-import/select-folder", { method: "POST" });
      feedback.textContent = "Pasta de saúde atualizada.";
      await loadHealthStatus();
    } catch (error) {
      feedback.textContent = error.message;
    }
  });

  document.querySelector("#health-import-now").addEventListener("click", async () => {
    feedback.textContent = "Importando dados de saúde…";
    try {
      const result = await request("/api/health-import/import-now", { method: "POST" });
      feedback.textContent = `Importação concluída: ${result.imported} novo(s), ${result.updated} atualizado(s), ${result.skipped} ignorado(s).`;
      await loadHealthStatus();
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
  document.querySelector("#clear-computer-data").addEventListener("click", async () => {
    if (!window.confirm("Excluir somente os dados de monitoramento do computador?")) return;
    feedback.textContent = "Limpando dados…";
    try {
      const payload = await request("/api/computer-monitor/clear-data", {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      });
      feedback.textContent = `${payload.deleted} bloco(s) removido(s).`;
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
  load();
})();
