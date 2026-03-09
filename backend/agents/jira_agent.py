"""
Agent B — Jira Agent (LangGraph)
=================================
Scoped to Jira ONLY via AgentCore Identity.
EXTREME LOGGING at every node, edge, and decision.
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

logger = logging.getLogger("agent.jira")


class JiraAgentState(TypedDict):
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
def scope_check(state: JiraAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔶 JIRA AGENT — NODE: scope_check")
    logger.info("━" * 60)
    logger.info(f"  Input URL:      {state['url']}")
    logger.info(f"  Session ID:     {state['session_id'][:12]}...")
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
        logger.info(f"  ✅ SCOPE PASSED — Jira agent is authorized for this URL")
        logger.info(f"  Next: routing to 'check_auth' node")
        logger.info("━" * 60)

        return {
            "provider": provider,
            "authorized": True,
            "status": "scope_passed",
            "messages": [
                f"✅ [scope_check] Jira agent identity {identity_client.identity_arn} authorized for {url}",
                f"   Detected provider: {provider} | Allowed: jira | Match: YES",
            ],
        }
    except UnauthorizedProviderError as e:
        elapsed = (time.time() - start) * 1000
        detected = identity_client.detect_provider(url) or "unknown"

        logger.error(f"  enforce_scope() REJECTED ({elapsed:.1f}ms)")
        logger.error(f"  Detected provider: {detected}")
        logger.error(f"  Agent's allowed:   jira")
        logger.error(f"  🚫 UNAUTHORIZED — routing to 'format_rejection' node")
        logger.info("━" * 60)

        return {
            "provider": detected,
            "authorized": False,
            "status": "rejected",
            "error": str(e),
            "messages": [
                f"🚫 [scope_check] REJECTED — Jira agent cannot access '{detected}' resources",
                f"   Identity: {identity_client.identity_arn}",
                f"   Reason: Agent scoped to 'jira' only, URL belongs to '{detected}'",
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
def check_auth(state: JiraAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔶 JIRA AGENT — NODE: check_auth")
    logger.info("━" * 60)
    logger.info(f"  Session ID: {state['session_id'][:12]}...")
    logger.info(f"  Checking if OAuth token exists for this session...")

    identity_client = _get_identity_client()
    session_id = state["session_id"]

    token = identity_client.get_cached_token(session_id)
    if token:
        logger.info(f"  ✅ TOKEN FOUND — user has already authorized Jira")
        logger.info(f"    token_type:  {token.get('token_type', 'N/A')}")
        logger.info(f"    cloud_id:    {token.get('cloud_id', 'N/A')[:12]}...")
        logger.info(f"    cloud_name:  {token.get('cloud_name', 'N/A')}")
        logger.info(f"  Next: routing to 'fetch_jira_data' node")
        logger.info("━" * 60)
        return {
            "status": "authenticated",
            "messages": [
                f"🔑 [check_auth] Jira OAuth token found for session",
                f"   Cloud: {token.get('cloud_name', 'N/A')} ({token.get('cloud_id', 'N/A')[:12]}...)",
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
                f"🔐 [check_auth] OAuth authorization required for Jira",
                f"   User must click the auth link to grant access",
                f"   AgentCore Identity will broker the OAuth flow",
            ],
        }


# ═══════════════════════════════════════════
#  NODE: fetch_jira_data
# ═══════════════════════════════════════════
def fetch_jira_data(state: JiraAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔶 JIRA AGENT — NODE: fetch_jira_data")
    logger.info("━" * 60)
    logger.info(f"  URL: {state['url']}")
    logger.info(f"  Retrieving token from cache...")

    identity_client = _get_identity_client()
    token_data = identity_client.get_cached_token(state["session_id"])

    if not token_data:
        logger.error(f"  ✖ No token available — cannot call Jira API")
        logger.info("━" * 60)
        return {
            "status": "error",
            "error": "No token available",
            "messages": ["❌ [fetch_jira_data] Cannot fetch — no OAuth token"],
        }

    url = state["url"]
    access_token = token_data.get("access_token", "")
    cloud_id = token_data.get("cloud_id", "")

    logger.info(f"  Token retrieved. cloud_id={cloud_id[:12]}...")
    logger.info(f"  Calling Jira API...")

    start = time.time()
    result = _call_jira_api(url, access_token, cloud_id)
    elapsed = (time.time() - start) * 1000

    logger.info(f"  Jira API response ({elapsed:.1f}ms):")
    for k, v in result.items():
        logger.info(f"    {k}: {str(v)[:80]}")
    logger.info(f"  Next: routing to 'format_success' node")
    logger.info("━" * 60)

    return {
        "status": "complete",
        "result": result,
        "messages": [
            f"📦 [fetch_jira_data] Jira API call complete ({elapsed:.0f}ms)",
            f"   Type: {result.get('type', 'unknown')}",
        ],
    }


# ═══════════════════════════════════════════
#  NODE: format_rejection
# ═══════════════════════════════════════════
def format_rejection(state: JiraAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔶 JIRA AGENT — NODE: format_rejection")
    logger.info("━" * 60)
    logger.info(f"  Building rejection response...")
    logger.info(f"  Error: {state.get('error', 'N/A')}")
    logger.info(f"  → END (terminal node)")
    logger.info("━" * 60)

    return {
        "result": {
            "agent": "jira_agent",
            "action": "REJECTED",
            "reason": state.get("error", "Unauthorized provider"),
            "url": state["url"],
            "identity_arn": _get_identity_client().identity_arn,
            "agent_scope": "jira",
            "url_provider": state.get("provider", "unknown"),
            "hint": "This URL should be handled by the GitHub Agent (Agent A).",
        },
        "messages": ["📋 [format_rejection] Rejection payload built → END"],
    }


# ═══════════════════════════════════════════
#  NODE: format_auth_required
# ═══════════════════════════════════════════
def format_auth_required(state: JiraAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔶 JIRA AGENT — NODE: format_auth_required")
    logger.info("━" * 60)
    logger.info(f"  Auth URL: {state.get('auth_url', 'N/A')[:60]}...")
    logger.info(f"  → END (terminal node)")
    logger.info("━" * 60)

    return {
        "result": {
            "agent": "jira_agent",
            "action": "AUTH_REQUIRED",
            "auth_url": state.get("auth_url", ""),
            "provider": "jira",
            "message": "Please authorize Jira access to continue.",
        },
        "messages": ["📋 [format_auth_required] Auth-required payload built → END"],
    }


# ═══════════════════════════════════════════
#  NODE: format_success
# ═══════════════════════════════════════════
def format_success(state: JiraAgentState) -> dict:
    logger.info("")
    logger.info("━" * 60)
    logger.info("🔶 JIRA AGENT — NODE: format_success")
    logger.info("━" * 60)
    logger.info(f"  Wrapping result with agent metadata...")
    logger.info(f"  → END (terminal node)")
    logger.info("━" * 60)

    return {
        "result": {
            **state.get("result", {}),
            "agent": "jira_agent",
            "action": "SUCCESS",
        },
        "messages": ["📋 [format_success] Success payload built → END"],
    }


# ═══════════════════════════════════════════
#  ROUTING FUNCTIONS
# ═══════════════════════════════════════════
def route_after_scope(state: JiraAgentState) -> Literal["check_auth", "format_rejection"]:
    decision = "check_auth" if state.get("authorized") else "format_rejection"
    logger.info(f"  🔀 [route_after_scope] authorized={state.get('authorized')} → routing to '{decision}'")
    return decision


def route_after_auth(state: JiraAgentState) -> Literal["fetch_jira_data", "format_auth_required"]:
    decision = "fetch_jira_data" if state.get("status") == "authenticated" else "format_auth_required"
    logger.info(f"  🔀 [route_after_auth] status='{state.get('status')}' → routing to '{decision}'")
    return decision


# ═══════════════════════════════════════════
#  GRAPH BUILDER
# ═══════════════════════════════════════════
def build_jira_agent_graph() -> StateGraph:
    logger.info("[build_jira_agent_graph] Constructing LangGraph state machine...")
    graph = StateGraph(JiraAgentState)

    logger.info("  Adding nodes: scope_check, check_auth, fetch_jira_data, format_rejection, format_auth_required, format_success")
    graph.add_node("scope_check", scope_check)
    graph.add_node("check_auth", check_auth)
    graph.add_node("fetch_jira_data", fetch_jira_data)
    graph.add_node("format_rejection", format_rejection)
    graph.add_node("format_auth_required", format_auth_required)
    graph.add_node("format_success", format_success)

    logger.info("  Setting entry point: scope_check")
    graph.set_entry_point("scope_check")

    logger.info("  Adding conditional edges: scope_check → [check_auth | format_rejection]")
    graph.add_conditional_edges("scope_check", route_after_scope)
    logger.info("  Adding conditional edges: check_auth → [fetch_jira_data | format_auth_required]")
    graph.add_conditional_edges("check_auth", route_after_auth)

    logger.info("  Adding terminal edges")
    graph.add_edge("fetch_jira_data", "format_success")
    graph.add_edge("format_rejection", END)
    graph.add_edge("format_auth_required", END)
    graph.add_edge("format_success", END)

    logger.info("[build_jira_agent_graph] Graph construction complete")
    return graph


_compiled_graph = None


def get_jira_agent():
    global _compiled_graph
    if _compiled_graph is None:
        logger.info("[get_jira_agent] First call — compiling graph...")
        _compiled_graph = build_jira_agent_graph().compile()
        logger.info("[get_jira_agent] Graph compiled and cached")
    return _compiled_graph


_identity_client = None


def _get_identity_client() -> AgentCoreIdentityClient:
    global _identity_client
    if _identity_client is None:
        arn = os.getenv("JIRA_AGENT_IDENTITY_ARN", "")
        logger.info(f"[_get_identity_client] Creating Jira AgentCore client (ARN={arn[:40]}...)")
        _identity_client = AgentCoreIdentityClient(identity_arn=arn, allowed_provider="jira")
    return _identity_client


def get_identity_client() -> AgentCoreIdentityClient:
    return _get_identity_client()


def _call_jira_api(url: str, access_token: str, cloud_id: str) -> dict:
    logger.info(f"[_call_jira_api] Parsing URL: {url}")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    parts = url.replace("https://", "").replace("http://", "").split("/")
    logger.info(f"  URL parts: {parts}")

    try:
        issue_key = None
        for i, part in enumerate(parts):
            if part == "browse" and i + 1 < len(parts):
                issue_key = parts[i + 1].split("?")[0]
                logger.info(f"  Found issue key via /browse/: {issue_key}")
                break
            if "-" in part and part.split("-")[-1].isdigit():
                issue_key = part.split("?")[0]
                logger.info(f"  Found issue key via pattern: {issue_key}")

        api_base = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
        logger.info(f"  API base: {api_base}")

        if issue_key:
            endpoint = f"{api_base}/issue/{issue_key}"
            logger.info(f"  Detected: Issue {issue_key}")
            logger.info(f"  GET {endpoint}")
            resp = requests.get(endpoint, headers=headers)
            logger.info(f"  Response: {resp.status_code}")
            data = resp.json()
            fields = data.get("fields", {})
            return {
                "type": "issue",
                "key": data.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "assignee": (fields.get("assignee") or {}).get("displayName"),
                "priority": (fields.get("priority") or {}).get("name"),
                "url": url,
            }
        else:
            project_key = None
            for i, part in enumerate(parts):
                if part == "projects" and i + 1 < len(parts):
                    project_key = parts[i + 1].split("?")[0]
                    break

            if project_key:
                endpoint = f"{api_base}/project/{project_key}"
                logger.info(f"  Detected: Project {project_key}")
                logger.info(f"  GET {endpoint}")
                resp = requests.get(endpoint, headers=headers)
                logger.info(f"  Response: {resp.status_code}")
                data = resp.json()
                return {
                    "type": "project",
                    "key": data.get("key"),
                    "name": data.get("name"),
                    "style": data.get("style"),
                    "url": url,
                }

            logger.warning(f"  Could not extract issue key or project key from URL")
            return {
                "type": "unknown",
                "message": "Could not parse specific resource from URL",
                "url": url,
            }

    except Exception as e:
        logger.exception(f"  Jira API call failed: {e}")
        return {"error": str(e), "url": url}
