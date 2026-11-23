"""Small Leadnius API client for the daily lead jobs (no dependencies)."""
import csv
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
API = "http://localhost:8000/api"
ACCOUNTS = json.load(open(os.path.join(HERE, "accounts.json")))


class ApiError(RuntimeError):
    pass


def call(method, path, token=None, body=None, form=None, headers=None):
    headers, data = dict(headers or {}), None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    elif form is not None:
        data, headers["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        raise ApiError(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")


def org_token(org):
    email, pw = ACCOUNTS[org]
    tok = call("POST", "/auth/login", form={"username": email, "password": pw})["access_token"]
    o = next(x for x in call("GET", "/organizations", tok)["organizations"] if x["name"] == org)
    return call("POST", f"/organizations/switch/{o['id']}", tok)["access_token"]


def healthy():
    try:
        urllib.request.urlopen("http://localhost:8000/docs", timeout=10)
        return True
    except Exception:  # noqa: BLE001
        return False


def psql(sql):
    line = next(l for l in open(os.path.join(ROOT, "lead-gen-backend", ".env")) if l.startswith("DATABASE_URL"))
    env = {**os.environ, "PGPASSWORD": urllib.parse.unquote(line.split("postgres:", 1)[1].split("@", 1)[0])}
    r = subprocess.run(["/Library/PostgreSQL/18/bin/psql", "-h", "localhost", "-U", "postgres", "-d", "lead_genius", "--csv", "-c", sql],
                       env=env, capture_output=True, text=True, check=True)
    return list(csv.DictReader(r.stdout.splitlines()))
