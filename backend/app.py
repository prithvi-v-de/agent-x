"""
AgentCore Identity Showcase - Flask Backend
EXTREME LOGGING VERSION
"""

import os
import sys
import json
import uuid
import time
import logging
import traceback
import requests
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory, redirect, session
from dotenv import load_dotenv

load_dotenv()

# ==================================================================
#  LOGGING SETUP
# ==================================================================

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)

app_logger = logging.getLogger("app.flask")
route_logger = logging.getLogger("app.routes")
oauth_logger = logging.getLogger("app.oauth")
agent_logger = logging.getLogger("app.agents")

logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)

# ==================================================================
#  STARTUP LOGGING
# ==================================================================

app_logger.info("")
app_logger.info("=" * 70)
app_logger.info("  AGENTCORE IDENTITY SHOWCASE — STARTING UP")
app_logger.info("=" * 70)
app_logger.info(f"  AWS_REGION:                {os.getenv('AWS_REGION', 'NOT SET')}")
app_logger.info(f"  GITHUB_AGENT_IDENTITY_ARN: {os.getenv('GITHUB_AGENT_IDENTITY_ARN', 'NOT SET')[:50]}...")
app_logger.info(f"  JIRA_AGENT_IDENTITY_ARN:   {os.getenv('JIRA_AGENT_IDENTITY_ARN', 'NOT SET')[:50]}...")
app_logger.info(f"  GITHUB_CLIENT_ID:          {os.getenv('GITHUB_CLIENT_ID', 'NOT SET')[:8]}...")
app_logger.info(f"  JIRA_CLIENT_ID:            {os.getenv('JIRA_CLIENT_ID', 'NOT SET')[:8]}...")
app_logger.info(f"  APP_URL:                   {os.getenv('APP_URL', 'NOT SET')}")
app_logger.info(f"  PORT:                      {os.getenv('PORT', '8080')}")
app_logger.info(f"  FLASK_SECRET_KEY:          {'SET' if os.getenv('FLASK_SECRET_KEY') else 'USING DEFAULT'}")
app_logger.info("=" * 70)
app_logger.info("")

from agents.github_agent import get_github_agent, get_identity_client as get_github_identity
from agents.jira_agent import get_jira_agent, get_identity_client as get_jira_identity

app_logger.info("Agent modules imported successfully")

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
app_logger.info(f"Flask app created. Static folder: {app.static_folder}")


# ==================================================================
#  REQUEST/RESPONSE MIDDLEWARE
# ==================================================================

@app.before_request
def log_request():
    request._start_time = time.time()
    request._request_id = str(uuid.uuid4())[:8]

    route_logger.info("")
    route_logger.info("+" + "-" * 64 + "+")
    route_logger.info(f"| INCOMING [{request._request_id}]  {request.method}  {request.path}")
    route_logger.info(f"|   Full URL:      {request.url}")
    route_logger.info(f"|   Remote IP:     {request.remote_addr}")
    route_logger.info(f"|   User-Agent:    {request.headers.get('User-Agent', 'N/A')[:60]}")
    route_logger.info(f"|   Content-Type:  {request.content_type or 'N/A'}")

    if request.args:
        route_logger.info(f"|   Query Params:")
        for k, v in request.args.items():
            route_logger.info(f"|     {k}: {v[:60]}{'...' if len(v) > 60 else ''}")

    if request.is_json:
        try:
            body = request.get_json(silent=True)
            if body:
                route_logger.info(f"|   JSON Body:")
                for k, v in body.items():
                    route_logger.info(f"|     {k}: {str(v)[:80]}")
        except Exception:
            pass

    route_logger.info("+" + "-" * 64 + "+")


@app.after_request
def log_response(response):
    elapsed = (time.time() - getattr(request, '_start_time', time.time())) * 1000
    req_id = getattr(request, '_request_id', '?')
    route_logger.info(f"  <- RESPONSE [{req_id}] {response.status_code} | {elapsed:.1f}ms | {request.method} {request.path}")
    if response.status_code >= 400:
        route_logger.warning(f"  ! Non-success status: {response.status_code}")
    return response


# ==================================================================
#  ROUTE: Serve Frontend
# ==================================================================

