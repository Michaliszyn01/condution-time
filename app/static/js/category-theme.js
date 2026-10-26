document.addEventListener("DOMContentLoaded", () => {
  const dashboard = document.querySelector("[data-chart-theme]");
  const chart = window.studyWeeklyChart;

  if (!dashboard || !chart) {
    return;
  }

  const palettes = {
    purple: {
      current: "#7657f6",
      previous: "#ded5ff",
    },
    green: {
      current: "#22b573",
      previous: "#cfecdd",
    },
  };
  const palette = palettes[dashboard.dataset.chartTheme];

  if (!palette) {
    return;
  }

  const dataset = chart.data.datasets[0];
  dataset.backgroundColor = dataset.data.map((_, index) =>
    index === dataset.data.length - 1 ? palette.current : palette.previous
  );
  chart.update("none");
});
