# agent-x
AgentCore Identity enforces which agent can talk to which service 
>
> Agent A connects to **GitHub only**. Agent B connects to **Jira only**.
> Paste a link → the right agent picks it up → the wrong agent rejects it.
> All powered by **AWS Bedrock AgentCore Identity**.
**scoping OAuth credentials per-agent so each agent can ONLY access the services it's authorized for.**

| Agent | Authorized For | Rejects |
|-------|---------------|---------|
| Agent A (GitHub Agent) | `github.com/*` links | Any Jira/Atlassian link |
| Agent B (Jira Agent) | `*.atlassian.net/*` links | Any GitHub link |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  FRONTEND                    │
│  User pastes a link → picks agent or auto   │
│  Shows auth status, results, rejections     │
└──────────────────┬──────────────────────────┘
                   │ POST /api/process
                   ▼
┌─────────────────────────────────────────────┐
│               FLASK BACKEND                  │
│                                             │
│  /api/process  → routes link to agent       │
│  /api/auth/callback → handles OAuth return  │
│  /api/status   → agent auth status          │
│                                             │
│  ┌───────────────┐  ┌───────────────┐       │
│  │   AGENT A     │  │   AGENT B     │       │
│  │  (LangGraph)  │  │  (LangGraph)  │       │
│  │               │  │               │       │
│  │  GitHub OAuth │  │  Jira OAuth   │       │
│  │  via AgentCore│  │  via AgentCore│       │
│  │  Identity     │  │  Identity     │       │
│  └───────┬───────┘  └───────┬───────┘       │
│          │                  │               │
│          ▼                  ▼               │
│  AgentCore Identity   AgentCore Identity    │
│  (GitHub scope)       (Jira scope)          │
└─────────────────────────────────────────────┘
```

---

## Prerequisites

- **AWS Account** with Bedrock AgentCore access (region of choice ie us-east-1 / us-west-2)
- **GitHub OAuth App** (create one)
- **Atlassian/Jira OAuth App** (create one)
- **AWS CLI v2** configured (`aws configure`)
- **Docker** installed locally
- **Python 3.11+**

---

## Step-by-Step Setup (The Dumb-Simple Version)

### STEP 1: Create Your OAuth Apps

#### 1a. GitHub OAuth App
1. Go to https://github.com/settings/developers
2. Click **"New OAuth App"**
3. Fill in:
   - **Application name**: `AgentCore GitHub Agent`
   - **Homepage URL**: `http://localhost:8080` (change to App Runner URL later)
   - **Authorization callback URL**: `http://localhost:8080/api/auth/github/callback`
4. Click **Register application**
5. Copy the **Client ID**
6. Click **Generate a new client secret** → copy the **Client Secret**
7. Save both somewhere safe.

#### 1b. Atlassian (Jira) OAuth App
1. Go to https://developer.atlassian.com/console/myapps/
2. Click **"Create"** → **"OAuth 2.0 integration"**
3. Name it `AgentCore Jira Agent`
4. Under **Authorization** → add callback URL: `http://localhost:8080/api/auth/jira/callback`
5. Under **Permissions** → add **Jira API** → add scopes:
   - `read:jira-work`
   - `read:jira-user`
6. Copy **Client ID** and **Secret**
7. Save both.

---

### STEP 2: Register Identities in AgentCore

This is the core of the demo. Each agent gets its own **AgentCore Identity** with a specific OAuth configuration.

```bash
# Make the setup script executable
chmod +x scripts/setup-agentcore-identities.sh

# Run it — it will prompt you for the OAuth credentials from Step 1
./scripts/setup-agentcore-identities.sh
```

**What this script does (explained simply):**

1. Creates an **OAuth2 credential** in AgentCore for GitHub
2. Creates an **OAuth2 credential** in AgentCore for Jira
3. Creates **Agent Identity A** → linked to GitHub credential ONLY
4. Creates **Agent Identity B** → linked to Jira credential ONLY
5. Outputs the Identity ARNs you'll need for the `.env` file

