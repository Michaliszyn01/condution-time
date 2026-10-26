document.addEventListener("DOMContentLoaded", () => {
  const rulesCard = document.querySelector("#application-rules");
  const feedback = document.querySelector("#computer-feedback");
  if (!rulesCard) return;

  const request = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Não foi possível concluir a ação.");
    return payload;
  };

  const toggle = document.querySelector('a[href="#computer-monitor-toggle"]');
  if (toggle) {
    toggle.addEventListener("click", async (event) => {
      event.preventDefault();
      const status = rulesCard.dataset.monitorStatus;
      const action = status === "running" ? "pause" : status === "paused" ? "resume" : "start";
      try {
        const payload = await request(`/api/computer-monitor/${action}`, { method: "POST" });
        rulesCard.dataset.monitorStatus = payload.monitor.status;
        feedback.textContent = payload.monitor.status === "running"
          ? "Monitoramento ativo."
          : payload.monitor.status === "paused"
            ? "Monitoramento pausado."
            : "Monitoramento desligado.";
        window.setTimeout(() => window.location.reload(), 350);
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
  }

  document.querySelectorAll(".computer-rule-save").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest(".computer-rule-row");
      const ruleId = row.dataset.ruleId;
      const payload = {
        executable_name: row.dataset.executable,
        friendly_name: row.querySelector("strong").textContent.trim(),
        classification: row.querySelector(".computer-rule-classification").value,
        category: row.querySelector(".computer-rule-category").value,
        enabled: true,
        priority: 100,
      };
      try {
        const result = await request(
          ruleId ? `/api/computer-monitor/rules/${ruleId}` : "/api/computer-monitor/rules",
          {
            method: ruleId ? "PATCH" : "POST",
            body: JSON.stringify(payload),
          },
        );
        row.dataset.ruleId = result.rule.id;
        feedback.textContent = "Regra salva. Ela será usada nos próximos blocos.";
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
  });

  const projectForm = document.querySelector("#project-rule-form");
  if (projectForm) {
    projectForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(projectForm);
      try {
        await request("/api/computer-monitor/projects", {
          method: "POST",
          body: JSON.stringify({
            display_name: data.get("display_name"),
            match_terms: String(data.get("match_terms"))
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            classification: "productive",
            category: "programming",
          }),
        });
        window.location.reload();
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
  }

  document.querySelectorAll(".computer-project-delete").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest("[data-project-id]");
      try {
        await request(`/api/computer-monitor/projects/${row.dataset.projectId}`, {
          method: "DELETE",
        });
        row.remove();
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
  });
});
