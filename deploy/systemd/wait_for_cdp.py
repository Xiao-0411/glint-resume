"""Wait until the local crawler Chrome exposes its CDP endpoint."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def wait_for_cdp(port: int, timeout: float) -> bool:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as response:
                payload = json.load(response)
            if payload.get("webSocketDebuggerUrl"):
                return True
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if wait_for_cdp(args.port, args.timeout):
        print(f"CDP is ready on 127.0.0.1:{args.port}")
        return 0
    print(f"CDP did not become ready on 127.0.0.1:{args.port}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
