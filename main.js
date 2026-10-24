const bynFormatter = new Intl.NumberFormat("ru-BY", {
  style: "currency",
  currency: "BYN",
  maximumFractionDigits: 2
});

const formatBYN = value => bynFormatter.format(Number(value) || 0);

const themeToggle = document.getElementById("themeToggle");
const hamburger = document.getElementById("hamburger");
const nav = document.getElementById("nav");

if (localStorage.getItem("theme") === "dark") {
  document.body.classList.add("dark");
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("theme", document.body.classList.contains("dark") ? "dark" : "light");
  });
}

if (hamburger && nav) {
  hamburger.addEventListener("click", () => nav.classList.toggle("open"));
}

const modal = document.getElementById("expenseModal");
const form = document.getElementById("expenseForm");
const modalTitle = document.getElementById("modalTitle");
const formError = document.getElementById("formError");
let editingId = null;

function openModal(expense = null) {
  if (!modal) return;

  editingId = expense ? Number(expense.id) : null;
  modalTitle.textContent = expense ? "Редактировать расход" : "Новый расход";

  document.getElementById("amount").value = expense ? expense.amount : "";
  document.getElementById("category").value = expense
    ? expense.category
    : document.getElementById("category").options[0].value;
  document.getElementById("date").value = expense
    ? expense.date
    : new Date().toISOString().slice(0, 10);
  document.getElementById("comment").value = expense ? expense.comment : "";

  formError.classList.add("hidden");
  modal.classList.remove("hidden");
}

function closeModal() {
  if (!modal) return;
  modal.classList.add("hidden");
  editingId = null;
  form.reset();
}

