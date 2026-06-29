"""
monitor_bridge.py — Poll printer status and push progress to frontend.

Runs in a loop: queries printer via bambu.py status --json every interval,
writes progress to task_state so the frontend WebSocket picks up updates.
Exits when print completes (state becomes IDLE) or on unrecoverable error.

Usage:
  python monitor_bridge.py <task_id> [--interval 60]
"""

import os, sys, time, json, re, subprocess, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_state import set_status, get_status

BAMBU_SCRIPT = os.path.join(
    os.environ.get("SKILLS_DIR",
                    os.path.expanduser(r"~\.openclaw\workspace\skills")),
    "bambu-studio-ai", "scripts", "bambu.py"
)

POLL_INTERVAL = 60  # seconds between checks
MAX_FAILURES = 5


def _env():
    env = os.environ.copy()
    env.setdefault("BAMBU_MODE", "local")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _printer_conn_info():
    """Read printer connection info from env vars (set by PowerShell prompt)."""
    return (
        os.environ.get("BAMBU_IP", ""),
        os.environ.get("BAMBU_ACCESS_CODE", ""),
        os.environ.get("BAMBU_SERIAL", ""),
    )


def run_direct_status():
    """Query printer directly via bambulabs_api MQTT.

    Returns a clean dict suitable for JSON serialization.  Bypasses
    bambu.py's subprocess overhead and serialization bugs, and gives
    access to the raw MQTT print data (progress, layer, etc.) that
    bambu.py's text output may skip for non-RUNNING/PAUSE states.
    """
    try:
        import bambulabs_api as bl

        ip, access_code, serial = _printer_conn_info()
        if not all([ip, access_code, serial]):
            print("  Missing printer connection env vars")
            return None

        printer = bl.Printer(ip, access_code, serial)
        # Full connect: MQTT start + pushall to populate _data
        printer.connect()
        time.sleep(5)

        data = printer.mqtt_client._data
        pd = data.get("print", {})
        printer.disconnect()

        if not pd:
            return None

        result = {}

        # State
        result["state"] = pd.get("gcode_state") or "UNKNOWN"

        # Progress (%): mc_percent is the main progress field
        mc = pd.get("mc_percent")
        if mc is not None:
            result["progress"] = int(mc)

        # Remaining time (minutes)
        mr = pd.get("mc_remaining_time")
        if mr is not None:
            result["remaining"] = int(mr)

        # Layer info — from 3D sub-object
        d3 = pd.get("3D", {})
        ln = d3.get("layer_num")
        tn = d3.get("total_layer_num")
        if ln is not None and tn is not None:
            result["layer"] = int(ln)
            result["total_layers"] = int(tn)

        # Temperatures
        nt = pd.get("nozzle_temper")
        if nt is not None:
            result["nozzle_temp"] = float(nt)
        ntt = pd.get("nozzle_target_temper")
        if ntt is not None:
            result["nozzle_target"] = float(ntt)

        bt = pd.get("bed_temper")
        if bt is not None:
            result["bed_temp"] = float(bt)
        btt = pd.get("bed_target_temper")
        if btt is not None:
            result["bed_target"] = float(btt)

        # File name
        result["file"] = pd.get("gcode_file") or pd.get("subtask_name") or ""

        # Speed level
        spd = pd.get("spd_lvl")
        if spd is not None:
            result["speed"] = int(spd)

        return result

    except Exception as e:
        print(f"  Direct status error: {e}")
        return None


def run_bambu_status():
    """Get printer status. Tries direct MQTT first, falls back to bambu.py."""
    # Primary: direct MQTT (richer data, no serialization bugs)
    status = run_direct_status()
    if status and status.get("state"):
        return status

    # Fallback: bambu.py subprocess
    try:
        r = subprocess.run(
            [sys.executable, BAMBU_SCRIPT, "status"],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
            env=_env()
        )
        if r.returncode == 0 and r.stdout.strip():
            status = parse_text_status(r.stdout)
            if status:
                return status
        print(f"  bambu.py exit={r.returncode} stderr={r.stderr.strip()[-200:]}")
    except subprocess.TimeoutExpired:
        print("  bambu.py status timed out (30s)")
    except FileNotFoundError:
        print(f"  Python not found at: {sys.executable}")
    except Exception as e:
        print(f"  bambu.py error: {e}")
    return None


