"""
One-shot TastyTrade OAuth refresh-token setup.

Runs on your local host (NOT in Docker) because the OAuth redirect URI is
http://localhost:8000/callback and your browser needs to reach it.

What it does:
  1. Reads TT_CLIENT_ID / TT_CLIENT_SECRET from .env (project root)
  2. Starts a tiny HTTP server on 127.0.0.1:8000
  3. Opens your default browser to TastyTrade's OAuth authorize URL
  4. You click "Authorize" (you'll already be logged in)
  5. TastyTrade redirects to http://localhost:8000/callback?code=...
  6. Script exchanges the code for an access+refresh token pair
  7. Writes the new TT_REFRESH_TOKEN to .env (atomic backup first)
  8. Prints success

Usage (from project root, NOT inside Docker):
    python backend/scripts/tt_oauth_setup.py

Only stdlib — no pip install required.
"""
from __future__ import annotations

import http.server
import os
import shutil
import socketserver
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

TT_AUTH_BASE = "https://my.tastytrade.com"         # where the user lands to authorize
TT_API_BASE  = "https://api.tastytrade.com"        # where we exchange the code
REDIRECT_URI = "http://localhost:8765/callback"
LOCAL_PORT   = 8765


def project_root() -> Path:
    here = Path(__file__).resolve()
    # .../backend/scripts/tt_oauth_setup.py  -> project root is two up from scripts
    return here.parent.parent.parent


def read_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        print(f"ERROR: .env not found at {env_path}")
        sys.exit(1)
    out: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def update_env(env_path: Path, key: str, new_value: str) -> None:
    """Replace KEY=... line in .env, preserving everything else.
    Creates a .bak backup first."""
    backup = env_path.with_suffix(env_path.suffix + ".bak")
    shutil.copyfile(env_path, backup)
    lines = env_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={new_value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={new_value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"  → backed up original to {backup.name}")
    print(f"  → wrote new {key} to {env_path.name}")


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    # populated by the main thread after the request arrives
    received_code: str | None = None
    received_error: str | None = None

    def log_message(self, *args, **kwargs):
        pass  # quiet

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        err = qs.get("error", [None])[0]
        err_desc = qs.get("error_description", [None])[0]

        CallbackHandler.received_code = code
        CallbackHandler.received_error = err or err_desc

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code:
            msg = (
                "<h1>✅ Authorization received</h1>"
                "<p>You can close this tab and return to the terminal.</p>"
            )
        else:
            msg = (
                f"<h1>❌ Authorization failed</h1><p>{err or 'no code returned'}</p>"
                f"<pre>{err_desc or ''}</pre>"
            )
        self.wfile.write(msg.encode("utf-8"))


def exchange_code_for_tokens(
    code: str, client_id: str, client_secret: str
) -> dict:
    """POST to TT's /oauth/token with authorization_code grant."""
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
    }).encode("ascii")
    req = urllib.request.Request(
        f"{TT_API_BASE}/oauth/token",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            import json
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"\nERROR: token exchange failed: HTTP {e.code}")
        print(f"  body: {e.read().decode('utf-8', errors='replace')[:500]}")
        sys.exit(1)


def main() -> None:
    env_path = project_root() / ".env"
    env = read_env(env_path)
    client_id = env.get("TT_CLIENT_ID", "")
    client_secret = env.get("TT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: TT_CLIENT_ID / TT_CLIENT_SECRET missing from .env")
        sys.exit(1)

    print("=" * 70)
    print("  TastyTrade OAuth refresh-token setup")
    print("=" * 70)
    print(f"  .env:        {env_path}")
    print(f"  client_id:   {client_id[:8]}…")
    print(f"  redirect:    {REDIRECT_URI}")
    print()

    # 1. Start local server to catch the redirect
    server = socketserver.TCPServer(("127.0.0.1", LOCAL_PORT), CallbackHandler)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"  → local callback server listening on {REDIRECT_URI}")

    # 2. Build the authorize URL and open the browser
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": "read",
    }
    auth_url = f"{TT_AUTH_BASE}/auth.html?{urllib.parse.urlencode(auth_params)}"
    print(f"\n  → opening browser to:\n     {auth_url}\n")
    print("  If the browser does not open automatically, copy-paste the URL above.")
    print("  Then click 'Authorize' in TastyTrade.\n")
    webbrowser.open(auth_url)

    # 3. Wait for the callback (up to 120s)
    deadline = time.time() + 120
    print("  waiting for callback", end="", flush=True)
    while time.time() < deadline:
        if CallbackHandler.received_code or CallbackHandler.received_error:
            break
        time.sleep(0.5)
        print(".", end="", flush=True)
    print()

    server.shutdown()
    server.server_close()

    if CallbackHandler.received_error:
        print(f"\n❌ OAuth denied / errored: {CallbackHandler.received_error}")
        sys.exit(1)
    if not CallbackHandler.received_code:
        print("\n❌ Timed out waiting for authorization.")
        sys.exit(1)

    code = CallbackHandler.received_code
    print(f"\n  → got authorization code (len={len(code)})")

    # 4. Exchange code for tokens
    print("  → exchanging code for access+refresh tokens...")
    tokens = exchange_code_for_tokens(code, client_id, client_secret)

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in")

    if not refresh_token:
        print(f"ERROR: no refresh_token in response: {tokens}")
        sys.exit(1)

    print(f"  → access_token  (len={len(access_token or '')}, expires in {expires_in}s)")
    print(f"  → refresh_token (len={len(refresh_token)})")

    # 5. Update .env
    print("\n  → updating .env")
    update_env(env_path, "TT_REFRESH_TOKEN", refresh_token)

    print()
    print("=" * 70)
    print("  ✅ Setup complete.")
    print("=" * 70)
    print("  Next: restart the backend container to pick up the new token:")
    print("    docker restart earnings_calendar_engine-backend-1")
    print()


if __name__ == "__main__":
    main()
