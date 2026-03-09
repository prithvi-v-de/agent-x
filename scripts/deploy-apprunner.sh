#!/bin/bash
# =============================================================================
# Deploy to AWS App Runner
# =============================================================================
# Builds Docker image, pushes to ECR, creates/updates App Runner service.
#
# Prerequisites:
#   - AWS CLI v2 configured
#   - Docker running
#   - .env file populated
# =============================================================================

set -euo pipefail

REGION="${AWS_REGION:-us-east-2}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="agent-x"
IMAGE_TAG="latest"
SERVICE_NAME="agent-x"

echo "=============================================="
echo "  Deploying to App Runner"
echo "  Account: ${ACCOUNT_ID}"
echo "  Region:  ${REGION}"
echo "=============================================="

# --- Step 1: Create ECR Repository ---
echo ""
echo "--- Step 1: ECR Repository ---"
aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${REGION}" 2>/dev/null \
    || aws ecr create-repository --repository-name "${ECR_REPO}" --region "${REGION}"
echo "  ✅ ECR repo ready: ${ECR_REPO}"

# --- Step 2: Build & Push Docker Image ---
echo ""
echo "--- Step 2: Build & Push ---"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker build -t "${ECR_REPO}:${IMAGE_TAG}" .
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"
echo "  ✅ Image pushed: ${ECR_URI}:${IMAGE_TAG}"

# --- Step 3: Create App Runner Access Role (if needed) ---
echo ""
echo "--- Step 3: IAM Roles ---"

APPRUNNER_ECR_ROLE="AppRunnerECRAccess-${SERVICE_NAME}"

# Check if role exists
if ! aws iam get-role --role-name "${APPRUNNER_ECR_ROLE}" 2>/dev/null; then
    echo "  Creating ECR access role..."
    aws iam create-role \
        --role-name "${APPRUNNER_ECR_ROLE}" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "build.apprunner.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'

    aws iam attach-role-policy \
        --role-name "${APPRUNNER_ECR_ROLE}" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"

    echo "  Waiting for role propagation..."
    sleep 10
fi

ECR_ROLE_ARN=$(aws iam get-role --role-name "${APPRUNNER_ECR_ROLE}" --query 'Role.Arn' --output text)
echo "  ✅ ECR Role: ${ECR_ROLE_ARN}"

# Instance role for Bedrock/AgentCore access
INSTANCE_ROLE="AppRunnerInstance-${SERVICE_NAME}"

if ! aws iam get-role --role-name "${INSTANCE_ROLE}" 2>/dev/null; then
    echo "  Creating instance role with Bedrock access..."
    aws iam create-role \
        --role-name "${INSTANCE_ROLE}" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'

    aws iam put-role-policy \
        --role-name "${INSTANCE_ROLE}" \
        --policy-name "BedrockAgentCoreAccess" \
        --policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "bedrock:*",
                    "bedrock-agent:*",
                    "bedrock-agent-runtime:*"
                ],
                "Resource": "*"
            }]
        }'

    sleep 10
fi

INSTANCE_ROLE_ARN=$(aws iam get-role --role-name "${INSTANCE_ROLE}" --query 'Role.Arn' --output text)
echo "  ✅ Instance Role: ${INSTANCE_ROLE_ARN}"

# --- Step 4: Source env vars ---
echo ""
echo "--- Step 4: Loading .env ---"
source <(grep -v '^\s*#' .env | grep -v '^\s*$' | sed 's/^/export /')
echo "  ✅ Env vars loaded"

# --- Step 5: Create/Update App Runner Service ---
echo ""
echo "--- Step 5: App Runner Service ---"

# Check if service exists
EXISTING_SERVICE=$(aws apprunner list-services --region "${REGION}" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
    --output text 2>/dev/null || echo "")

if [ -z "${EXISTING_SERVICE}" ] || [ "${EXISTING_SERVICE}" == "None" ]; then
    echo "  Creating new App Runner service..."
    SERVICE_RESPONSE=$(aws apprunner create-service \
        --region "${REGION}" \
        --service-name "${SERVICE_NAME}" \
        --source-configuration '{
            "AuthenticationConfiguration": {
                "AccessRoleArn": "'"${ECR_ROLE_ARN}"'"
            },
            "ImageRepository": {
                "ImageIdentifier": "'"${ECR_URI}:${IMAGE_TAG}"'",
                "ImageRepositoryType": "ECR",
                "ImageConfiguration": {
                    "Port": "8080",
                    "RuntimeEnvironmentVariables": {
                        "AWS_REGION": "'"${REGION}"'",
                        "GITHUB_AGENT_IDENTITY_ARN": "'"${GITHUB_AGENT_IDENTITY_ARN}"'",
                        "JIRA_AGENT_IDENTITY_ARN": "'"${JIRA_AGENT_IDENTITY_ARN}"'",
                        "GITHUB_CLIENT_ID": "'"${GITHUB_CLIENT_ID}"'",
                        "GITHUB_CLIENT_SECRET": "'"${GITHUB_CLIENT_SECRET}"'",
                        "JIRA_CLIENT_ID": "'"${JIRA_CLIENT_ID}"'",
                        "JIRA_CLIENT_SECRET": "'"${JIRA_CLIENT_SECRET}"'",
                        "FLASK_SECRET_KEY": "'"$(openssl rand -hex 24)"'"
                    }
                }
            }
        }' \
        --instance-configuration '{
            "Cpu": "1024",
            "Memory": "2048",
            "InstanceRoleArn": "'"${INSTANCE_ROLE_ARN}"'"
        }' \
        --health-check-configuration '{
            "Protocol": "HTTP",
            "Path": "/health",
            "Interval": 10,
            "Timeout": 5,
            "HealthyThreshold": 1,
            "UnhealthyThreshold": 5
        }' \
        --output json)

    SERVICE_URL=$(echo "${SERVICE_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['Service']['ServiceUrl'])")
else
    echo "  Updating existing service..."
    aws apprunner start-deployment \
        --region "${REGION}" \
        --service-arn "${EXISTING_SERVICE}"
    SERVICE_URL=$(aws apprunner describe-service \
        --region "${REGION}" \
        --service-arn "${EXISTING_SERVICE}" \
        --query 'Service.ServiceUrl' --output text)
fi

echo ""
echo "=============================================="
echo "  ✅ DEPLOYMENT COMPLETE"
echo "=============================================="
echo ""
echo "  Service URL: https://${SERVICE_URL}"
echo ""
echo "  ⚠️  UPDATE YOUR OAUTH CALLBACK URLs:"
echo "  GitHub:  https://${SERVICE_URL}/api/auth/github/callback"
echo "  Jira:    https://${SERVICE_URL}/api/auth/jira/callback"
echo ""
echo "  Also update APP_URL in App Runner env vars to:"
echo "  https://${SERVICE_URL}"
echo "=============================================="
