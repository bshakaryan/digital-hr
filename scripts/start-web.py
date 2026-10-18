"""Run the demo on a single Docker web host; fail if any child exits."""
import os
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from app.web_storage import prepare_storage, verify_storage


def main():
    env = os.environ.copy()
    if len(env.get("JWT_SECRET", "")) < 32 or len(env.get("DEMO_PASSWORD", "")) < 12:
        raise RuntimeError("Set JWT_SECRET (32+ characters) and DEMO_PASSWORD (12+ characters) in hosting Environment settings")
    if env.get("ZUP_MODE", "mock") != "mock" or env.get("DOCUMENTOLOG_MODE", "mock") != "mock":
        raise RuntimeError("The root Dockerfile runs the mock demo; use the separate-service deployment for real integrations")
    root = os.getuid() == 0
    storage = prepare_storage(env, owner=(1000, 1000) if root else None)
    # Prepare configured paths and existing DB/journal ownership before dropping
    # privileges, then verify writes as the actual application user.
    if root:
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
    verify_storage(storage)
    defaults = {
        "ZUP_MODE": "mock", "ZUP_AUTH_TYPE": "bearer",
        "ZUP_BASE_URL": "http://127.0.0.1:8300/hs/jana/v1",
        "ZUP_API_TOKEN": env["JWT_SECRET"],
        "DOCUMENTOLOG_MODE": "mock", "DOCUMENTOLOG_API_KEY": env["JWT_SECRET"],
        "DOCUMENTOLOG_BASE_URL": "http://127.0.0.1:8400",
        "DOCUMENTOLOG_MOCK_BACKEND_URL": "http://127.0.0.1:8000",
        "DOCUMENTOLOG_PUBLIC_URL": "http://127.0.0.1:8000",
        "DOCUMENTOLOG_CALLBACK_URL": "http://127.0.0.1:8000",
        "DOCUMENTOLOG_BROWSER_URL": env.get("RENDER_EXTERNAL_URL") or f"http://localhost:{env.get('PORT', '10000')}",
        "HOSTNAME": "0.0.0.0", "PORT": "10000",
    }
    for key, value in defaults.items():
        env.setdefault(key, value)
    env["HOSTNAME"] = "0.0.0.0"
    children = []

    def stop(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def start(name, args, cwd="/app/backend"):
        process = subprocess.Popen(args, cwd=cwd, env=env)
        children.append((name, process))

    def check_children():
        for name, process in children:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited with code {process.returncode}")

    def wait_http(url):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            check_children()
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (URLError, TimeoutError):
                pass
            time.sleep(0.2)
        raise RuntimeError(f"Startup health check timed out: {url}")

    def uvicorn(module, port, factory=False):
        return [sys.executable, "-m", "uvicorn", module, *(["--factory"] if factory else []),
                "--host", "127.0.0.1", "--port", str(port), "--no-access-log"]

    try:
        start("mock ZUP", uvicorn("app.mock_zup:app_factory", 8300, True))
        start("mock Documentolog", uvicorn("app.mock_documentolog:app_factory", 8400, True))
        wait_http("http://127.0.0.1:8300/health")
        wait_http("http://127.0.0.1:8400/health")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True, timeout=120)
        # Provision only an empty database, preserving intentionally cleared requests.
        subprocess.run([sys.executable, "-c", "from sqlalchemy import select; from sqlalchemy.orm import Session; "
            "from app.database import get_engine; from app.models import Employee; from app.seed import seed; "
            "db=Session(get_engine()); empty=db.scalar(select(Employee.id).limit(1)) is None; db.close(); "
            "seed() if empty else None"], env=env, check=True, timeout=120)
        if env.get("ZUP_MODE", "mock") == "mock":
            subprocess.run([sys.executable, "-m", "app.provision_jana_people"], env=env, check=True, timeout=120)
        # Both commands are idempotent: file hashes prevent duplicate imports, and
        # stable demo course codes/assignment keys preserve existing progress and XP.
        subprocess.run([sys.executable, "-m", "app.import_initial_knowledge", "--directory", "/app/corpus"],
                       env=env, check=True, timeout=240)
        subprocess.run([sys.executable, "-m", "app.provision_academy_demo"],
                       env=env, check=True, timeout=240)
        start("backend", uvicorn("app.main:app", 8000))
        wait_http("http://127.0.0.1:8000/api/health")
        start("ZUP worker", [sys.executable, "-m", "app.zup_worker"])
        start("frontend", ["node", "server.js"], "/app/web")
        while True:
            check_children()
            time.sleep(0.5)
    finally:
        for _, process in reversed(children):
            if process.poll() is None:
                process.terminate()
        for _, process in reversed(children):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
