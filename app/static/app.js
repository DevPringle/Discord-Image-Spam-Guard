(function () {
  function applyPresetButtons() {
    const presetField = document.getElementById("preset-field");
    const settingsForm = document.getElementById("settings-form");
    const presetButtons = document.querySelectorAll("[data-preset]");
    if (!presetButtons.length) return;

    presetButtons.forEach((button) => {
      button.addEventListener("click", function () {
        let values = {};
        try {
          values = JSON.parse(button.getAttribute("data-preset") || "{}");
        } catch (err) {
          values = {};
        }
        const presetName = button.getAttribute("data-preset-name") || "";
        if (presetField) presetField.value = presetName;

        Object.keys(values).forEach((key) => {
          const field = settingsForm ? settingsForm.querySelector(`[name="${key}"]`) : document.querySelector(`[name="${key}"]`);
          if (!field) return;
          if (field.type === "checkbox") {
            field.checked = !!values[key];
          } else {
            field.value = values[key];
          }
        });
      });
    });
  }

  function applyDropzones() {
    const dropzones = document.querySelectorAll(".dropzone");
    dropzones.forEach((dropzone) => {
      const inputId = dropzone.getAttribute("data-input");
      const previewId = dropzone.getAttribute("data-preview");
      const input = inputId ? document.getElementById(inputId) : null;
      const preview = previewId ? document.getElementById(previewId) : null;
      if (!input) return;

      const renderPreview = () => {
        if (!preview) return;
        const files = Array.from(input.files || []);
        preview.innerHTML = files.map((file) => `<div class="note-chip">${file.name}</div>`).join("");
      };

      dropzone.addEventListener("click", () => input.click());
      dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
      dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
      dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        const dt = e.dataTransfer;
        if (!dt || !dt.files || !dt.files.length) return;
        input.files = dt.files;
        renderPreview();
      });
      input.addEventListener("change", renderPreview);
    });
  }

  async function refreshBotStatus() {
    const pill = document.getElementById("bot-status-pill");
    const text = document.getElementById("bot-status-text");
    if (!pill || !text) return;
    try {
      const res = await fetch("/api/bot-status", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const online = !!data.fresh;
      pill.classList.toggle("status-online", online);
      text.textContent = online ? "Bot online" : "Bot offline";
    } catch (err) {}
  }

  async function refreshLiveSummary() {
    const totalDetections = document.getElementById("live-total-detections");
    const totalReferences = document.getElementById("live-total-references");
    if (!totalDetections && !totalReferences) return;
    try {
      const res = await fetch("/api/live-summary", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      if (totalDetections && typeof data.total_detections !== "undefined") totalDetections.textContent = data.total_detections;
      if (totalReferences && typeof data.total_reference_images !== "undefined") totalReferences.textContent = data.total_reference_images;
    } catch (err) {}
  }

  async function refreshLiveDetections() {
    const tbody = document.getElementById("live-detections-body");
    if (!tbody) return;
    try {
      const res = await fetch("/api/live-detections", { cache: "no-store" });
      if (!res.ok) return;
      const rows = await res.json();
      if (!Array.isArray(rows) || !rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="muted">Nothing yet.</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map((row) => {
        const deleted = row.deleted_message ? "yes" : "no";
        const score = typeof row.match_score !== "undefined" ? row.match_score : "";
        const method = row.match_method ? `${row.match_method} (${score})` : "";
        return `<tr>
          <td>${row.created_at || ""}</td>
          <td>${row.username || ""}</td>
          <td>${row.channel_name || ""}</td>
          <td>${row.matched_reference_label || ""}</td>
          <td>${method}</td>
          <td>${row.action_taken || ""}</td>
          <td>${deleted}</td>
        </tr>`;
      }).join("");
    } catch (err) {}
  }

  function boot() {
    applyPresetButtons();
    applyDropzones();
    refreshBotStatus();
    refreshLiveSummary();
    refreshLiveDetections();
    setInterval(refreshBotStatus, 2500);
    setInterval(refreshLiveSummary, 4000);
    setInterval(refreshLiveDetections, 5000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
