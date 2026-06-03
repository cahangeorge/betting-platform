const API_BASE = "/api/v1";
let _token = null;
function setToken(t) {
  _token = t;
  localStorage.removeItem("bt_token");
}
function getToken() {
  if (!_token) _token = localStorage.getItem("bt_token");
  return _token;
}
async function request(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : void 0
  });
  if (res.status === 401) {
    setToken(null);
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}
const api = {
  // Auth
  login: (email, password) => request("POST", "/auth/login", { email, password }),
  register: (email, password) => request("POST", "/auth/register", { email, password }),
  // Me
  me: () => request("GET", "/auth/me"),
  // Matches
  listMatches: (status) => request("GET", `/matches${status ? `?status=${status}` : ""}`),
  // Bankroll
  listBankrolls: () => request("GET", "/bankroll"),
  createBankroll: (name, currency = "GBP") => request("POST", "/bankroll", { name, currency }),
  // Bot
  botStatus: (bankrollId) => request("GET", `/bot/status?bankroll_id=${bankrollId}`),
  botStart: (bankrollId, opts) => request("POST", "/bot/start", { bankroll_id: bankrollId, paper: true, ...opts }),
  botStop: (bankrollId) => request("POST", `/bot/stop?bankroll_id=${bankrollId}`),
  // Trades
  listTrades: (bankrollId, status) => request("GET", `/bot/trades?bankroll_id=${bankrollId}${status ? `&status=${status}` : ""}`),
  // Stats / momentum
  momentum: (matchId) => request("GET", `/stats/momentum/${matchId}`),
  statHistory: (matchId) => request("GET", `/stats/history/${matchId}`),
  // Predictions
  predict: (homeTeam, awayTeam, league = "PL", model = "poisson") => request("POST", `/predictions/predict?model_key=${model}`, { home_team: homeTeam, away_team: awayTeam, league }),
  // Training
  importCsv: () => request("POST", "/training/import-csv"),
  fitModel: (league) => request("POST", `/training/fit${league ? `?league=${league}` : ""}`),
  fitAndEval: () => request("POST", "/training/fit-and-eval"),
  // Data
  expandCsv: (seasons = "2024") => request("POST", `/data/expand-csv?seasons=${seasons}`),
  ingesterStatus: () => request("GET", "/data/ingester/status"),
  ingesterStart: () => request("POST", "/data/ingester/start"),
  ingesterStop: () => request("POST", "/data/ingester/stop")
};
export {
  api as a
};
