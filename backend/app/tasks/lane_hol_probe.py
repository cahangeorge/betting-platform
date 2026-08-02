"""Real Redis probe proving browser work cannot head-of-line block control."""

import asyncio
import secrets
from time import monotonic

from app.config import get_settings
from app.tasks.broker import broker
from app.tasks.jobs import taskiq_healthcheck_task
from app.tasks.worker_lanes import WorkerLane, queue_name_for_lane


async def verify_lane_head_of_line_isolation(
    *, browser_delay_seconds: float = 2.0, control_deadline_seconds: float = 1.5
) -> None:
    settings = get_settings()
    browser_nonce = f"browser-{secrets.token_urlsafe(12)}"
    control_nonce = f"control-{secrets.token_urlsafe(12)}"

    await broker.startup()
    try:
        browser_task = (
            await taskiq_healthcheck_task.kicker()
            .with_labels(queue_name=queue_name_for_lane(settings, WorkerLane.PROVIDER_BROWSER))
            .kiq(browser_nonce, delay_seconds=browser_delay_seconds)
        )
        await asyncio.sleep(0.1)

        started = monotonic()
        control_task = (
            await taskiq_healthcheck_task.kicker()
            .with_labels(queue_name=queue_name_for_lane(settings, WorkerLane.CONTROL))
            .kiq(control_nonce)
        )
        control_result = await control_task.wait_result(timeout=control_deadline_seconds)
        control_elapsed = monotonic() - started
        browser_result = await browser_task.wait_result(timeout=browser_delay_seconds + 10)
    finally:
        await broker.shutdown()

    if control_result.is_err or control_result.return_value != control_nonce:
        raise RuntimeError("Control lane returned an invalid healthcheck result")
    if control_elapsed >= control_deadline_seconds:
        raise RuntimeError(f"Control lane exceeded its {control_deadline_seconds:.2f}s isolation deadline")
    if browser_result.is_err or browser_result.return_value != browser_nonce:
        raise RuntimeError("Browser lane returned an invalid delayed result")


if __name__ == "__main__":
    asyncio.run(verify_lane_head_of_line_isolation())
    print("Taskiq browser/control head-of-line isolation passed")
