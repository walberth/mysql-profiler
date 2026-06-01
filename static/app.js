(() => {
  const body = document.body;
  const apiUrl = body.dataset.apiUrl;
  const refreshMs = Number(body.dataset.refreshMs || 2000);
  const maxEntries = Number(body.dataset.maxLogEntries || 500);

  const logsEl = document.getElementById("logs");
  const statusEl = document.getElementById("status-value");
  const summaryEl = document.getElementById("summary-bar");
  const filterEl = document.getElementById("filter-input");
  const limitEl = document.getElementById("limit-input");
  const toggleEl = document.getElementById("toggle-scroll");

  let autoScroll = true;

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function currentLimit() {
    const rawValue = Number(limitEl.value || maxEntries);
    if (!Number.isFinite(rawValue)) {
      return maxEntries;
    }
    return Math.max(20, Math.min(rawValue, maxEntries));
  }

  function filteredEntries(entries) {
    const needle = filterEl.value.trim().toLowerCase();
    if (!needle) {
      return entries;
    }
    return entries.filter((entry) =>
      String(entry.argument).toLowerCase().includes(needle),
    );
  }

  function render(data) {
    const entries = filteredEntries(data.entries || [])
      .slice()
      .reverse();
    const state = data.state || {};
    const connected = Boolean(state.connected);

    statusEl.textContent = connected ? "Conectado" : "Con errores";
    statusEl.classList.toggle("status-ok", connected);
    statusEl.classList.toggle("status-error", !connected);

    const lastPoll = state.last_poll || "sin sondeos";
    const lastError = state.last_error ? ` | Error: ${state.last_error}` : "";
    summaryEl.textContent = `${entries.length} visibles de ${(data.entries || []).length} en buffer | Último sondeo: ${lastPoll}${lastError}`;

    if (!entries.length) {
      logsEl.innerHTML =
        '<div class="log-empty">No hay consultas que coincidan con el filtro actual.</div>';
      return;
    }

    logsEl.innerHTML = entries
      .map(
        (entry) => `
            <article class="log-entry">
                <div class="entry-time">${escapeHtml(entry.event_time)}</div>
                <pre class="entry-query">${escapeHtml(entry.argument)}</pre>
            </article>
        `,
      )
      .join("");

    if (autoScroll) {
      logsEl.scrollTop = 0;
    }
  }

  async function refresh() {
    try {
      const response = await fetch(
        `${apiUrl}?limit=${encodeURIComponent(currentLimit())}`,
        {
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
          },
        },
      );

      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      render(data);
    } catch (error) {
      summaryEl.textContent = `No se pudo cargar la API de logs: ${error}`;
      statusEl.textContent = "Sin respuesta";
      statusEl.classList.remove("status-ok");
      statusEl.classList.add("status-error");
    }
  }

  toggleEl.addEventListener("click", () => {
    autoScroll = !autoScroll;
    toggleEl.textContent = `Auto-scroll ${autoScroll ? "ON" : "OFF"}`;
  });

  filterEl.addEventListener("input", refresh);
  limitEl.addEventListener("change", refresh);
  limitEl.addEventListener("blur", refresh);

  refresh();
  window.setInterval(refresh, refreshMs);
})();
