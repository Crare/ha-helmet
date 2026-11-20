/*
 * Dashboard cards for the Helmet library loans integration.
 * Loaded automatically by the integration; both cards appear in
 * Edit dashboard → Add card. They find every Helmet library card themselves.
 *
 *   type: custom:helmet-loans-card          # optional: title
 *   type: custom:helmet-reservations-card   # optional: title
 */

const TEXT = {
  en: {
    loans: "Library loans",
    reservations: "Library reservations",
    title: "Title",
    due: "Due",
    status: "Status",
    noLoans: "No loans",
    noReservations: "No reservations",
    noCards: "No Helmet library cards found. Add one under Settings → Devices & services.",
    overdue: "overdue",
    today: "today",
    days: (d) => `${d} d`,
    ready: "Ready",
    pickupBy: (d) => `pick up by ${d}`,
    queue: "In queue",
  },
  fi: {
    loans: "Kirjaston lainat",
    reservations: "Kirjaston varaukset",
    title: "Nimeke",
    due: "Eräpäivä",
    status: "Tila",
    noLoans: "Ei lainoja",
    noReservations: "Ei varauksia",
    noCards: "Helmet-kirjastokortteja ei löytynyt. Lisää kortti kohdassa Asetukset → Laitteet ja palvelut.",
    overdue: "myöhässä",
    today: "tänään",
    days: (d) => `${d} pv`,
    ready: "Noudettavissa",
    pickupBy: (d) => `nouda viim. ${d}`,
    queue: "Jonossa",
  },
};

const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

/** "2026-11-22" → local Date at midnight, or null. */
const parseDate = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
};

const daysFromToday = (date) => {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((date - today) / 86400000);
};

const shortDate = (date, withYear) =>
  `${date.getDate()}.${date.getMonth() + 1}.${withYear ? date.getFullYear() : ""}`;

const STYLE = `
  .content { padding: 0 16px 16px; }
  .empty { color: var(--secondary-text-color); padding: 4px 0 8px; }
  h3 { font-size: 1.05em; font-weight: 500; margin: 12px 0 6px; }
  h3 .count { color: var(--secondary-text-color); font-weight: 400; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-weight: 500; color: var(--secondary-text-color);
       font-size: 0.85em; padding: 4px 8px 4px 0; border-bottom: 1px solid var(--divider-color); }
  td { padding: 6px 8px 6px 0; border-bottom: 1px solid var(--divider-color); vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  td.when { white-space: nowrap; }
  td.left { white-space: nowrap; text-align: right; padding-right: 0; color: var(--secondary-text-color); }
  .soon { color: var(--warning-color, #ff9800); font-weight: 500; }
  .late { color: var(--error-color, #db4437); font-weight: 500; }
  .ready { color: var(--success-color, #43a047); font-weight: 500; }
  .queue { color: var(--secondary-text-color); }
`;

class HelmetBaseCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._key = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig() {
    return {};
  }

  get _text() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return TEXT[lang] || TEXT.en;
  }

  /** Helmet sensors carrying `attr`, with a display name per library card. */
  _sensors(attr, accept) {
    const hass = this._hass;
    return Object.values(hass.states)
      .filter((s) => s.entity_id.startsWith("sensor.") && Array.isArray(s.attributes[attr]))
      .filter((s) => {
        const entry = hass.entities?.[s.entity_id];
        return (!entry || entry.platform === "helmet") && accept(s);
      })
      .map((s) => {
        const entry = hass.entities?.[s.entity_id];
        const device = entry?.device_id ? hass.devices?.[entry.device_id] : undefined;
        const name = device?.name_by_user || device?.name || s.attributes.friendly_name || s.entity_id;
        return { state: s, name, items: s.attributes[attr] };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _render() {
    if (!this._hass || !this._config) return;
    const sensors = this._findSensors();
    // Re-render only when the data or language changed, not on every state update.
    const key = JSON.stringify([this._text.title, this._config, sensors.map((s) => [s.name, s.state.last_updated])]);
    if (key === this._key) return;
    this._key = key;

    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const t = this._text;
    const title = this._config.title ?? this._defaultTitle(t);
    const body = sensors.length
      ? sensors.map((s) => this._section(s, t)).join("")
      : `<div class="empty">${escapeHtml(t.noCards)}</div>`;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card header="${escapeHtml(title)}">
        <div class="content">${body}</div>
      </ha-card>`;
  }

  _heading(sensor) {
    return `<h3>${escapeHtml(sensor.name)} <span class="count">(${sensor.items.length})</span></h3>`;
  }
}

class HelmetLoansCard extends HelmetBaseCard {
  _defaultTitle(t) {
    return t.loans;
  }

  _findSensors() {
    return this._sensors("loans", () => true);
  }

  _section(sensor, t) {
    if (!sensor.items.length) return `${this._heading(sensor)}<div class="empty">${escapeHtml(t.noLoans)}</div>`;
    const rows = sensor.items
      .map((loan) => {
        const due = parseDate(loan.due_date);
        if (!due) return `<tr><td>${escapeHtml(loan.title)}</td><td class="when">–</td><td></td></tr>`;
        const days = daysFromToday(due);
        const [cls, label] =
          days < 0 ? ["late", t.overdue] : days === 0 ? ["soon", t.today] : [days <= 3 ? "soon" : "", t.days(days)];
        return `<tr><td>${escapeHtml(loan.title)}</td>
          <td class="when ${cls}">${shortDate(due, true)}</td>
          <td class="left ${cls}">${escapeHtml(label)}</td></tr>`;
      })
      .join("");
    return `${this._heading(sensor)}
      <table><thead><tr><th>${escapeHtml(t.title)}</th><th>${escapeHtml(t.due)}</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }
}

class HelmetReservationsCard extends HelmetBaseCard {
  _defaultTitle(t) {
    return t.reservations;
  }

  _findSensors() {
    // The "Ready for pickup" sensor also has `holds`, but only ready ones and a `waiting` count.
    return this._sensors("holds", (s) => s.attributes.waiting === undefined);
  }

  _section(sensor, t) {
    if (!sensor.items.length) return `${this._heading(sensor)}<div class="empty">${escapeHtml(t.noReservations)}</div>`;
    const rows = sensor.items
      .map((hold) => {
        if (!hold.ready) {
          return `<tr><td>${escapeHtml(hold.title)}</td><td class="queue">⏳ ${escapeHtml(t.queue)}</td></tr>`;
        }
        const by = parseDate(hold.pickup_by);
        const status = by ? `${t.ready}, ${t.pickupBy(shortDate(by, false))}` : t.ready;
        return `<tr><td><b>${escapeHtml(hold.title)}</b></td><td class="ready">📚 ${escapeHtml(status)}</td></tr>`;
      })
      .join("");
    return `${this._heading(sensor)}
      <table><thead><tr><th>${escapeHtml(t.title)}</th><th>${escapeHtml(t.status)}</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }
}

if (!customElements.get("helmet-loans-card")) {
  customElements.define("helmet-loans-card", HelmetLoansCard);
  customElements.define("helmet-reservations-card", HelmetReservationsCard);
  window.customCards = window.customCards || [];
  window.customCards.push(
    {
      type: "helmet-loans-card",
      name: "Helmet loans",
      description: "Loans of every Helmet library card, with due dates.",
      preview: true,
      documentationURL: "https://github.com/Crare/ha-helmet",
    },
    {
      type: "helmet-reservations-card",
      name: "Helmet reservations",
      description: "Reservations of every Helmet library card; ready ones first with the last pickup day.",
      preview: true,
      documentationURL: "https://github.com/Crare/ha-helmet",
    },
  );
}