@app.route("/")
def serve_frontend():
    route_logger.info("Serving frontend index.html")
    return send_from_directory(app.static_folder, "index.html")


# ==================================================================
#  ROUTE: /api/process  (MAIN ENDPOINT)
# ==================================================================

@app.route("/api/process", methods=["POST"])
def process_url():
    agent_logger.info("")
    agent_logger.info("=" * 66)
    agent_logger.info("  /api/process  —  DUAL AGENT EXECUTION START")
    agent_logger.info("=" * 66)

    data = request.get_json()
    url = data.get("url", "").strip()
    session_id = data.get("session_id") or session.get("session_id") or str(uuid.uuid4())
    session["session_id"] = session_id

    agent_logger.info(f"  Input URL:    '{url}'")
    agent_logger.info(f"  Session ID:   {session_id}")

    if not url:
        agent_logger.warning("  X  No URL provided — returning 400")
        return jsonify({"error": "No URL provided"}), 400

    if not (url.startswith("http://") or url.startswith("https://")):
        old_url = url
        url = "https://" + url
        agent_logger.info(f"  Auto-prefixed: '{old_url}' -> '{url}'")

    results = {}

    # ───── AGENT A: GitHub Agent ─────
    agent_logger.info("")
    agent_logger.info("  +-------------------------------------------------+")
    agent_logger.info("  |  INVOKING AGENT A  —  GitHub Agent (LangGraph)   |")
    agent_logger.info("  +-------------------------------------------------+")

    try:
        github_agent = get_github_agent()
        agent_logger.info("  Graph compiled. Invoking with initial state...")

        gh_start = time.time()
        github_result = github_agent.invoke({
            "url": url, "session_id": session_id, "status": "", "provider": "",
            "authorized": False, "auth_url": "", "result": {}, "error": "", "messages": [],
        })
        gh_elapsed = (time.time() - gh_start) * 1000

        agent_logger.info(f"  Agent A complete ({gh_elapsed:.1f}ms)")
        agent_logger.info(f"    status:     {github_result.get('status', 'N/A')}")
        agent_logger.info(f"    action:     {github_result.get('result', {}).get('action', 'N/A')}")
        agent_logger.info(f"    authorized: {github_result.get('authorized', 'N/A')}")
        agent_logger.info(f"    trace count:{len(github_result.get('messages', []))}")
        for i, msg in enumerate(github_result.get("messages", [])):
            agent_logger.info(f"      trace[{i}]: {msg}")

        results["github_agent"] = {
            "result": github_result.get("result", {}),
            "trace": github_result.get("messages", []),
            "status": github_result.get("status", "unknown"),
        }
    except Exception as e:
        agent_logger.exception(f"  AGENT A CRASHED: {e}")
        results["github_agent"] = {
            "result": {"action": "ERROR", "error": str(e)},
            "trace": [f"X Agent error: {e}"], "status": "error",
        }

    # ───── AGENT B: Jira Agent ─────
    agent_logger.info("")
    agent_logger.info("  +-------------------------------------------------+")
    agent_logger.info("  |  INVOKING AGENT B  —  Jira Agent (LangGraph)     |")
    agent_logger.info("  +-------------------------------------------------+")

    try:
        jira_agent = get_jira_agent()
        agent_logger.info("  Graph compiled. Invoking with initial state...")

        jira_start = time.time()
        jira_result = jira_agent.invoke({
            "url": url, "session_id": session_id, "status": "", "provider": "",
            "authorized": False, "auth_url": "", "result": {}, "error": "", "messages": [],
        })
        jira_elapsed = (time.time() - jira_start) * 1000

        agent_logger.info(f"  Agent B complete ({jira_elapsed:.1f}ms)")
        agent_logger.info(f"    status:     {jira_result.get('status', 'N/A')}")
        agent_logger.info(f"    action:     {jira_result.get('result', {}).get('action', 'N/A')}")
        agent_logger.info(f"    authorized: {jira_result.get('authorized', 'N/A')}")
        agent_logger.info(f"    trace count:{len(jira_result.get('messages', []))}")
        for i, msg in enumerate(jira_result.get("messages", [])):
            agent_logger.info(f"      trace[{i}]: {msg}")

        results["jira_agent"] = {
            "result": jira_result.get("result", {}),
            "trace": jira_result.get("messages", []),
            "status": jira_result.get("status", "unknown"),
        }
    except Exception as e:
        agent_logger.exception(f"  AGENT B CRASHED: {e}")
        results["jira_agent"] = {
            "result": {"action": "ERROR", "error": str(e)},
            "trace": [f"X Agent error: {e}"], "status": "error",
        }

    # ───── SUMMARY ─────
    agent_logger.info("")
    agent_logger.info("=" * 66)
    agent_logger.info("  EXECUTION SUMMARY")
    agent_logger.info(f"  URL:      {url[:55]}")
    agent_logger.info(f"  Agent A:  {results['github_agent']['result'].get('action', '?'):12s} (GitHub Agent)")
    agent_logger.info(f"  Agent B:  {results['jira_agent']['result'].get('action', '?'):12s} (Jira Agent)")
    agent_logger.info("=" * 66)
    agent_logger.info("")

    return jsonify({"url": url, "session_id": session_id, "agents": results})


