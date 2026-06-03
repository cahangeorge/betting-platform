const API_BASE = "/api/v1";
function getToken() {
  return localStorage.getItem("bt_token");
}
async function _fetch(path, opts = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { "Content-Type": "application/json", ...opts.headers || {} };
  const t = getToken();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const r = await fetch(url, { ...opts, headers });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}
const api = {
  login: (email, password) => _fetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email, password) => _fetch("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => _fetch("/auth/me"),
  listMatches: (status) => _fetch(`/matches?${status ? "status=" + status : ""}`),
  getMatch: (id) => _fetch(`/matches/${id}`),
  listBankrolls: () => _fetch("/bankroll"),
  botStatus: (id) => _fetch(`/bot/status?bankroll_id=${id}`),
  botStart: (id, cfg) => _fetch("/bot/start", { method: "POST", body: JSON.stringify({ bankroll_id: id, ...cfg }) }),
  botStop: (id) => _fetch("/bot/stop", { method: "POST", body: JSON.stringify({ bankroll_id: id }) }),
  listTrades: (id, status) => _fetch(`/bot/trades?bankroll_id=${id}${status ? "&status=" + status : ""}`),
  momentum: (id) => _fetch(`/stats/momentum/${id}`),
  statHistory: (id) => _fetch(`/stats/history/${id}`),
  predict: (home, away) => _fetch("/predictions/predict?home_team=" + encodeURIComponent(home) + "&away_team=" + encodeURIComponent(away)),
  importCsv: () => _fetch("/training/import-csv", { method: "POST" }),
  fitModel: () => _fetch("/training/fit", { method: "POST" }),
  fitAndEval: () => _fetch("/training/fit-and-eval", { method: "POST" }),
  expandCsv: (seasons) => _fetch("/data/expand-csv?seasons=" + encodeURIComponent(seasons), { method: "POST" }),
  ingesterStatus: () => _fetch("/data/ingester/status"),
  ingesterStart: () => _fetch("/data/ingester/start", { method: "POST" }),
  ingesterStop: () => _fetch("/data/ingester/stop", { method: "POST" }),
  paperSettle: (id, result) => _fetch("/bot/paper/settle", { method: "POST", body: JSON.stringify({ trade_id: id, result }) })
};
export {
  api as a
};