if (modal) {
  document.getElementById("addExpenseBtn").addEventListener("click", () => openModal());
  document.getElementById("closeModal").addEventListener("click", closeModal);
  document.getElementById("cancelModal").addEventListener("click", closeModal);

  modal.addEventListener("click", event => {
    if (event.target === modal) closeModal();
  });

  document.querySelectorAll(".edit").forEach(button => {
    button.addEventListener("click", () => openModal(button.dataset));
  });

  document.querySelectorAll(".delete").forEach(button => {
    button.addEventListener("click", async () => {
      if (!confirm("Удалить расход?")) return;

      const response = await fetch(`/api/expenses/${button.dataset.id}`, {
        method: "DELETE"
      });

      if (response.ok) location.reload();
    });
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();

    const payload = {
      amount: Number(document.getElementById("amount").value),
      category: document.getElementById("category").value,
      date: document.getElementById("date").value,
      comment: document.getElementById("comment").value
    };

    const url = editingId ? `/api/expenses/${editingId}` : "/api/expenses";

    const response = await fetch(url, {
      method: editingId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const data = await response.json();
      formError.textContent = data.error || "Ошибка сохранения";
      formError.classList.remove("hidden");
      return;
    }

    location.reload();
  });
}

function renderStat(title, value, hint = "") {
  return `
    <div class="stat">
      <small>${title}</small>
      <strong>${value}</strong>
      ${hint ? `<span>${hint}</span>` : ""}
    </div>
  `;
}

function renderListItem(item, value) {
  return `
    <div class="list-item">
      <div class="list-icon" style="background:${item.color}22;color:${item.color}">
        <i class="fa-solid ${item.icon}"></i>
      </div>
      <div>
        <div class="title">${item.comment || item.category_name}</div>
        <div class="meta">${item.category_name} · ${item.date}</div>
      </div>
      <div class="value">${value}</div>
    </div>
  `;
}

function destroyChart(id) {
  const chart = Chart.getChart(id);
  if (chart) chart.destroy();
}

async function loadStats() {
  const statsElement = document.getElementById("stats");
  const analyticsStatsElement = document.getElementById("analyticsStats");

  if (!statsElement && !analyticsStatsElement) return;

  const response = await fetch("/api/stats");
  const stats = await response.json();
  const hasData = stats.byMonth.length > 0 || stats.recent.length > 0;

  if (window.pageType === "dashboard") {
    document.getElementById("emptyDashboard").classList.toggle("hidden", hasData);
    document.getElementById("dashboardContent").classList.toggle("hidden", !hasData);

    if (!hasData) return;

    statsElement.innerHTML = [
      renderStat("Расходы за месяц", formatBYN(stats.currentMonthTotal)),
      renderStat("Средний расход в день", formatBYN(stats.averagePerDay)),
      renderStat("Самая затратная категория", stats.topCategory || "—"),
      renderStat(
        "Сравнение с прошлым месяцем",
        `${stats.changePercent > 0 ? "+" : ""}${stats.changePercent}%`,
        `Прошлый месяц: ${formatBYN(stats.previousMonthTotal)}`
      )
    ].join("");

    document.getElementById("recentList").innerHTML = stats.recent
      .map(item => renderListItem(item, formatBYN(item.amount)))
      .join("");

    destroyChart("categoryChart");
    new Chart(document.getElementById("categoryChart"), {
      type: "doughnut",
      data: {
        labels: stats.byCategory.map(item => item.name),
        datasets: [{
          data: stats.byCategory.map(item => item.total),
          backgroundColor: stats.byCategory.map(item => item.color)
        }]
      },
      options: {
        plugins: {
          tooltip: {
            callbacks: {
              label: context => `${context.label}: ${formatBYN(context.raw)}`
            }
          }
        }
      }
    });

    destroyChart("dailyChart");
    new Chart(document.getElementById("dailyChart"), {
      type: "bar",
      data: {
        labels: stats.byDay.map(item => item.date.slice(5)),
        datasets: [{
          label: "Расходы",
          data: stats.byDay.map(item => item.total),
          backgroundColor: "#4f46e5",
          borderRadius: 6
        }]
      },
      options: {
        plugins: {
          tooltip: { callbacks: { label: context => formatBYN(context.raw) } }
        },
        scales: {
          y: { ticks: { callback: value => formatBYN(value) } }
        }
      }
    });

    destroyChart("monthlyChart");
    new Chart(document.getElementById("monthlyChart"), {
      type: "line",
      data: {
        labels: stats.byMonth.map(item => item.month),
        datasets: [{
          label: "Расходы",
          data: stats.byMonth.map(item => item.total),
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, .15)",
          fill: true,
          tension: .35
        }]
      },
      options: {
        plugins: {
          tooltip: { callbacks: { label: context => formatBYN(context.raw) } }
        },
        scales: {
          y: { ticks: { callback: value => formatBYN(value) } }
        }
      }
    });
  }

  if (window.pageType === "analytics") {
    document.getElementById("emptyAnalytics").classList.toggle("hidden", hasData);
    document.getElementById("analyticsContent").classList.toggle("hidden", !hasData);

    if (!hasData) return;

    analyticsStatsElement.innerHTML = [
      renderStat("Расходы в текущем месяце", formatBYN(stats.currentMonthTotal)),
      renderStat("Средний расход в день", formatBYN(stats.averagePerDay)),
      renderStat("Прогноз до конца месяца", formatBYN(stats.forecast), "На основе текущего темпа")
    ].join("");

    document.getElementById("topExpenses").innerHTML = stats.topExpenses
      .map(item => renderListItem(item, formatBYN(item.amount)))
      .join("");

    document.getElementById("averageCheck").innerHTML = stats.averageCheck
      .map(item => `
        <div class="list-item">
          <div class="title">${item.category}</div>
          <div class="meta">${item.count} операций</div>
          <div class="value">${formatBYN(item.average)}</div>
        </div>
      `)
      .join("");

    destroyChart("analyticsMonthlyChart");
    new Chart(document.getElementById("analyticsMonthlyChart"), {
      type: "bar",
      data: {
        labels: stats.byMonth.map(item => item.month),
        datasets: [{
          label: "Расходы",
          data: stats.byMonth.map(item => item.total),
          backgroundColor: "#8b5cf6",
          borderRadius: 6
        }]
      },
      options: {
        plugins: {
          tooltip: { callbacks: { label: context => formatBYN(context.raw) } }
        },
        scales: {
          y: { ticks: { callback: value => formatBYN(value) } }
        }
      }
    });
  }
}

loadStats();
