document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.querySelector("#study-weekly-chart");
  const dataElement = document.querySelector("#study-weekly-chart-data");

  if (!canvas || !dataElement || !window.Chart) {
    return;
  }

  const chartData = JSON.parse(dataElement.textContent);
  const barColors = chartData.values.map((_, index) =>
    index === chartData.values.length - 1 ? "#246bfd" : "#cbdcff"
  );
  const datasets = chartData.datasets?.length
    ? chartData.datasets.map((dataset) => ({
        ...dataset,
        borderRadius: 5,
        borderSkipped: false,
        maxBarThickness: 38
      }))
    : [
        {
          data: chartData.values,
          backgroundColor: barColors,
          borderRadius: 8,
          borderSkipped: false,
          maxBarThickness: 38
        }
      ];

  window.studyWeeklyChart = new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: chartData.labels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 450,
      },
      plugins: {
        legend: {
          display: Boolean(chartData.datasets?.length),
          labels: {usePointStyle: true, boxWidth: 8},
        },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (items) => {
              const detail = chartData.details?.[items[0]?.dataIndex];
              return detail?.date_label || "";
            },
            label: (context) => chartData.datasets?.length
              ? `${context.dataset.label}: ${context.raw} min`
              : `${context.raw} pontos`,
            afterLabel: (context) => {
              if (chartData.datasets?.length) {
                const count = context.dataset.sessionCounts?.[context.dataIndex] || 0;
                const origins = context.dataset.origins?.[context.dataIndex] || [];
                const sessionLabel = count === 1 ? "sessão" : "sessões";
                return [
                  `${count} ${sessionLabel}`,
                  origins.length ? `Origem: ${origins.join(", ")}` : ""
                ].filter(Boolean);
              }
              const detail = chartData.details?.[context.dataIndex];
              if (!detail) return "";
              return detail.tooltip_lines || `${detail.duration} estudados`;
            },
          },
        },
      },
      scales: {
        x: {
          stacked: Boolean(chartData.datasets?.length),
          border: {
            display: false,
          },
          grid: {
            display: false,
          },
          ticks: {
            color: "#98a2b3",
            font: {
              family: "Inter",
              size: 11,
              weight: 600,
            },
          },
        },
        y: {
          stacked: Boolean(chartData.datasets?.length),
          beginAtZero: true,
          suggestedMax: 100,
          display: false,
          grid: {
            display: false,
          },
        },
      },
    },
  });
});