# ==================================================================
#  ROUTE: GitHub OAuth Callback
# ==================================================================

@app.route("/api/auth/github/callback")
def github_oauth_callback():
    oauth_logger.info("")
    oauth_logger.info("=" * 60)
    oauth_logger.info("  GITHUB OAUTH CALLBACK")
    oauth_logger.info("=" * 60)

    code = request.args.get("code")
    state_raw = request.args.get("state", "{}")
    error = request.args.get("error")

    oauth_logger.info(f"  Code present:  {bool(code)}")
    oauth_logger.info(f"  Error param:   {error or 'none'}")

    if error:
        oauth_logger.error(f"  X  GitHub returned error: {error}")
        return redirect(f"/?error={error}&provider=github")

    try:
        state = json.loads(state_raw)
        oauth_logger.info(f"  State parsed: session={state.get('session_id', 'N/A')[:12]}...")
    except json.JSONDecodeError:
        state = {}

    session_id = state.get("session_id", session.get("session_id", ""))

    if not code:
        oauth_logger.error("  X  No authorization code")
        return redirect(f"/?error=no_code&provider=github")

    oauth_logger.info("  Exchanging code for token...")
    try:
        t0 = time.time()
        resp = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": os.getenv("GITHUB_CLIENT_ID"),
                "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
                "code": code,
            },
        )
        ms = (time.time() - t0) * 1000
        token_data = resp.json()

        oauth_logger.info(f"  Exchange: {resp.status_code} ({ms:.1f}ms)")
        oauth_logger.info(f"    keys:       {list(token_data.keys())}")
        oauth_logger.info(f"    token_type: {token_data.get('token_type', 'N/A')}")
        oauth_logger.info(f"    scope:      {token_data.get('scope', 'N/A')}")
        oauth_logger.info(f"    has token:  {bool(token_data.get('access_token'))}")

        if "access_token" not in token_data:
            oauth_logger.error(f"  X  No access_token: {json.dumps(token_data)[:200]}")
            return redirect(f"/?error=token_exchange_failed&provider=github")

        identity_client = get_github_identity()
        identity_client.store_token(session_id, token_data)

        oauth_logger.info(f"  GITHUB OAUTH COMPLETE  —  session {session_id[:12]}...")
        return redirect(f"/?auth=success&provider=github&session_id={session_id}")

    except Exception as e:
        oauth_logger.exception(f"  GITHUB OAUTH ERROR: {e}")
        return redirect(f"/?error={str(e)[:50]}&provider=github")


# ==================================================================
#  ROUTE: Jira OAuth Callback
# ==================================================================

