#!/usr/bin/env python3
"""
Leadnius go-live preflight (docs/go-live.md). Reads the API and web-app env files and says what blocks a launch,
what is only switched off, and which OAuth / webhook URLs to register. Standard library only.

    python3 ops/golive_check.py                                   # the local env files (shows what's missing today)
    python3 ops/golive_check.py --backend prod-api.env --frontend prod-web.env
    python3 ops/golive_check.py --backend … --frontend … --strict  # exit 1 if anything blocks the launch

Values are never printed, only whether they look right.
"""
import argparse
import os
import re
import sys
from typing import Callable, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = re.compile(r"(//|@)(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|/|$)")
WEAK = {"supersecretkey", "change-me", "changeme", "secret", "change-me-to-a-random-string-of-at-least-32-characters"}


def load(path: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return env
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = re.split(r"\s+#", v, 1)[0].strip().strip('"').strip("'")
        env[k.strip()] = v
    return env


Check = Tuple[str, str, str]  # (status, area, message): status ok | warn | fail


def https_url(v: str) -> bool:
    return v.startswith("https://") and not LOCAL.search(v)


def run(be: Dict[str, str], fe: Dict[str, str]) -> List[Check]:
    out: List[Check] = []

    def check(ok: bool, area: str, good: str, bad: str, level: str = "fail") -> None:
        out.append(("ok", area, good) if ok else (level, area, bad))

    g = lambda env, k: (env.get(k) or os.environ.get(k) or "").strip()  # noqa: E731
    is_true = lambda v: v.lower() in ("1", "true", "yes")  # noqa: E731

    # ---------------- API (lead-gen-backend) ----------------
    A = "API"
    check(g(be, "DEV_MODE").lower() == "false", A, "DEV_MODE=false", "DEV_MODE must be false (demo seeding on, test-mode sends, dev token echo)")
    key = g(be, "SECRET_KEY")
    check(len(key) >= 32 and key not in WEAK, A, "SECRET_KEY is strong", "SECRET_KEY must be 32+ random characters (openssl rand -hex 32); the API refuses to start otherwise")
    db = g(be, "DATABASE_URL")
    check(bool(db) and not LOCAL.search(db), A, "DATABASE_URL points at a hosted database", "DATABASE_URL must point at the production Postgres (on Render it comes from the blueprint)")
    check(https_url(g(be, "FRONTEND_URL")), A, "FRONTEND_URL is the public https web app", "FRONTEND_URL must be the public https URL of the web app (OAuth returns and email links)")
    bu = g(be, "BACKEND_URL")
    check(https_url(bu), A, "BACKEND_URL is the public https API", "BACKEND_URL not set: Render's onrender.com URL is used for OAuth callbacks (set it when you use api.<your domain>)", "warn")
    wh = g(be, "INBOUND_WEBHOOK_SECRET")
    check(len(wh) >= 16 and wh != "change-me", A, "INBOUND_WEBHOOK_SECRET set", "INBOUND_WEBHOOK_SECRET unset/default: the inbound-reply webhook rejects everything", "warn")
    check(is_true(g(be, "TRUST_PROXY_HEADERS")), A, "TRUST_PROXY_HEADERS=true", "TRUST_PROXY_HEADERS should be true behind Render's proxy (rate limits see real IPs)", "warn")
    email = g(be, "RESEND_API_KEY") or (g(be, "SMTP_HOST") and g(be, "SMTP_USER") and g(be, "SMTP_PASSWORD"))
    check(bool(email), A, "Transactional email configured", "No RESEND_API_KEY or SMTP: signup verification and password reset emails can't be sent")
    sender = g(be, "EMAIL_FROM")
    check(bool(sender) and sender != "onboarding@resend.dev", A, "EMAIL_FROM is your domain", "EMAIL_FROM is Resend's test sender; use an address on your verified domain")
    check(bool(g(be, "ANTHROPIC_API_KEY")), A, "Claude key set (AI writing)", "ANTHROPIC_API_KEY empty: AI ideas, copy, scripts, messages and scans are off", "warn")
    for flag in ("EMAIL_DRY_RUN", "WHATSAPP_DRY_RUN", "UNIPILE_DRY_RUN", "CONTENT_POST_DRY_RUN"):
        v = g(be, flag)
        good = f"{flag}=false (real sends)" if v else f"{flag} unset: follows DEV_MODE (real sends once DEV_MODE=false)"
        check(not is_true(v), A, good, f"{flag}=true: that channel only logs", "warn")
    media = g(be, "CONTENT_MEDIA_DIR")
    check(bool(media) and media.startswith("/var/data"), A, "CONTENT_MEDIA_DIR on the persistent disk", "CONTENT_MEDIA_DIR not on a persistent disk: uploaded/AI images vanish on every deploy (blueprint mounts /var/data)", "warn")

    F = "Features"
    pairs = [
        ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "Google: sign-in, Gmail inboxes, YouTube posting"),
        ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET", "Microsoft: Outlook / 365 inboxes"),
        ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LinkedIn: sign-in and posting via LinkedIn's API"),
        ("META_APP_ID", "META_APP_SECRET", "Meta: Instagram + Facebook Page posting"),
        ("X_CLIENT_ID", "X_CLIENT_SECRET", "X: posting via X's API"),
        ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "Reddit: posting (Reddit \"web app\") and lead capture"),
    ]
    for a, b, what in pairs:
        check(bool(g(be, a) and g(be, b)), F, f"{what}", f"{what} — off ({a} / {b} empty)", "warn")
    check(bool(g(be, "UNIPILE_API_KEY")), F, "Unipile: LinkedIn / WhatsApp DMs, LinkedIn + Instagram posting",
          "Unipile — off (UNIPILE_API_KEY empty): Chrome extension only for LinkedIn DMs", "warn")
    if g(be, "UNIPILE_API_KEY"):
        check(bool(g(be, "UNIPILE_WEBHOOK_SECRET")), F, "Unipile webhook secret set", "UNIPILE_WEBHOOK_SECRET empty: Unipile reply webhooks are rejected", "warn")

    # ---------------- web app (lead-gen-frontend) ----------------
    W = "Web app"
    api_url = g(fe, "NEXT_PUBLIC_API_URL")
    check(https_url(api_url), W, "NEXT_PUBLIC_API_URL is the public https API", "NEXT_PUBLIC_API_URL must be the public https API URL (baked in at build time)")
    check(https_url(g(fe, "LEADNIUS_API_URL")), W, "LEADNIUS_API_URL set", "LEADNIUS_API_URL must be the https API URL (SEO sign-in bridge)")
    app_url = g(fe, "APP_URL")
    check(https_url(app_url), W, "APP_URL is the public https web app", "APP_URL must be the public https web-app URL (SEO links, emails, Search Console)")
    check(len(g(fe, "SESSION_SECRET")) >= 32, W, "SESSION_SECRET strong", "SESSION_SECRET must be 32+ characters")
    check(bool(re.fullmatch(r"[0-9a-fA-F]{64}", g(fe, "CREDENTIALS_KEY"))), W, "CREDENTIALS_KEY is 64 hex", "CREDENTIALS_KEY must be 64 hex characters (openssl rand -hex 32); never change it after launch")
    sdb = g(fe, "DATABASE_URL")
    check(bool(sdb) and not LOCAL.search(sdb), W, "SEO DATABASE_URL hosted", "DATABASE_URL (SEO database) must point at the production Postgres")
    check(g(fe, "ALLOW_SIMULATED_PROVIDER").lower() == "false", W, "Simulated AI answers off", "ALLOW_SIMULATED_PROVIDER should be false in production", "warn")
    check(bool(g(fe, "OPENROUTER_API_KEY") or g(fe, "OPENAI_API_KEY") or g(fe, "GEMINI_API_KEY") or g(fe, "PERPLEXITY_API_KEY")),
          W, "AI provider for SEO answers + AI images", "No OPENROUTER/OPENAI/GEMINI/PERPLEXITY key: SEO AI checks and AI images are off")
    check(bool(g(fe, "DATAFORSEO_LOGIN") and g(fe, "DATAFORSEO_PASSWORD")), W, "DataForSEO set", "DataForSEO empty: SEO keyword and ranking data are limited", "warn")
    fe_mail = g(fe, "RESEND_API_KEY") or (g(fe, "SMTP_HOST") and g(fe, "SMTP_USER") and g(fe, "SMTP_PASS"))
    check(bool(fe_mail and g(fe, "EMAIL_FROM")), W, "SEO emails configured", "SEO emails (monthly reports, alerts) off: set SMTP_HOST/USER/PASS or RESEND_API_KEY and EMAIL_FROM", "warn")
    check(g(fe, "NEXT_MANUAL_SIG_HANDLE").lower() == "true", W, "NEXT_MANUAL_SIG_HANDLE=true", "NEXT_MANUAL_SIG_HANDLE=true lets the SEO worker finish jobs on deploys", "warn")
    worker = g(fe, "RUN_WORKER_IN_APP").lower()
    out.append(("warn", W, "RUN_WORKER_IN_APP=false: run the separate SEO worker service too (npm run seo:worker:prod), or SEO checks never run")
               if worker == "false" else ("ok", W, "SEO worker runs inside the web app (keep the web service at one instance)"))

    # ---------------- the two apps agree ----------------
    X = "Consistency"
    fu, au = g(be, "FRONTEND_URL").rstrip("/"), app_url.rstrip("/")
    if fu and au:
        check(fu == au, X, "API FRONTEND_URL = web APP_URL", f"API FRONTEND_URL and web APP_URL differ", "warn")
    if bu and api_url:
        check(bu.rstrip("/") == api_url.rstrip("/"), X, "API BACKEND_URL = web NEXT_PUBLIC_API_URL", "API BACKEND_URL and web NEXT_PUBLIC_API_URL differ", "warn")
    if api_url and g(fe, "LEADNIUS_API_URL"):
        check(api_url.rstrip("/") == g(fe, "LEADNIUS_API_URL").rstrip("/"), X, "NEXT_PUBLIC_API_URL = LEADNIUS_API_URL", "NEXT_PUBLIC_API_URL and LEADNIUS_API_URL differ", "warn")
    return out