def parse_text_status(text):
    """Parse bambu.py status text output into a dict.
    Example text:
      🔌 LAN | Bambu Lab X2D
      🔥 Nozzle: 210.0°C / 220.0°C
      🛏️ Bed: 55.0°C / 55.0°C
      📄 State: RUNNING
      🏎️ Speed: Standard
      💡 Light: ON
      📁 File: model.gcode.3mf
      📊 Progress: 45%
      📐 Layer: 52/119
      ⏳ Remaining: 0h 15m
    """
    result = {}
    try:
        # State
        m = re.search(r"State:\s*(\S+)", text)
        if m:
            result["state"] = m.group(1)

        # Progress
        m = re.search(r"Progress:\s*([\d.]+)%", text)
        if m:
            result["progress"] = float(m.group(1))

        # Nozzle temp
        m = re.search(r"Nozzle:\s*([\d.]+)°C\s*/\s*([\d.]+)°C", text)
        if m:
            result["nozzle_temp"] = float(m.group(1))
            result["nozzle_target"] = float(m.group(2))

        # Bed temp
        m = re.search(r"Bed:\s*([\d.]+)°C\s*/\s*([\d.]+)°C", text)
        if m:
            result["bed_temp"] = float(m.group(1))
            result["bed_target"] = float(m.group(2))

        # Remaining time: "0h 15m" → total minutes
        m = re.search(r"Remaining:\s*(\d+)h\s*(\d+)m", text)
        if m:
            result["remaining"] = int(m.group(1)) * 60 + int(m.group(2))

        # Layer
        m = re.search(r"Layer:\s*(\d+)/(\d+)", text)
        if m:
            result["layer"] = int(m.group(1))
            result["total_layers"] = int(m.group(2))

        # File
        m = re.search(r"File:\s*(.+)", text)
        if m:
            result["file"] = m.group(1).strip()

        # Speed
        m = re.search(r"Speed:\s*(.+)", text)
        if m:
            result["speed"] = m.group(1).strip()
    except Exception as e:
        print(f"  Text parse error: {e}")
    return result if result else None


def main():
    parser = argparse.ArgumentParser(description="Monitor print and push to frontend")
    parser.add_argument("task_id")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL)
    args = parser.parse_args()

    task_id = args.task_id
    interval = args.interval
    failures = 0
    last_progress = None
    last_progress_ticks = 0

    print(f"Monitor bridge started: task={task_id}, interval={interval}s")

    while True:
        status = run_bambu_status()

        if status is None:
            failures += 1
            print(f"Status check failed ({failures}/{MAX_FAILURES})")
            if failures >= MAX_FAILURES:
                set_status(task_id, "failed",
                           step="monitoring",
                           progress=last_progress or 0,
                           message="监控中断：连续多次获取状态失败")
                sys.exit(1)
            time.sleep(interval)
            continue

        failures = 0
        state = status.get("state", "").upper()
        progress = status.get("progress", 0)
        remaining = status.get("remaining", 0)
        nozzle = status.get("nozzle_temp", 0)
        bed = status.get("bed_temp", 0)
        layer = status.get("layer")
        total_layers = status.get("total_layers")

        # Detect stall: progress unchanged for STALL ticks
        if progress == last_progress and state in ("RUNNING", "PAUSE"):
            last_progress_ticks += 1
        else:
            last_progress_ticks = 0
        last_progress = progress

        # Build message
        parts = []
        if state == "PAUSE":
            parts.append("打印已暂停")
        elif state in ("FAILED", "ERROR", "FAULT", "ABORT"):
            parts.append(f"打印异常: {state}")
        else:
            parts.append(f"打印中")
        parts.append(f"{progress}%")
        if remaining:
            parts.append(f"剩余 {remaining // 60}h{remaining % 60}m")
        if layer and total_layers:
            parts.append(f"层 {layer}/{total_layers}")
        if last_progress_ticks >= 10:  # stalled for 10+ checks
            parts.append(f"⚠️ 进度停滞")

        message = " | ".join(parts)
        print(f"[{state}] {message}")

        if state in ("FAILED", "ERROR", "FAULT", "ABORT"):
            set_status(task_id, "failed",
                       step="monitoring",
                       progress=progress,
                       message=f"打印失败: {state}")
            sys.exit(1)

        if state == "IDLE" or state == "FINISH":
            set_status(task_id, "done",
                       step="done",
                       progress=100,
                       message="打印完成")
            print("Print complete.")
            break

        set_status(task_id, "printing",
                   step="printing",
                   progress=min(progress or 0, 99),
                   message=message)

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor bridge stopped.")
        sys.exit(130)
