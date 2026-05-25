"""Install windmill-app-dashboard.json into Windmill via the REST API.

Reads WINDMILL_PUBLIC_URL, WINDMILL_WORKSPACE, WINDMILL_TOKEN from .env (or env vars),
computes policy.triggerables_v2 (sha256 of each inline script's content), and POSTs to
/api/w/{ws}/apps/create — falling back to /apps/update/{path} if the app exists.

Run:
    python install-dashboard.py
    python install-dashboard.py --path u/admin/loan_dashboard --workspace loan
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_triggerables(value: dict) -> dict[str, dict]:
    """Allowlist every inline script in the app, keyed by rawscript/<sha256(content)>.

    Without this the app raises "Policy is missing triggerables" in viewer mode.
    """
    triggerables: dict[str, dict] = {}

    def entry() -> dict:
        return {"static_inputs": {}, "one_of_inputs": {}, "allow_user_resources": []}

    for script in value.get("hiddenInlineScripts", []) or []:
        content = (script.get("inlineScript") or {}).get("content")
        if content:
            triggerables[f"rawscript/{sha256_hex(content)}"] = entry()

    for grid_item in value.get("grid", []) or []:
        component_id = grid_item.get("id")
        ci = (grid_item.get("data") or {}).get("componentInput") or {}
        if ci.get("type") == "runnable":
            runnable = ci.get("runnable") or {}
            inline = runnable.get("inlineScript") or {}
            content = inline.get("content")
            if content:
                h = sha256_hex(content)
                triggerables[f"rawscript/{h}"] = entry()
                if component_id:
                    triggerables[f"{component_id}:rawscript/{h}"] = entry()

    return triggerables


def http_json(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    env = load_env(repo_root / ".env")

    p = argparse.ArgumentParser()
    p.add_argument("--base-url",  default=env.get("WINDMILL_PUBLIC_URL", "http://localhost:8080"))
    p.add_argument("--workspace", default=env.get("WINDMILL_WORKSPACE"))
    p.add_argument("--token",     default=env.get("WINDMILL_TOKEN"))
    p.add_argument("--path",      default="u/admin/loan_dashboard")
    p.add_argument("--json-file", default=str(repo_root / "windmill-app-dashboard.json"))
    args = p.parse_args()

    if not args.workspace:
        sys.exit("WINDMILL_WORKSPACE not set (.env or --workspace)")
    if not args.token:
        sys.exit("WINDMILL_TOKEN not set (.env or --token)")

    json_path = Path(args.json_file)
    if not json_path.exists():
        sys.exit(f"App JSON not found: {json_path}")

    app = json.loads(json_path.read_text(encoding="utf-8"))
    value = app["value"]
    policy = value.pop("policy", None) or {"execution_mode": "viewer"}
    policy["triggerables_v2"] = build_triggerables(value)

    print(f"Windmill:   {args.base_url}")
    print(f"Workspace:  {args.workspace}")
    print(f"App path:   {args.path}")
    print(f"Source:     {json_path}")
    print(f"Components: {len(value.get('grid', []))}")
    print(f"Scripts:    {len(value.get('hiddenInlineScripts', []))}")
    print(f"Triggerables: {len(policy['triggerables_v2'])}")
    print()

    create_body = {"path": args.path, "summary": app.get("summary", ""), "value": value, "policy": policy}
    create_url = f"{args.base_url}/api/w/{args.workspace}/apps/create"
    update_url = f"{args.base_url}/api/w/{args.workspace}/apps/update/{args.path}"

    print(f"POST {create_url}")
    status, body = http_json("POST", create_url, args.token, create_body)
    if 200 <= status < 300:
        print(f"[OK] Created: {body.strip()}")
    elif status == 409 or "already exists" in body.lower():
        print(f"[INFO] App exists, updating...")
        update_body = {"summary": app.get("summary", ""), "value": value, "policy": policy}
        print(f"POST {update_url}")
        status, body = http_json("POST", update_url, args.token, update_body)
        if 200 <= status < 300:
            print(f"[OK] Updated: {body.strip()}")
        else:
            print(f"[FAIL] HTTP {status}: {body}", file=sys.stderr)
            return 1
    else:
        print(f"[FAIL] HTTP {status}: {body}", file=sys.stderr)
        return 1

    print()
    print(f"Open: {args.base_url}/apps/get/{args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
