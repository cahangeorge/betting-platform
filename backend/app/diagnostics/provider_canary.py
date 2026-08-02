import asyncio
import os

from app.config import get_settings
from app.providers import DEFAULT_PROVIDER_REGISTRY, ProviderExecutionContext
from app.services.python_bridge import run_penaltyblog, run_soccerdata

settings = get_settings()


async def _verify_oddsharvester_browser() -> None:
    script = """
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("<title>Bet provider canary</title>")
        assert await page.title() == "Bet provider canary"
        await browser.close()

asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        settings.resolved_oddsharvester_python,
        "-c",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    if process.returncode != 0:
        raise RuntimeError(f"OddsHarvester Chromium canary failed: {stderr.decode().strip()}")


async def verify_provider_runtime() -> None:
    # Evaluate the provider gate before any runtime or subprocess work.
    DEFAULT_PROVIDER_REGISTRY.require_operation(
        "penaltyblog",
        "local-model",
        "goal_expectancy",
        context=ProviderExecutionContext.CANARY,
    )
    issues = settings.bridge_validation_issues()
    if issues:
        raise RuntimeError("Provider runtime paths are incomplete")

    prediction = await run_penaltyblog(
        {
            "operation": "goal_expectancy",
            "payload": {
                "home": 0.48,
                "draw": 0.28,
                "away": 0.24,
                "return_details": True,
            },
        }
    )
    if prediction.get("operation") != "goal_expectancy":
        raise RuntimeError("Penaltyblog prediction canary returned an invalid payload")

    catalog = await run_soccerdata({"operation": "catalog"})
    if not isinstance(catalog, dict) or not catalog:
        raise RuntimeError("Soccerdata catalog canary returned an invalid payload")

    await _verify_oddsharvester_browser()


if __name__ == "__main__":
    asyncio.run(verify_provider_runtime())
    print("Provider runtime canary passed")