def urls(be: Dict[str, str], fe: Dict[str, str]) -> List[Tuple[str, str]]:
    api = (be.get("BACKEND_URL") or fe.get("NEXT_PUBLIC_API_URL") or "https://<api>").rstrip("/")
    web = (fe.get("APP_URL") or be.get("FRONTEND_URL") or "https://<app>").rstrip("/")
    return [
        ("Google OAuth (sign-in)", f"{api}/api/auth/google/callback"),
        ("Google OAuth (Gmail inbox)", f"{api}/api/integrations/oauth/callback/google"),
        ("Google OAuth (YouTube posting)", f"{api}/api/studio/oauth/callback/google"),
        ("Google OAuth (Search Console, SEO)", f"{web}/api/seo/integrations/google/callback"),
        ("Microsoft (Outlook inbox)", f"{api}/api/integrations/oauth/callback/outlook"),
        ("LinkedIn (sign-in)", f"{api}/api/auth/linkedin/callback"),
        ("LinkedIn (posting)", f"{api}/api/studio/oauth/callback/linkedin"),
        ("Meta (Instagram + Facebook posting)", f"{api}/api/studio/oauth/callback/meta"),
        ("X (posting)", f"{api}/api/studio/oauth/callback/x"),
        ("Reddit (posting)", f"{api}/api/studio/oauth/callback/reddit"),
        ("Meta WhatsApp webhook", f"{api}/api/webhooks/whatsapp"),
        ("Unipile webhook", f"{api}/api/webhooks/unipile"),
        ("Inbound replies webhook (header x-webhook-secret)", f"{api}/api/webhooks/inbound"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default=os.path.join(ROOT, "lead-gen-backend", ".env"))
    ap.add_argument("--frontend", default=os.path.join(ROOT, "lead-gen-frontend", ".env.local"))
    ap.add_argument("--strict", action="store_true", help="exit 1 when something blocks the launch")
    a = ap.parse_args()
    be, fe = load(a.backend), load(a.frontend)
    print(f"API env:     {a.backend}{'' if be else '  (not found)'}")
    print(f"Web app env: {a.frontend}{'' if fe else '  (not found)'}\n")
    results = run(be, fe)
    mark = {"ok": "  ✓", "warn": "  !", "fail": "  ✗"}
    area = None
    for status, ar, msg in results:
        if ar != area:
            area = ar
            print(f"{ar}")
        print(f"{mark[status]} {msg}")
    blockers = sum(1 for s, _, _ in results if s == "fail")
    off = sum(1 for s, _, _ in results if s == "warn")
    print(f"\n{blockers} blocker(s), {off} thing(s) switched off or worth a look.\n")
    print("Register these URLs with each provider:")
    for name, url in urls(be, fe):
        print(f"  {name:<52} {url}")
    return 1 if (a.strict and blockers) else 0


if __name__ == "__main__":
    sys.exit(main())
