// Общие утилиты для всех страниц.
window.App = (function () {
  function getToken() {
    return localStorage.getItem("token");
  }

  function setToken(token) {
    localStorage.setItem("token", token);
  }

  function clearToken() {
    localStorage.removeItem("token");
  }

  async function api(path, options = {}) {
    const headers = Object.assign(
      { "Accept": "application/json" },
      options.headers || {}
    );
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    const response = await fetch(path, Object.assign({}, options, { headers }));

    if (response.status === 401) {
      // токен истёк или отсутствует — отправляем на логин
      window.location.href = "/static/login.html";
      throw new Error("Unauthorized");
    }
    return response;
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) return "—";
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString("ru-RU");
  }

  function fmtDateTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString("ru-RU");
  }

  function statusBadge(status) {
    const cls = ["active", "cancelled", "free", "booked"].includes(status)
      ? status
      : "";
    return `<span class="status ${cls}">${escapeHtml(status)}</span>`;
  }

  function renderNav(active) {
    const items = [
      ["appointments.html", "Записи"],
      ["summary.html", "Сводка"],
    ];
    const links = items
      .map(([href, label]) => {
        const cls = href === active ? "nav-link active" : "nav-link";
        return `<a class="${cls}" href="/static/${href}">${label}</a>`;
      })
      .join("");

    return `<nav class="topnav">
      <span class="brand">Сервис записи</span>
      ${links}
      <a class="nav-link logout" href="#" id="logout">Выйти</a>
    </nav>`;
  }

  function mountNav(active) {
    const holder = document.getElementById("nav");
    if (!holder) return;
    holder.innerHTML = renderNav(active);
    const logout = document.getElementById("logout");
    if (logout) {
      logout.addEventListener("click", (e) => {
        e.preventDefault();
        clearToken();
        window.location.href = "/static/login.html";
      });
    }
  }

  return {
    getToken, setToken, clearToken,
    api, escapeHtml, fmtDate, fmtDateTime,
    statusBadge, mountNav,
  };
})();