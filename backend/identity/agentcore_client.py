"""
AgentCore Identity Client
==========================
Wraps AWS Bedrock AgentCore Identity APIs for OAuth credential management.

LOGGING: Every function entry, exit, decision, and data transformation is logged.
"""

import os
import json
import time
import logging
from typing import Optional
from urllib.parse import urlencode

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("agentcore.identity")


class AgentCoreIdentityError(Exception):
    pass


class UnauthorizedProviderError(AgentCoreIdentityError):
    pass


class OAuthFlowRequiredError(AgentCoreIdentityError):
    def __init__(self, auth_url: str, session_uri: str):
        self.auth_url = auth_url
        self.session_uri = session_uri
        super().__init__(f"OAuth required: {auth_url}")


class AgentCoreIdentityClient:
    PROVIDER_CONFIG = {
        "github": {
            "auth_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scopes": "repo read:user read:org",
            "link_patterns": ["github.com"],
        },
        "jira": {
            "auth_url": "https://auth.atlassian.com/authorize",
            "token_url": "https://auth.atlassian.com/oauth/token",
            "scopes": "read:jira-work read:jira-user offline_access",
            "link_patterns": ["atlassian.net", "jira.com"],
            "audience": "api.atlassian.com",
        },
    }

    def __init__(self, identity_arn: str, allowed_provider: str):
        logger.info("=" * 70)
        logger.info("AGENTCORE IDENTITY CLIENT — INITIALIZING")
        logger.info("=" * 70)
        logger.info(f"  Identity ARN:     {identity_arn}")
        logger.info(f"  Allowed Provider: {allowed_provider}")
        logger.info(f"  AWS Region:       {os.getenv('AWS_REGION', 'us-east-1')}")

        self.identity_arn = identity_arn
        self.allowed_provider = allowed_provider
        self.region = os.getenv("AWS_REGION", "us-east-1")

        logger.info(f"  Creating boto3 bedrock-agent-runtime client in {self.region}...")
        self.bedrock_client = boto3.client(
            "bedrock-agent-runtime",
            region_name=self.region,
        )
        logger.info(f"  boto3 client created successfully")

        self._token_cache: dict[str, dict] = {}
        logger.info(f"  Token cache initialized (empty)")

        config = self.PROVIDER_CONFIG.get(allowed_provider, {})
        logger.info(f"  Provider config loaded:")
        logger.info(f"    auth_url:      {config.get('auth_url', 'N/A')}")
        logger.info(f"    token_url:     {config.get('token_url', 'N/A')}")
        logger.info(f"    scopes:        {config.get('scopes', 'N/A')}")
        logger.info(f"    link_patterns: {config.get('link_patterns', 'N/A')}")
        logger.info("=" * 70)
        logger.info(f"CLIENT READY — [{allowed_provider.upper()} AGENT]")
        logger.info("=" * 70)

    def detect_provider(self, url: str) -> Optional[str]:
        logger.info(f"[detect_provider] Scanning URL: {url}")
        url_lower = url.lower()
        for provider, config in self.PROVIDER_CONFIG.items():
            for pattern in config["link_patterns"]:
                logger.info(f"  Testing pattern '{pattern}' in URL... {'YES' if pattern in url_lower else 'no'}")
                if pattern in url_lower:
                    logger.info(f"[detect_provider] MATCH FOUND → provider = '{provider}'")
                    return provider
        logger.warning(f"[detect_provider] NO MATCH — URL does not belong to any known provider")
        return None

    def is_authorized_for(self, provider: str) -> bool:
        authorized = provider == self.allowed_provider
        logger.info(f"[is_authorized_for] URL provider='{provider}' vs agent allowed='{self.allowed_provider}' → {'AUTHORIZED' if authorized else 'DENIED'}")
        return authorized

    def enforce_scope(self, url: str) -> str:
        logger.info("")
        logger.info("┌" + "─" * 60 + "┐")
        logger.info("│  AGENTCORE IDENTITY — SCOPE ENFORCEMENT                    │")
        logger.info("└" + "─" * 60 + "┘")
        logger.info(f"  Agent:    {self.allowed_provider.upper()} Agent")
        logger.info(f"  Identity: {self.identity_arn}")
        logger.info(f"  URL:      {url}")

        logger.info("  Step 1/2: Detecting provider from URL...")
        start = time.time()
        provider = self.detect_provider(url)
        elapsed_ms = (time.time() - start) * 1000
        logger.info(f"  Step 1/2 done ({elapsed_ms:.1f}ms) → detected: '{provider}'")

        if provider is None:
            logger.error(f"  ✖ SCOPE FAILED: Unrecognized URL — not GitHub or Jira")
            raise AgentCoreIdentityError(f"Unrecognized URL: {url}. Not a GitHub or Jira link.")

        logger.info(f"  Step 2/2: Checking authorization...")
        logger.info(f"    This agent's scope:  {self.allowed_provider}")
        logger.info(f"    URL's provider:      {provider}")
        logger.info(f"    Match?               {provider == self.allowed_provider}")

        if not self.is_authorized_for(provider):
            logger.error("")
            logger.error("  ╔══════════════════════════════════════════════════╗")
            logger.error("  ║  🚫  SCOPE CHECK: *** REJECTED ***               ║")
            logger.error("  ╚══════════════════════════════════════════════════╝")
            logger.error(f"  Agent '{self.allowed_provider}' CANNOT access '{provider}' resources")
            logger.error(f"  Identity ARN: {self.identity_arn}")
            logger.error(f"  URL: {url}")
            logger.error(f"  → AgentCore Identity blocks this request at the identity layer.")
            logger.error(f"  → The agent code never even gets a token for '{provider}'.")
            logger.error("")
            raise UnauthorizedProviderError(
                f"REJECTED: This agent (identity: {self.identity_arn}) is only "
                f"authorized for '{self.allowed_provider}'. Cannot access "
                f"'{provider}' resource: {url}"
            )

        logger.info("")
        logger.info("  ╔══════════════════════════════════════════════════╗")
        logger.info("  ║  ✅  SCOPE CHECK: *** AUTHORIZED ***              ║")
        logger.info("  ╚══════════════════════════════════════════════════╝")
        logger.info(f"  Agent '{self.allowed_provider}' IS authorized for '{provider}'")
        logger.info(f"  Proceeding to token retrieval...")
        logger.info("")
        return provider

    def get_oauth_url(self, session_id: str) -> str:
        provider = self.allowed_provider
        config = self.PROVIDER_CONFIG[provider]
        app_url = os.getenv("APP_URL", "http://localhost:8080")
        logger.info(f"[get_oauth_url] Building OAuth URL for '{provider}'")
        logger.info(f"  Session: {session_id}")
        logger.info(f"  App URL: {app_url}")

        if provider == "github":
            callback = f"{app_url}/api/auth/github/callback"
            params = {
                "client_id": os.getenv("GITHUB_CLIENT_ID"),
                "redirect_uri": callback,
                "scope": config["scopes"],
                "state": json.dumps({"session_id": session_id, "identity_arn": self.identity_arn, "provider": provider}),
            }
            oauth_url = f"{config['auth_url']}?{urlencode(params)}"
            logger.info(f"  Built GitHub OAuth URL (len={len(oauth_url)})")
            logger.info(f"    client_id:    {params['client_id']}")
            logger.info(f"    redirect_uri: {callback}")
            logger.info(f"    scope:        {config['scopes']}")
            return oauth_url

        elif provider == "jira":
            callback = f"{app_url}/api/auth/jira/callback"
            params = {
                "audience": config["audience"],
                "client_id": os.getenv("JIRA_CLIENT_ID"),
                "scope": config["scopes"],
                "redirect_uri": callback,
                "response_type": "code",
                "prompt": "consent",
                "state": json.dumps({"session_id": session_id, "identity_arn": self.identity_arn, "provider": provider}),
            }
            oauth_url = f"{config['auth_url']}?{urlencode(params)}"
            logger.info(f"  Built Jira OAuth URL (len={len(oauth_url)})")
            logger.info(f"    client_id:    {params['client_id']}")
            logger.info(f"    redirect_uri: {callback}")
            logger.info(f"    audience:     {config['audience']}")
            return oauth_url

    def request_token(self, session_id: str) -> dict:
        logger.info(f"[request_token] Provider='{self.allowed_provider}' Session='{session_id[:12]}...'")
        cache_key = f"{session_id}:{self.allowed_provider}"
        logger.info(f"  Cache key: {cache_key[:30]}...")
        logger.info(f"  Checking token cache...")

        if cache_key in self._token_cache:
            cached = self._token_cache[cache_key]
            logger.info(f"  ✅ CACHE HIT — returning stored token")
            logger.info(f"    token_type:       {cached.get('token_type', 'N/A')}")
            logger.info(f"    has access_token: {bool(cached.get('access_token'))}")
            return cached

        logger.info(f"  ✖ CACHE MISS — no token found")
        logger.info(f"  In full AgentCore, this calls:")
        logger.info(f"    bedrock-agent-runtime.get_agent_identity_token(")
        logger.info(f"        agentIdentityArn='{self.identity_arn}',")
        logger.info(f"        sessionId='{session_id[:12]}...'")
        logger.info(f"    )")
        logger.info(f"  No token exists → raising OAuthFlowRequiredError...")

        try:
            auth_url = self.get_oauth_url(session_id)
            raise OAuthFlowRequiredError(auth_url=auth_url, session_uri=session_id)
        except OAuthFlowRequiredError:
            raise
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"  AWS ClientError: {error_code}")
            if error_code == "AccessDeniedException":
                raise UnauthorizedProviderError(
                    f"AgentCore Identity denied token for {self.identity_arn}"
                )
            raise

    def store_token(self, session_id: str, token_data: dict):
        cache_key = f"{session_id}:{self.allowed_provider}"
        logger.info(f"[store_token] Storing token for '{self.allowed_provider}'")
        logger.info(f"  Cache key:       {cache_key[:30]}...")
        logger.info(f"  token_type:      {token_data.get('token_type', 'N/A')}")
        logger.info(f"  has access:      {bool(token_data.get('access_token'))}")
        logger.info(f"  scope:           {token_data.get('scope', 'N/A')}")
        logger.info(f"  cloud_id (jira): {token_data.get('cloud_id', 'N/A')}")
        self._token_cache[cache_key] = token_data
        logger.info(f"  ✅ Stored. Total cached: {len(self._token_cache)}")

    def get_cached_token(self, session_id: str) -> Optional[dict]:
        cache_key = f"{session_id}:{self.allowed_provider}"
        token = self._token_cache.get(cache_key)
        logger.info(f"[get_cached_token] {self.allowed_provider} | {session_id[:8]}... → {'HIT' if token else 'MISS'}")
        return token

    def revoke_token(self, session_id: str):
        cache_key = f"{session_id}:{self.allowed_provider}"
        had = cache_key in self._token_cache
        self._token_cache.pop(cache_key, None)
        logger.info(f"[revoke_token] {self.allowed_provider} | {session_id[:8]}... → {'REVOKED' if had else 'NOTHING TO REVOKE'}")
