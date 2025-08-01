import os
import signal
import subprocess
import sys
import time

processes = []


def stop(signum=None, frame=None):
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    if signum is not None:
        raise SystemExit(0)


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
try:
    processes.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "metricon.cli.main",
                "--root",
                os.environ.get("METRICON_HOME", ".metricon"),
                "serve",
                "--port",
                "8000",
            ],
            start_new_session=True,
        )
    )
    processes.append(subprocess.Popen(["npm", "run", "dev"], start_new_session=True))
    print("Workbench: http://127.0.0.1:5173 ; API: http://127.0.0.1:8000", flush=True)
    while all(process.poll() is None for process in processes):
        time.sleep(0.5)
    failed = next(process.returncode for process in processes if process.returncode is not None)
    raise SystemExit(failed or 1)
finally:
    stop()
