import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

settings = get_settings()

TEMP_DIR = Path(tempfile.gettempdir()) / "bet-bridge"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

BRIDGE_TIMEOUT = settings.bridge_timeout_seconds
ODDSHARVESTER_TIMEOUT = settings.oddsharvester_timeout_seconds


class BridgeError(Exception):
    pass


@dataclass(frozen=True)
class OddsHarvesterJsonResult:
    records: list[dict]
    report: dict | None = None
    cli_error: str | None = None


def bridge_runtime_summary() -> dict[str, str]:
    return {
        "penaltyblog_python": settings.resolved_penaltyblog_python,
        "penaltyblog_bridge": settings.resolved_penaltyblog_bridge,
        "penaltyblog_root": settings.resolved_penaltyblog_root,
        "soccerdata_python": settings.resolved_soccerdata_python,
        "soccerdata_bridge": settings.resolved_soccerdata_bridge,
        "soccerdata_root": settings.resolved_soccerdata_root,
        "oddsharvester_python": settings.resolved_oddsharvester_python,
    }


def validate_bridge_runtime(provider: str) -> list[str]:
    return settings.provider_validation_issues(provider)


def _require_provider_runtime(provider: str) -> None:
    issues = validate_bridge_runtime(provider)
    if issues:
        raise BridgeError(f"{provider} runtime is not ready: {'; '.join(issues)}")


async def run_bridge(
    payload: dict,
    python_bin: str,
    bridge_script: str,
    label: str = "bridge",
    timeout: int = BRIDGE_TIMEOUT,
    extra_env: dict[str, str] | None = None,
) -> dict:
    if not bridge_script:
        raise BridgeError(
            f"{label} bridge script is not configured. Set the corresponding BET_* bridge path env var."
        )

    python_path = Path(python_bin)
    if not python_path.exists():
        raise BridgeError(
            f"{label} python executable not found: {python_bin}. "
            f"Check backend/.env.example and set the BET_* bridge runtime paths."
        )

    bridge_path = Path(bridge_script)
    if not bridge_path.exists():
        raise BridgeError(
            f"{label} bridge script not found: {bridge_script}. "
            f"Check backend/.env.example and set the BET_* bridge runtime paths."
        )

    output_path = TEMP_DIR / f"{label}_{os.getpid()}_{id(payload)}.json"
    cmd = [python_bin, bridge_script, "--payload", json.dumps(payload), "--output", str(output_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **(extra_env or {})},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise BridgeError(f"{label} request timed out after {timeout}s")

        if proc.returncode != 0:
            stderr_text = stderr.decode().strip() if stderr else ""
            raise BridgeError(stderr_text or f"{label} bridge exited with code {proc.returncode}")

        if not output_path.exists():
            raise BridgeError(f"{label} bridge produced no output file")

        text = output_path.read_text()
        output_path.unlink(missing_ok=True)
        parsed = json.loads(text)

        if not parsed.get("ok"):
            raise BridgeError(parsed.get("error", f"{label} bridge returned failure"))

        return parsed["result"]
    except BridgeError:
        raise
    except Exception as e:
        raise BridgeError(f"{label} bridge error: {e}") from e


async def run_penaltyblog(payload: dict) -> dict:
    _require_provider_runtime("penaltyblog")
    return await run_bridge(
        payload,
        settings.resolved_penaltyblog_python,
        settings.resolved_penaltyblog_bridge,
        label="penaltyblog",
        extra_env={"BET_PENALTYBLOG_ROOT": settings.resolved_penaltyblog_root},
    )


async def run_soccerdata(payload: dict) -> dict:
    _require_provider_runtime("soccerdata")
    return await run_bridge(
        payload,
        settings.resolved_soccerdata_python,
        settings.resolved_soccerdata_bridge,
        label="soccerdata",
        extra_env={"BET_SOCCERDATA_ROOT": settings.resolved_soccerdata_root},
    )


async def run_oddsharvester(
    args: list[str], *, timeout: int | None = None, extra_env: dict[str, str] | None = None
) -> str:
    python_bin = settings.resolved_oddsharvester_python
    if not python_bin or not Path(python_bin).exists():
        raise BridgeError(
            f"oddsharvester python executable not found: {python_bin}. "
            f"Check backend/.env.example and set BET_ODDSHARVESTER_PYTHON."
        )

    cmd = [python_bin, "-m", "oddsharvester", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **(extra_env or {})},
        )
        effective_timeout = timeout or ODDSHARVESTER_TIMEOUT
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
        if proc.returncode != 0:
            raise BridgeError(stderr.decode().strip() or f"OddsHarvester exited with code {proc.returncode}")
        return stdout.decode().strip()
    except asyncio.TimeoutError:
        proc.kill()
        raise BridgeError(f"OddsHarvester request timed out after {timeout or ODDSHARVESTER_TIMEOUT}s")


