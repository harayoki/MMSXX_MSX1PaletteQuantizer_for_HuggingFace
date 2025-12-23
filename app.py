import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


ROOT_DIR = Path(__file__).parent.resolve()
NODE_MODULES = ROOT_DIR / "node_modules"
PACKAGE_LOCK = ROOT_DIR / "package-lock.json"


def ensure_npm() -> None:
    if shutil.which("npm") is None:
        raise RuntimeError("npm is required to run the SvelteKit app, but it was not found in PATH.")


def install_dependencies() -> None:
    if NODE_MODULES.exists():
        return

    command = ["npm", "ci" if PACKAGE_LOCK.exists() else "install"]
    subprocess.run(command, cwd=ROOT_DIR, check=True)


def build_svelte() -> None:
    subprocess.run(["npm", "run", "build"], cwd=ROOT_DIR, check=True)


def start_preview_server(port: int) -> subprocess.Popen:
    host = os.environ.get("HOST", "0.0.0.0")
    command: List[str] = ["npm", "run", "preview", "--", "--host", host, "--port", str(port)]
    env = os.environ.copy()
    env["HOST"] = host
    env["PORT"] = str(port)
    return subprocess.Popen(command, cwd=ROOT_DIR, env=env)


def wait_for_process(proc: subprocess.Popen) -> int:
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        return proc.wait()


def main() -> Tuple[int, str]:
    ensure_npm()
    install_dependencies()
    build_svelte()

    port = int(os.environ.get("PORT", "7860"))
    process = start_preview_server(port)
    exit_code = wait_for_process(process)
    return exit_code, f"SvelteKit preview exited with code {exit_code}"


if __name__ == "__main__":
    code, message = main()
    if message:
        print(message)
    sys.exit(code)
