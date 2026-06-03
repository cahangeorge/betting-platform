"""Sprint 7 smoke test — training pipeline."""
import asyncio
import httpx

BASE = "http://localhost:8000/api/v1"

async def smoke():
    async with httpx.AsyncClient(base_url=BASE) as c:
        r = await c.post("/auth/register", json={"email": "train@test.com", "password": "testpass123"})
        print(f"1. REGISTER: {r.status_code}", end="")
        if r.status_code in (201, 409): print(" OK")
        else: return

        r = await c.post("/auth/login", json={"email": "train@test.com", "password": "testpass123"})
        assert r.status_code == 200
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("2. LOGIN: 200")

        r = await c.post("/training/import-csv", headers=h)
        print(f"3. IMPORT CSV: {r.status_code} {r.json()}")

        r = await c.post("/training/fit", headers=h)
        print(f"4. FIT: {r.status_code} {r.json()}")

        r = await c.post("/predictions/predict?model_key=poisson", headers=h, json={
            "home_team": "Arsenal", "away_team": "Chelsea", "league": "PL",
        })
        d = r.json()
        print(f"5. PREDICT: {d['model_name']} H={d['home_win_prob'][:6]} D={d['draw_prob'][:6]} A={d['away_win_prob'][:6]}")

        is_real = d['home_win_prob'] not in ("0.3333", "0.333333")
        print(f"6. TRAINED? {'YES (real probs)' if is_real else 'NO (heuristic)'}")

        r = await c.post("/training/fit-and-eval", headers=h)
        print(f"7. FIT+EVAL: {r.status_code}", r.json().get("calibration", {}) if r.status_code == 200 else r.text[:100])

        r = await c.post("/predictions/predict?model_key=ensemble", headers=h, json={
            "home_team": "Real Madrid", "away_team": "Barcelona", "league": "LL",
        })
        d = r.json()
        print(f"8. ENSEMBLE: H={d['home_win_prob'][:6]} D={d['draw_prob'][:6]} A={d['away_win_prob'][:6]} conf={d['confidence']}")

        print("\n=== ALL TRAINING TESTS ===")

asyncio.run(smoke())