async def validate_oddsharvester_football_catalog(
    candidates: list[dict], *, timeout: int | None = None, season: str | None = None
) -> list[dict]:
    """Run the bounded Results-page validator for discovered football leagues."""
    _require_provider_runtime("oddsharvester")
    script_path = settings.repo_root / "OddsHarvester" / "scripts" / "validate_football_catalog.py"
    if not script_path.exists():
        raise BridgeError(f"OddsHarvester catalog validator not found: {script_path}")

    token = f"catalog_validation_{os.getpid()}_{id(candidates)}"
    input_path = TEMP_DIR / f"{token}.input.json"
    output_path = TEMP_DIR / f"{token}.output.json"
    input_path.write_text(json.dumps(candidates))
    cmd = [
        settings.resolved_oddsharvester_python,
        str(script_path),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]
    if season:
        cmd.extend(["--season", season])
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout or ODDSHARVESTER_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise BridgeError(f"OddsHarvester catalog validation timed out after {timeout or ODDSHARVESTER_TIMEOUT}s")
        if proc.returncode != 0:
            raise BridgeError(stderr.decode().strip() or "OddsHarvester catalog validator failed")
        if not output_path.exists():
            raise BridgeError("OddsHarvester catalog validator produced no output file")
        payload = json.loads(output_path.read_text())
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise BridgeError("OddsHarvester catalog validator returned invalid JSON")
        return payload
    except json.JSONDecodeError as exc:
        raise BridgeError(f"OddsHarvester catalog validator returned invalid JSON: {exc}") from exc
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


async def discover_oddsharvester_football_catalog(*, timeout: int | None = None) -> dict:
    """Discover the rendered OddsPortal football catalog through the existing worker script."""
    _require_provider_runtime("oddsharvester")
    script_path = settings.repo_root / "OddsHarvester" / "scripts" / "discover_football_catalog.py"
    if not script_path.exists():
        raise BridgeError(f"OddsHarvester catalog discovery script not found: {script_path}")

    output_path = TEMP_DIR / f"catalog_discovery_{os.getpid()}_{id(asyncio.current_task())}.json"
    cmd = [
        settings.resolved_oddsharvester_python,
        str(script_path),
        "--output",
        str(output_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            _stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or ODDSHARVESTER_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise BridgeError(
                f"OddsHarvester catalog discovery timed out after {timeout or ODDSHARVESTER_TIMEOUT}s"
            )
        if proc.returncode != 0:
            raise BridgeError(stderr.decode().strip() or "OddsHarvester catalog discovery failed")
        if not output_path.exists():
            raise BridgeError("OddsHarvester catalog discovery produced no output file")
        payload = json.loads(output_path.read_text())
        leagues = payload.get("leagues") if isinstance(payload, dict) else None
        if not isinstance(leagues, list) or not all(isinstance(item, dict) for item in leagues):
            raise BridgeError("OddsHarvester catalog discovery returned invalid JSON")
        return payload
    except json.JSONDecodeError as exc:
        raise BridgeError(f"OddsHarvester catalog discovery returned invalid JSON: {exc}") from exc
    finally:
        output_path.unlink(missing_ok=True)


async def run_oddsharvester_json(
    args: list[str],
    label: str = "oddsharvester",
    *,
    timeout: int | None = None,
    include_report: bool = False,
    extra_env: dict[str, str] | None = None,
) -> list[dict] | OddsHarvesterJsonResult:
    output_path = TEMP_DIR / f"{label}_{os.getpid()}_{abs(hash(tuple(args)))}.json"
    report_path = output_path.with_suffix(".report.json")
    command_args = [*args, "--output", str(output_path), "--format", "json"]
    if include_report:
        command_args.extend(["--report-output", str(report_path)])

    cli_error: str | None = None
    run_kwargs: dict[str, object] = {"timeout": timeout}
    if extra_env:
        run_kwargs["extra_env"] = extra_env
    try:
        raw_output = await run_oddsharvester(command_args, **run_kwargs)
    except BridgeError as exc:
        cli_error = str(exc)
        if include_report and _report_option_is_unsupported(cli_error):
            output_path.unlink(missing_ok=True)
            report_path.unlink(missing_ok=True)
            raw_output = await run_oddsharvester(
                [*args, "--output", str(output_path), "--format", "json"], **run_kwargs
            )
            cli_error = None
        elif not (include_report and report_path.exists()):
            output_path.unlink(missing_ok=True)
            report_path.unlink(missing_ok=True)
            raise

    try:
        report = _read_oddsharvester_report(report_path) if report_path.exists() else None
    except BridgeError:
        output_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        raise

    if not output_path.exists():
        report_path.unlink(missing_ok=True)
        if include_report and report is not None:
            return OddsHarvesterJsonResult(records=[], report=report, cli_error=cli_error)
        raise BridgeError(
            "OddsHarvester completed without producing a JSON output file. "
            f"CLI output was: {raw_output or '(empty)'}"
        )

    try:
        payload = json.loads(output_path.read_text())
    except json.JSONDecodeError as exc:
        raise BridgeError(f"OddsHarvester returned invalid JSON output: {exc}") from exc
    finally:
        output_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)

    if not isinstance(payload, list):
        raise BridgeError("OddsHarvester JSON output must be a list of scraped match records")

    if include_report:
        return OddsHarvesterJsonResult(records=payload, report=report, cli_error=cli_error)
    return payload


def _report_option_is_unsupported(error: str) -> bool:
    normalized = error.lower()
    return "report-output" in normalized and ("no such option" in normalized or "unknown option" in normalized)


def _read_oddsharvester_report(report_path: Path) -> dict:
    try:
        report = json.loads(report_path.read_text())
    except json.JSONDecodeError as exc:
        raise BridgeError(f"OddsHarvester returned an invalid JSON report: {exc}") from exc
    if not isinstance(report, dict):
        raise BridgeError("OddsHarvester JSON report must be an object")
    return report
