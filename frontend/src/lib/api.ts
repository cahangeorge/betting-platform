/** Backend API client for the betting platform. */
const API_BASE = '/api/v1';

let _token: string | null = null;

export function setToken(t: string | null) { _token = t; if (t) localStorage.setItem('bt_token', t); else localStorage.removeItem('bt_token'); }
export function getToken() { return localStorage.getItem('bt_token'); }

async function _fetch(path: string, opts: RequestInit = {}) {
    const url = `${API_BASE}${path}`;
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...opts.headers as Record<string, string> || {} };
    const t = _token || getToken();
    if (t) headers['Authorization'] = `Bearer ${t}`;
    const r = await fetch(url, { ...opts, headers });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    return r.json();
}

export const api = {
    login: (email: string, password: string) => _fetch('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
    register: (email: string, password: string) => _fetch('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
    me: () => _fetch('/auth/me'),
    listMatches: (status?: string) => _fetch(`/matches?${status ? 'status=' + status : ''}`),
    getMatch: (id: string) => _fetch(`/matches/${id}`),
    listBankrolls: () => _fetch('/bankroll'),
    botStatus: (id: string) => _fetch(`/bot/status?bankroll_id=${id}`),
    botStart: (id: string, cfg: object) => _fetch('/bot/start', { method: 'POST', body: JSON.stringify({ bankroll_id: id, ...cfg }) }),
    botStop: (id: string) => _fetch('/bot/stop', { method: 'POST', body: JSON.stringify({ bankroll_id: id }) }),
    listTrades: (id: string, status?: string) => _fetch(`/bot/trades?bankroll_id=${id}${status ? '&status=' + status : ''}`),
    momentum: (id: string) => _fetch(`/stats/momentum/${id}`),
    statHistory: (id: string) => _fetch(`/stats/history/${id}`),
    predict: (home: string, away: string) => _fetch('/predictions/predict?home_team=' + encodeURIComponent(home) + '&away_team=' + encodeURIComponent(away)),
    importCsv: () => _fetch('/training/import-csv', { method: 'POST' }),
    fitModel: () => _fetch('/training/fit', { method: 'POST' }),
    fitAndEval: () => _fetch('/training/fit-and-eval', { method: 'POST' }),
    expandCsv: (seasons: string) => _fetch('/data/expand-csv?seasons=' + encodeURIComponent(seasons), { method: 'POST' }),
    ingesterStatus: () => _fetch('/data/ingester/status'),
    ingesterStart: () => _fetch('/data/ingester/start', { method: 'POST' }),
    ingesterStop: () => _fetch('/data/ingester/stop', { method: 'POST' }),
    paperSettle: (id: string, result: string) => _fetch('/bot/paper/settle', { method: 'POST', body: JSON.stringify({ trade_id: id, result }) }),
};
