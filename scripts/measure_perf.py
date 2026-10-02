"""Measure detection throughput on this machine: the real cameras, detector and journey tracker.

    python scripts/measure_perf.py                       # 13 demo feeds, 60 s, motion gating on
    python scripts/measure_perf.py --seconds 120 --no-gating
    DETECTOR_BACKEND=openvino python scripts/measure_perf.py

Plays the dashboard feeds from videos/ at FEED_FPS, runs the same DetectionLoop and journey
tracker as the server, and reports per-feed analysed frames per second (all feeds, feeds with
people or vehicles in view = "active", the rest = "idle"), the detection cycle time and CPU use.
Writes benchmark/results/perf_<cpu>.json. Quote the CPU and the settings with any number.
Power draw needs a plug-in meter; it is not measured here.
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def cpu_name():
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            return out or platform.processor()
        text = Path("/proc/cpuinfo").read_text()
        return re.search(r"model name\s*:\s*(.+)", text).group(1).strip()
    except Exception:
        return platform.processor() or "unknown CPU"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--warmup", type=float, default=15)
    ap.add_argument("--feeds", type=int, default=0, help="use only the first N feeds (0 = all)")
    ap.add_argument("--no-gating", action="store_true", help="analyse every feed on every pass")
    args = ap.parse_args()
    if args.no_gating:
        os.environ["MOTION_GATING"] = "0"

    from app import config
    from app.pipeline import Camera, DetectionLoop
    from app.tracking.tracker import JourneyTracker

    specs = config.CAMERAS[: args.feeds or None]
    cameras = [Camera(i, cam_id, name, config.VIDEO_DIR / file) for i, (cam_id, name, file) in enumerate(specs)]
    tracker = JourneyTracker({c.id: c.name for c in cameras})
    loop = DetectionLoop(cameras, on_results=tracker.update)
    for cam in cameras:
        cam.start()
    loop.start()

    time.sleep(args.warmup)
    start_counts, start_busy = dict(loop.processed), {}
    t0, cpu0 = time.time(), time.process_time()
    busy_samples = {c.id: 0 for c in cameras}
    samples = 0
    while time.time() - t0 < args.seconds:
        time.sleep(0.5)
        samples += 1
        for c in cameras:
            busy_samples[c.id] += bool(loop.busy.get(c.id))
    wall, cpu = time.time() - t0, time.process_time() - cpu0

    fps = {c.id: (loop.processed[c.id] - start_counts.get(c.id, 0)) / wall for c in cameras}
    active = [cid for cid, n in busy_samples.items() if n >= samples / 2]
    idle = [cid for cid in fps if cid not in active]
    mean = lambda ids: round(sum(fps[i] for i in ids) / len(ids), 2) if ids else None
    res = {
        "cpu": cpu_name(), "logical_cpus": os.cpu_count(), "os": platform.platform(),
        "backend": config.DETECTOR_BACKEND, "general_model": config.GENERAL_MODEL,
        "weapon_model": config.THREAT_MODEL.name, "motion_gating": config.MOTION_GATING,
        "idle_interval_s": config.IDLE_INTERVAL_S, "feeds": len(cameras), "feed_fps": config.FEED_FPS,
        "seconds": round(wall, 1),
        "fps_per_feed": {"all": mean(list(fps)), "active": mean(active), "idle": mean(idle),
                         "min": round(min(fps.values()), 2), "max": round(max(fps.values()), 2)},
        "active_feeds": len(active),
        "cycle_time_s": round(loop.cycle_time, 2),
        "process_cpu_percent_of_one_core": round(100 * cpu / wall),
        "per_feed": {cid: round(v, 2) for cid, v in fps.items()},
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out = ROOT / "benchmark" / "results"
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", res["cpu"].lower()).strip("-")[:40]
    model = res['general_model'].removesuffix('.onnx')
    path = out / f"perf_{slug}_{res['backend']}_{model}_{'gated' if res['motion_gating'] else 'all'}.json"
    path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    f = res["fps_per_feed"]
    print(f"{res['cpu']} · {res['backend']} · {res['general_model']} + weapon model · "
          f"motion gating {'on' if res['motion_gating'] else 'off'}")
    print(f"{res['feeds']} feeds, {res['seconds']} s: analysed fps per feed - all {f['all']}, "
          f"active ({res['active_feeds']} feeds) {f['active']}, idle {f['idle']} (min {f['min']}, max {f['max']})")
    print(f"detection cycle {res['cycle_time_s']} s; CPU {res['process_cpu_percent_of_one_core']}% of one core")
    print(f"saved {path.relative_to(ROOT)}")
    sys.stdout.flush()
    os._exit(0)  # camera threads are daemons; skip their teardown


if __name__ == "__main__":
    main()
