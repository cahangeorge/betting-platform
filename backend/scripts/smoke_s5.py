"""Sprint 5 smoke test — full API workout."""
import asyncio
import httpx

BASE = "http://localhost:8000/api/v1"

async def smoke():
    async with httpx.AsyncClient(base_url=BASE) as c:
        # 1. Register user
        r = await c.post("/auth/register", json={"email": "bot@test.com", "password": "testpass123"})
        print(f"1. REGISTER: {r.status_code}", end="")
        if r.status_code == 201:
            print(" USER CREATED")
        elif r.status_code == 409:
            print(" USER EXISTS (ok)")
        else:
            print(f" {r.text[:80]}")

        # 2. Login
        r = await c.post("/auth/login", json={"email": "bot@test.com", "password": "testpass123"})
        assert r.status_code == 200, f"login: {r.status_code}"
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"2. LOGIN: 200 TOKEN OK (first 12 chars: {token[:12]}...)")

        # 3. Health
        r = await c.get("http://localhost:8000/health")
        assert r.status_code == 200
        print(f"3. HEALTH: {r.json()}")

        # 4. Get /me
        r = await c.get("/auth/me", headers=headers)
        assert r.status_code == 200
        uid = r.json()["id"]
        print(f"4. /ME: user={uid}")

        # 5. Create match
        r = await c.post("/matches", headers=headers, json={
            "external_id": "smoke-001",
            "home_team": "Arsenal", "away_team": "Chelsea",
            "league": "Premier League", "sport": "football",
            "kickoff_time": "2026-06-03T15:00:00Z",
            "status": "live",
            "betfair_market_id": "1.234567",
            "smarkets_market_id": "mkt_abc123",
        })
        assert r.status_code == 201
        mid = r.json()["id"]
        print(f"5. MATCH CREATE: {r.status_code} match={mid[:8]}...")

        # 6. List matches
        r = await c.get("/matches?status=live")
        assert r.status_code == 200
        print(f"6. LIST MATCHES: {len(r.json())} live")

        # 7. Create bankroll
        r = await c.post("/bankroll", headers=headers, json={
            "name": "Paper Test", "currency": "GBP",
        })
        assert r.status_code == 201
        bid = r.json()["id"]
        print(f"7. BANKROLL CREATE: {r.status_code} id={bid[:8]}...")

        # 8. Bot status (idle)
        r = await c.get("/bot/status", params={"bankroll_id": bid}, headers=headers)
        assert r.status_code == 200
        d = r.json()
        print(f"8. BOT STATUS: running={d['running']} cycles={d['cycles']}")

        # 9. Bot start (paper, slow poll)
        r = await c.post("/bot/start", headers=headers, json={
            "bankroll_id": bid,
            "kelly_fraction": 0.5, "edge_threshold": 0.15,
            "poll_interval_seconds": 30.0, "paper": True,
            "exchange_whitelist": ["betfair"],
            "min_odds": 1.5, "max_odds": 20.0,
        })
        assert r.status_code == 200
        print(f"9. BOT START: {r.json()['status']}")

        # 10. Bot status (running)
        await asyncio.sleep(0.5)
        r = await c.get("/bot/status", params={"bankroll_id": bid}, headers=headers)
        assert r.status_code == 200
        print(f"10. BOT STATUS (running): running={r.json()['running']}")

        # 11. List trades (empty)
        r = await c.get("/bot/trades", params={"bankroll_id": bid}, headers=headers)
        assert r.status_code == 200
        print(f"11. TRADES: {len(r.json())} positions")

        # 12. Predict
        r = await c.post("/predictions/predict?model_key=poisson", headers=headers, json={
            "home_team": "Arsenal", "away_team": "Chelsea", "league": "Premier League",
        })
        assert r.status_code == 200
        p = r.json()
        print(f"12. PREDICT: {p['model_name']} H={p['home_win_prob'][:6]} D={p['draw_prob'][:6]} A={p['away_win_prob'][:6]}")

        # 13. Bot stop
        r = await c.post("/bot/stop", params={"bankroll_id": bid}, headers=headers)
        assert r.status_code == 200
        print(f"13. BOT STOP: {r.json()['status']}")

        # 14. Bot status (stopped)
        r = await c.get("/bot/status", params={"bankroll_id": bid}, headers=headers)
        assert r.status_code == 200
        print(f"14. BOT STATUS (stopped): running={r.json()['running']}")

        print("\n=== ALL 14 TESTS PASSED ===")


asyncio.run(smoke())