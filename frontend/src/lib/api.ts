/** Backend API client for the betting platform. */
const API_BASE = '/api/v1';

let _token: string | null = null;

export function setToken(t: string | null) { _token = t; if (t) localStorage.setItem('bt_token', t); else localStorage.removeItem('bt_token'); }
export function getToken(): string | null { if (!_token) _token = localStorage.getItem('bt_token'); return _token; }

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
    });

    if (res.status === 401) { setToken(null); throw new Error('Unauthorized'); }
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
    }
    return res.json();
}

export const api = {
    // Auth
    login: (email: string, password: string) =>
        request<{ access_token: string }>('POST', '/auth/login', { email, password }),
    register: (email: string, password: string) =>
        request<{ id: string }>('POST', '/auth/register', { email, password }),

    // Me
    me: () => request<{ id: string; email: string }>('GET', '/auth/me'),

    // Matches
    listMatches: (status?: string) =>
        request<Array<Record<string, unknown>>>('GET', `/matches${status ? `?status=${status}` : ''}`),

    // Bankroll
    listBankrolls: () =>
        request<Array<Record<string, unknown>>>('GET', '/bankroll'),
    createBankroll: (name: string, currency = 'GBP') =>
        request<Record<string, unknown>>('POST', '/bankroll', { name, currency }),

    // Bot
    botStatus: (bankrollId: string) =>
        request<{ running: boolean; cycles: number; orders_placed: number; paper: boolean }>('GET', `/bot/status?bankroll_id=${bankrollId}`),
    botStart: (bankrollId: string, opts?: Record<string, unknown>) =>
        request<Record<string, unknown>>('POST', '/bot/start', { bankroll_id: bankrollId, paper: true, ...opts }),
    botStop: (bankrollId: string) =>
        request<Record<string, unknown>>('POST', `/bot/stop?bankroll_id=${bankrollId}`),

    // Trades
    listTrades: (bankrollId: string, status?: string) =>
        request<Array<Record<string, unknown>>>('GET', `/bot/trades?bankroll_id=${bankrollId}${status ? `&status=${status}` : ''}`),

    // Stats / momentum
    momentum: (matchId: string) =>
        request<Record<string, unknown>>('GET', `/stats/momentum/${matchId}`),
    statHistory: (matchId: string) =>
        request<Array<Record<string, unknown>>>('GET', `/stats/history/${matchId}`),

    // Predictions
    predict: (homeTeam: string, awayTeam: string, league = 'PL', model = 'poisson') =>
        request<Record<string, unknown>>('POST', `/predictions/predict?model_key=${model}`, { home_team: homeTeam, away_team: awayTeam, league }),

    // Training
    importCsv: () => request<Record<string, unknown>>('POST', '/training/import-csv'),
    fitModel: (league?: string) => request<Record<string, unknown>>('POST', `/training/fit${league ? `?league=${league}` : ''}`),
    fitAndEval: () => request<Record<string, unknown>>('POST', '/training/fit-and-eval'),

    // Data
    expandCsv: (seasons = '2024') => request<Record<string, unknown>>('POST', `/data/expand-csv?seasons=${seasons}`),
    ingesterStatus: () => request<Record<string, unknown>>('GET', '/data/ingester/status'),
    ingesterStart: () => request<Record<string, unknown>>('POST', '/data/ingester/start'),
    ingesterStop: () => request<Record<string, unknown>>('POST', '/data/ingester/stop'),
};