After running, you'll get output like:
```
✅ GitHub Agent Identity ARN: arn:aws:bedrock:us-east-1:123456:agent-identity/github-agent-xxx
✅ Jira Agent Identity ARN:   arn:aws:bedrock:us-east-1:123456:agent-identity/jira-agent-xxx
```

---

### STEP 3: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:
```env
AWS_REGION=us-east-1
GITHUB_AGENT_IDENTITY_ARN=arn:aws:bedrock:us-east-1:XXXX:agent-identity/github-agent-xxx
JIRA_AGENT_IDENTITY_ARN=arn:aws:bedrock:us-east-1:XXXX:agent-identity/jira-agent-xxx
GITHUB_CLIENT_ID=your_github_client_id
JIRA_CLIENT_ID=your_jira_client_id
APP_URL=http://localhost:8080
```

---

### STEP 4: Run Locally

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Start the backend (serves frontend too)
python app.py
```

Open `http://localhost:8080` → paste a GitHub or Jira link → watch the magic.

---

### STEP 5: Deploy to App Runner

```bash
# Make deploy script executable
chmod +x scripts/deploy-apprunner.sh

# Run it
./scripts/deploy-apprunner.sh
```

**What the deploy script does:**
1. Builds the Docker image
2. Pushes to ECR
3. Creates an App Runner service with your env vars
4. Outputs the public URL

**IMPORTANT: After deploy, update your OAuth callback URLs:**
- GitHub: `https://YOUR-APPRUNNER-URL.awsapprunner.com/api/auth/github/callback`
- Jira: `https://YOUR-APPRUNNER-URL.awsapprunner.com/api/auth/jira/callback`
- Also update `APP_URL` in App Runner env vars

---

### STEP 6: Push to GitHub

```bash
git init
git add .
git commit -m "AgentCore Identity showcase - dual agent OAuth scoping"
gh repo create agentcore-identity-showcase --public --push
```

---

## How It Works (The AgentCore Identity Part)

### The Key Concept

AgentCore Identity acts as an **OAuth broker** for your agents. Instead of each agent managing its own tokens, AgentCore:

1. **Stores OAuth credentials** (client ID/secret) per provider
2. **Creates agent identities** that are scoped to specific credentials
3. **Handles the OAuth flow** (redirect → consent → token exchange)
4. **Issues scoped tokens** that only work for the authorized provider
5. **Refuses tokens** for providers the agent isn't authorized for

### In This Demo

```python
# Agent A asks AgentCore for a GitHub token → ✅ Gets it
token = agentcore_identity.get_token(
    identity_arn=GITHUB_AGENT_IDENTITY_ARN,
    provider="github"
)

# Agent A asks AgentCore for a Jira token → ❌ DENIED
token = agentcore_identity.get_token(
    identity_arn=GITHUB_AGENT_IDENTITY_ARN,
    provider="jira"
)  # Raises UnauthorizedProviderError
```


---

## Project Structure

```
agent-x/
├── README.md                          ← You are here
├── .env.example                       ← Template for env vars
├── Dockerfile                         ← Single container for App Runner
├── backend/
│   ├── app.py                         ← Flask server + routes
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── github_agent.py            ← Agent A (LangGraph + GitHub)
│   │   └── jira_agent.py              ← Agent B (LangGraph + Jira)
│   ├── identity/
│   │   ├── __init__.py
│   │   └── agentcore_client.py        ← AgentCore Identity wrapper
│   └── requirements.txt
├── frontend/
│   └── index.html                     ← Single-page UI
└── scripts/
    ├── setup-agentcore-identities.sh  ← Creates identities in AgentCore
    └── deploy-apprunner.sh            ← Deploys to App Runner
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `AccessDenied` on AgentCore calls | Check IAM role has `bedrock:*` or scoped AgentCore permissions |
| OAuth redirect loop | Make sure callback URLs match EXACTLY (http vs https, trailing slashes) |
| Agent gets wrong token | Verify the Identity ARNs in `.env` aren't swapped |
| ECR push fails | Run `aws ecr get-login-password --region us-east-1 \| docker login ...` |
| App Runner 502 | Check CloudWatch logs — usually a missing env var |

---

## License
Private
