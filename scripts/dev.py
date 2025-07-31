import os
import signal
import subprocess
import sys
import time

processes = []


def stop(signum=None, frame=None):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
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
            ]
        )
    )
    processes.append(subprocess.Popen(["npm", "run", "dev"]))
    print("Workbench: http://127.0.0.1:5173 ; API: http://127.0.0.1:8000", flush=True)
    while all(process.poll() is None for process in processes):
        time.sleep(0.5)
finally:
    stop()
