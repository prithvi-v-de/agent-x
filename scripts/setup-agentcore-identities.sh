#!/bin/bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-2}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=============================================="
echo "  AgentCore Identity Setup"
echo "  Account: ${ACCOUNT_ID}"
echo "  Region:  ${REGION}"
echo "=============================================="
echo ""

read -p "GitHub OAuth Client ID: " GITHUB_CLIENT_ID
read -sp "GitHub OAuth Client Secret: " GITHUB_CLIENT_SECRET
echo ""
read -p "Jira/Atlassian OAuth Client ID: " JIRA_CLIENT_ID
read -sp "Jira/Atlassian OAuth Client Secret: " JIRA_CLIENT_SECRET
echo ""
read -p "App URL (e.g., http://localhost:8080): " APP_URL

echo ""
echo "--- Creating GitHub OAuth credential ---"
GITHUB_CRED_RESPONSE=$(aws bedrock-agent create-agent-runtime-credential \
    --region "${REGION}" \
    --name "github-oauth-credential" \
    --description "OAuth2 credential for GitHub Agent" \
    --credential-type "OAUTH2" \
    --oauth2-credential-configuration '{
        "oauthProvider": "CUSTOM",
        "authorizationUrl": "https://github.com/login/oauth/authorize",
        "tokenUrl": "https://github.com/login/oauth/access_token",
        "clientId": "'"${GITHUB_CLIENT_ID}"'",
        "clientSecret": "'"${GITHUB_CLIENT_SECRET}"'",
        "scope": "repo read:user read:org",
        "redirectUri": "'"${APP_URL}/api/auth/github/callback"'"
    }' --output json 2>/dev/null || echo '{"credentialArn":"MANUAL_SETUP_REQUIRED"}')

GITHUB_CRED_ARN=$(echo "${GITHUB_CRED_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('credentialArn','MANUAL'))" 2>/dev/null || echo "MANUAL")
echo "  GitHub Credential: ${GITHUB_CRED_ARN}"

echo "--- Creating Jira OAuth credential ---"
JIRA_CRED_RESPONSE=$(aws bedrock-agent create-agent-runtime-credential \
    --region "${REGION}" \
    --name "jira-oauth-credential" \
    --description "OAuth2 credential for Jira Agent" \
    --credential-type "OAUTH2" \
    --oauth2-credential-configuration '{
        "oauthProvider": "CUSTOM",
        "authorizationUrl": "https://auth.atlassian.com/authorize",
        "tokenUrl": "https://auth.atlassian.com/oauth/token",
        "clientId": "'"${JIRA_CLIENT_ID}"'",
        "clientSecret": "'"${JIRA_CLIENT_SECRET}"'",
        "scope": "read:jira-work read:jira-user offline_access",
        "audience": "api.atlassian.com",
        "redirectUri": "'"${APP_URL}/api/auth/jira/callback"'"
    }' --output json 2>/dev/null || echo '{"credentialArn":"MANUAL_SETUP_REQUIRED"}')

JIRA_CRED_ARN=$(echo "${JIRA_CRED_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('credentialArn','MANUAL'))" 2>/dev/null || echo "MANUAL")
echo "  Jira Credential: ${JIRA_CRED_ARN}"

echo ""
echo "--- Creating Agent Identities ---"

GITHUB_IDENTITY_RESPONSE=$(aws bedrock-agent create-agent-identity \
    --region "${REGION}" \
    --name "github-agent-identity" \
    --description "Identity for Agent A - GitHub only" \
    --credential-arns "[\"${GITHUB_CRED_ARN}\"]" \
    --output json 2>/dev/null || echo '{"agentIdentityArn":"MANUAL_SETUP_REQUIRED"}')

GITHUB_IDENTITY_ARN=$(echo "${GITHUB_IDENTITY_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agentIdentityArn','MANUAL'))" 2>/dev/null || echo "MANUAL")

JIRA_IDENTITY_RESPONSE=$(aws bedrock-agent create-agent-identity \
    --region "${REGION}" \
    --name "jira-agent-identity" \
    --description "Identity for Agent B - Jira only" \
    --credential-arns "[\"${JIRA_CRED_ARN}\"]" \
    --output json 2>/dev/null || echo '{"agentIdentityArn":"MANUAL_SETUP_REQUIRED"}')

JIRA_IDENTITY_ARN=$(echo "${JIRA_IDENTITY_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agentIdentityArn','MANUAL'))" 2>/dev/null || echo "MANUAL")

echo ""
echo "=============================================="
echo "  SETUP COMPLETE"
echo "=============================================="
echo ""
echo "  GITHUB_AGENT_IDENTITY_ARN=${GITHUB_IDENTITY_ARN}"
echo "  JIRA_AGENT_IDENTITY_ARN=${JIRA_IDENTITY_ARN}"
echo ""
echo "  If any ARN shows MANUAL_SETUP_REQUIRED,"
echo "  use the AWS Console instead (see SETUP_GUIDE.md)"
echo "=============================================="