@app.route("/api/auth/jira/callback")
def jira_oauth_callback():
    oauth_logger.info("")
    oauth_logger.info("=" * 60)
    oauth_logger.info("  JIRA OAUTH CALLBACK")
    oauth_logger.info("=" * 60)

    code = request.args.get("code")
    state_raw = request.args.get("state", "{}")
    error = request.args.get("error")

    oauth_logger.info(f"  Code present:  {bool(code)}")
    oauth_logger.info(f"  Error param:   {error or 'none'}")

    if error:
        oauth_logger.error(f"  X  Atlassian returned error: {error}")
        return redirect(f"/?error={error}&provider=jira")

    try:
        state = json.loads(state_raw)
        oauth_logger.info(f"  State parsed: session={state.get('session_id', 'N/A')[:12]}...")
    except json.JSONDecodeError:
        state = {}

    session_id = state.get("session_id", session.get("session_id", ""))

    if not code:
        oauth_logger.error("  X  No authorization code")
        return redirect(f"/?error=no_code&provider=jira")

    try:
        app_url = os.getenv("APP_URL", "http://localhost:8080")
        callback_uri = f"{app_url}/api/auth/jira/callback"

        oauth_logger.info("  Exchanging code for token...")
        t0 = time.time()
        resp = requests.post(
            "https://auth.atlassian.com/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": os.getenv("JIRA_CLIENT_ID"),
                "client_secret": os.getenv("JIRA_CLIENT_SECRET"),
                "code": code,
                "redirect_uri": callback_uri,
            },
        )
        ms = (time.time() - t0) * 1000
        token_data = resp.json()

        oauth_logger.info(f"  Exchange: {resp.status_code} ({ms:.1f}ms)")
        oauth_logger.info(f"    keys:       {list(token_data.keys())}")
        oauth_logger.info(f"    has token:  {bool(token_data.get('access_token'))}")
        oauth_logger.info(f"    expires_in: {token_data.get('expires_in', 'N/A')}")

        if "access_token" not in token_data:
            oauth_logger.error(f"  X  No access_token: {json.dumps(token_data)[:200]}")
            return redirect(f"/?error=token_exchange_failed&provider=jira")

        # Cloud ID
        oauth_logger.info("  Fetching accessible resources (cloud ID)...")
        t1 = time.time()
        cloud_resp = requests.get(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        cms = (time.time() - t1) * 1000
        resources = cloud_resp.json()

        oauth_logger.info(f"  Resources: {cloud_resp.status_code} ({cms:.1f}ms) — {len(resources)} found")
        if resources:
            token_data["cloud_id"] = resources[0]["id"]
            token_data["cloud_name"] = resources[0].get("name", "")
            oauth_logger.info(f"    cloud_id:   {resources[0]['id']}")
            oauth_logger.info(f"    cloud_name: {resources[0].get('name', 'N/A')}")

        identity_client = get_jira_identity()
        identity_client.store_token(session_id, token_data)

        oauth_logger.info(f"  JIRA OAUTH COMPLETE  —  session {session_id[:12]}...")
        return redirect(f"/?auth=success&provider=jira&session_id={session_id}")

    except Exception as e:
        oauth_logger.exception(f"  JIRA OAUTH ERROR: {e}")
        return redirect(f"/?error={str(e)[:50]}&provider=jira")


# ==================================================================
#  ROUTE: Status + Health
# ==================================================================

@app.route("/api/status")
def auth_status():
    session_id = request.args.get("session_id") or session.get("session_id", "")
    route_logger.info(f"Status check  —  session: {session_id[:12] if session_id else 'none'}")

    github_token = get_github_identity().get_cached_token(session_id)
    jira_token = get_jira_identity().get_cached_token(session_id)

    route_logger.info(f"  GitHub authenticated: {github_token is not None}")
    route_logger.info(f"  Jira authenticated:   {jira_token is not None}")

    return jsonify({
        "session_id": session_id,
        "github_agent": {"authenticated": github_token is not None, "provider": "github", "identity_arn": os.getenv("GITHUB_AGENT_IDENTITY_ARN", "not-set")},
        "jira_agent": {"authenticated": jira_token is not None, "provider": "jira", "identity_arn": os.getenv("JIRA_AGENT_IDENTITY_ARN", "not-set")},
    })


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}), 200


@app.errorhandler(404)
def not_found(e):
    route_logger.warning(f"404: {request.path}")
    return jsonify({"error": "Not found", "path": request.path}), 404


@app.errorhandler(500)
def server_error(e):
    route_logger.error(f"500: {e}\n{traceback.format_exc()}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app_logger.info(f"Starting Flask on 0.0.0.0:{port} (debug={debug})")
    app_logger.info(f"Open http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
