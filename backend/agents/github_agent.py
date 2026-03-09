"""
Agent A — GitHub Agent
==================================
"""

import os
import time
import logging
from typing import TypedDict, Annotated, Literal
from operator import add

import requests
from langgraph.graph import StateGraph, END

from identity.agentcore_client import (
    AgentCoreIdentityClient,
    UnauthorizedProviderError,
    OAuthFlowRequiredError,
)

logger = logging.getLogger("agent.github")


class GitHubAgentState(TypedDict):
    url: str
    session_id: str
    status: str
    provider: str
    authorized: bool
    auth_url: str
    result: dict
    error: str
    messages: Annotated[list, add]


# ═══════════════════════════════════════════
#  NODE: scope_check
# ═══════════════════════════════════════════
def scope_check(state: GitHubAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔷 GITHUB AGENT — NODE: scope_check")
    logger.info("━" * 60)
    logger.info(f"  Input URL:    {state['url']}")
    logger.info(f"  Session ID:   {state['session_id'][:12]}...")
    logger.info(f"  Current status: {state.get('status', 'none')}")
    logger.info("")
    logger.info("  Calling AgentCore Identity enforce_scope()...")

    identity_client = _get_identity_client()
    url = state["url"]
    start = time.time()

    try:
        provider = identity_client.enforce_scope(url)
        elapsed = (time.time() - start) * 1000

        logger.info(f"  enforce_scope() returned: '{provider}' ({elapsed:.1f}ms)")
        logger.info(f"  ✅ SCOPE PASSED — GitHub agent is authorized for this URL")
        logger.info(f"  Next: routing to 'check_auth' node")
        logger.info("━" * 60)

        return {
            "provider": provider,
            "authorized": True,
            "status": "scope_passed",
            "messages": [
                f"✅ [scope_check] GitHub agent identity {identity_client.identity_arn} authorized for {url}",
                f"   Detected provider: {provider} | Allowed: github | Match: YES",
            ],
        }
    except UnauthorizedProviderError as e:
        elapsed = (time.time() - start) * 1000
        detected = identity_client.detect_provider(url) or "unknown"

        logger.error(f"  enforce_scope() REJECTED ({elapsed:.1f}ms)")
        logger.error(f"  Detected provider: {detected}")
        logger.error(f"  Agent's allowed:   github")
        logger.error(f"  🚫 UNAUTHORIZED — routing to 'format_rejection' node")
        logger.info("━" * 60)

        return {
            "provider": detected,
            "authorized": False,
            "status": "rejected",
            "error": str(e),
            "messages": [
                f"🚫 [scope_check] REJECTED — GitHub agent cannot access '{detected}' resources",
                f"   Identity: {identity_client.identity_arn}",
                f"   Reason: Agent scoped to 'github' only, URL belongs to '{detected}'",
                f"   AgentCore Identity blocked this request at the identity layer",
            ],
        }
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.exception(f"  enforce_scope() ERROR ({elapsed:.1f}ms): {e}")
        logger.info("━" * 60)

        return {
            "authorized": False,
            "status": "error",
            "error": str(e),
            "messages": [f"❌ [scope_check] Error: {e}"],
        }


# ═══════════════════════════════════════════
#  NODE: check_auth
# ═══════════════════════════════════════════
def check_auth(state: GitHubAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔷 GITHUB AGENT — NODE: check_auth")
    logger.info("━" * 60)
    logger.info(f"  Session ID: {state['session_id'][:12]}...")
    logger.info(f"  Checking if OAuth token exists for this session...")

    identity_client = _get_identity_client()
    session_id = state["session_id"]

    token = identity_client.get_cached_token(session_id)
    if token:
        logger.info(f"  ✅ TOKEN FOUND — user has already authorized GitHub")
        logger.info(f"    token_type:  {token.get('token_type', 'N/A')}")
        logger.info(f"    scope:       {token.get('scope', 'N/A')}")
        logger.info(f"  Next: routing to 'fetch_github_data' node")
        logger.info("━" * 60)
        return {
            "status": "authenticated",
            "messages": [
                f"🔑 [check_auth] GitHub OAuth token found for session",
                f"   Token scope: {token.get('scope', 'N/A')}",
            ],
        }

    logger.info(f"  ✖ NO TOKEN — need to initiate OAuth flow")
    try:
        identity_client.request_token(session_id)
        return {"status": "authenticated", "messages": ["🔑 [check_auth] Token acquired from AgentCore"]}
    except OAuthFlowRequiredError as e:
        logger.info(f"  🔐 OAuth flow required")
        logger.info(f"    Auth URL: {e.auth_url[:80]}...")
        logger.info(f"  Next: routing to 'format_auth_required' node")
        logger.info("━" * 60)
        return {
            "status": "needs_auth",
            "auth_url": e.auth_url,
            "messages": [
                f"🔐 [check_auth] OAuth authorization required for GitHub",
                f"   User must click the auth link to grant access",
                f"   AgentCore Identity will broker the OAuth flow",
            ],
        }


# ═══════════════════════════════════════════
#  NODE: fetch_github_data
# ═══════════════════════════════════════════
def fetch_github_data(state: GitHubAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔷 GITHUB AGENT — NODE: fetch_github_data")
    logger.info("━" * 60)
    logger.info(f"  URL: {state['url']}")
    logger.info(f"  Retrieving token from cache...")

    identity_client = _get_identity_client()
    token_data = identity_client.get_cached_token(state["session_id"])

    if not token_data:
        logger.error(f"  ✖ No token available — cannot call GitHub API")
        logger.info("━" * 60)
        return {
            "status": "error",
            "error": "No token available",
            "messages": ["❌ [fetch_github_data] Cannot fetch — no OAuth token"],
        }

    url = state["url"]
    access_token = token_data.get("access_token", "")
    logger.info(f"  Token retrieved. Calling GitHub API...")

    start = time.time()
    result = _call_github_api(url, access_token)
    elapsed = (time.time() - start) * 1000

    logger.info(f"  GitHub API response ({elapsed:.1f}ms):")
    for k, v in result.items():
        logger.info(f"    {k}: {str(v)[:80]}")
    logger.info(f"  Next: routing to 'format_success' node")
    logger.info("━" * 60)

    return {
        "status": "complete",
        "result": result,
        "messages": [
            f"📦 [fetch_github_data] GitHub API call complete ({elapsed:.0f}ms)",
            f"   Type: {result.get('type', 'unknown')}",
        ],
    }


# ═══════════════════════════════════════════
#  NODE: format_rejection
# ═══════════════════════════════════════════
def format_rejection(state: GitHubAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔷 GITHUB AGENT — NODE: format_rejection")
    logger.info("━" * 60)
    logger.info(f"  Building rejection response...")
    logger.info(f"  Error: {state.get('error', 'N/A')}")
    logger.info(f"  → END (terminal node)")
    logger.info("━" * 60)

    return {
        "result": {
            "agent": "github_agent",
            "action": "REJECTED",
            "reason": state.get("error", "Unauthorized provider"),
            "url": state["url"],
            "identity_arn": _get_identity_client().identity_arn,
            "agent_scope": "github",
            "url_provider": state.get("provider", "unknown"),
            "hint": "This URL should be handled by the Jira Agent (Agent B).",
        },
        "messages": ["📋 [format_rejection] Rejection payload built → END"],
    }


# ═══════════════════════════════════════════
#  NODE: format_auth_required
# ═══════════════════════════════════════════
def format_auth_required(state: GitHubAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔷 GITHUB AGENT — NODE: format_auth_required")
    logger.info("━" * 60)
    logger.info(f"  Auth URL: {state.get('auth_url', 'N/A')[:60]}...")
    logger.info(f"  → END (terminal node)")
    logger.info("━" * 60)

    return {
        "result": {
            "agent": "github_agent",
            "action": "AUTH_REQUIRED",
            "auth_url": state.get("auth_url", ""),
            "provider": "github",
            "message": "Please authorize GitHub access to continue.",
        },
        "messages": ["📋 [format_auth_required] Auth-required payload built → END"],
    }


# ═══════════════════════════════════════════
#  NODE: format_success
# ═══════════════════════════════════════════
def format_success(state: GitHubAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔷 GITHUB AGENT — NODE: format_success")
    logger.info("━" * 60)
    logger.info(f"  Wrapping result with agent metadata...")
    logger.info(f"  → END (terminal node)")
    logger.info("━" * 60)

    return {
        "result": {
            **state.get("result", {}),
            "agent": "github_agent",
            "action": "SUCCESS",
        },
        "messages": ["📋 [format_success] Success payload built → END"],
    }


# ═══════════════════════════════════════════
#  ROUTING FUNCTIONS
# ═══════════════════════════════════════════
def route_after_scope(state: GitHubAgentState) -> Literal["check_auth", "format_rejection"]:
    decision = "check_auth" if state.get("authorized") else "format_rejection"
    logger.info(f"  🔀 [route_after_scope] authorized={state.get('authorized')} → routing to '{decision}'")
    return decision


def route_after_auth(state: GitHubAgentState) -> Literal["fetch_github_data", "format_auth_required"]:
    decision = "fetch_github_data" if state.get("status") == "authenticated" else "format_auth_required"
    logger.info(f"  🔀 [route_after_auth] status='{state.get('status')}' → routing to '{decision}'")
    return decision


# ═══════════════════════════════════════════
#  GRAPH BUILDER
# ═══════════════════════════════════════════
def build_github_agent_graph() -> StateGraph:
    logger.info("[build_github_agent_graph] Constructing LangGraph state machine...")
    graph = StateGraph(GitHubAgentState)

    logger.info("  Adding nodes: scope_check, check_auth, fetch_github_data, format_rejection, format_auth_required, format_success")
    graph.add_node("scope_check", scope_check)
    graph.add_node("check_auth", check_auth)
    graph.add_node("fetch_github_data", fetch_github_data)
    graph.add_node("format_rejection", format_rejection)
    graph.add_node("format_auth_required", format_auth_required)
    graph.add_node("format_success", format_success)

    logger.info("  Setting entry point: scope_check")
    graph.set_entry_point("scope_check")

    logger.info("  Adding conditional edges: scope_check → [check_auth | format_rejection]")
    graph.add_conditional_edges("scope_check", route_after_scope)
    logger.info("  Adding conditional edges: check_auth → [fetch_github_data | format_auth_required]")
    graph.add_conditional_edges("check_auth", route_after_auth)

    logger.info("  Adding terminal edges: fetch_github_data→format_success→END, format_rejection→END, format_auth_required→END")
    graph.add_edge("fetch_github_data", "format_success")
    graph.add_edge("format_rejection", END)
    graph.add_edge("format_auth_required", END)
    graph.add_edge("format_success", END)

    logger.info("[build_github_agent_graph] Graph construction complete")
    return graph


_compiled_graph = None

def get_github_agent():
    global _compiled_graph
    if _compiled_graph is None:
        logger.info("[get_github_agent] First call — compiling graph...")
        _compiled_graph = build_github_agent_graph().compile()
        logger.info("[get_github_agent] Graph compiled and cached")
    return _compiled_graph


_identity_client = None

def _get_identity_client() -> AgentCoreIdentityClient:
    global _identity_client
    if _identity_client is None:
        arn = os.getenv("GITHUB_AGENT_IDENTITY_ARN", "")
        logger.info(f"[_get_identity_client] Creating GitHub AgentCore client (ARN={arn[:40]}...)")
        _identity_client = AgentCoreIdentityClient(identity_arn=arn, allowed_provider="github")
    return _identity_client

def get_identity_client() -> AgentCoreIdentityClient:
    return _get_identity_client()


def _call_github_api(url: str, access_token: str) -> dict:
    logger.info(f"[_call_github_api] Parsing URL: {url}")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    parts = url.replace("https://", "").replace("http://", "").split("/")
    logger.info(f"  URL parts: {parts}")

    if len(parts) < 3:
        logger.warning(f"  Cannot parse — too few path segments")
        return {"error": "Could not parse GitHub URL", "url": url}

    owner, repo = parts[1], parts[2]
    api_base = f"https://api.github.com/repos/{owner}/{repo}"
    logger.info(f"  Owner: {owner}, Repo: {repo}")
    logger.info(f"  API base: {api_base}")

    try:
        if len(parts) >= 5 and parts[3] == "issues":
            issue_num = parts[4]
            endpoint = f"{api_base}/issues/{issue_num}"
            logger.info(f"  Detected: Issue #{issue_num}")
            logger.info(f"  GET {endpoint}")
            resp = requests.get(endpoint, headers=headers)
            logger.info(f"  Response: {resp.status_code}")
            data = resp.json()
            return {"type": "issue", "title": data.get("title"), "state": data.get("state"), "body": data.get("body", "")[:500], "url": url}

        elif len(parts) >= 5 and parts[3] == "pull":
            pr_num = parts[4]
            endpoint = f"{api_base}/pulls/{pr_num}"
            logger.info(f"  Detected: PR #{pr_num}")
            logger.info(f"  GET {endpoint}")
            resp = requests.get(endpoint, headers=headers)
            logger.info(f"  Response: {resp.status_code}")
            data = resp.json()
            return {"type": "pull_request", "title": data.get("title"), "state": data.get("state"), "mergeable": data.get("mergeable"), "url": url}

        else:
            logger.info(f"  Detected: Repository overview")
            logger.info(f"  GET {api_base}")
            resp = requests.get(api_base, headers=headers)
            logger.info(f"  Response: {resp.status_code}")
            data = resp.json()
            return {"type": "repository", "name": data.get("full_name"), "description": data.get("description"), "stars": data.get("stargazers_count"), "language": data.get("language"), "url": url}

    except Exception as e:
        logger.exception(f"  GitHub API call failed: {e}")
        return {"error": str(e), "url": url}
