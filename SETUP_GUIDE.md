# AgentCore Identity Showcase — The "I Am a Noob" Deployment Guide

**Every single click. Every single screen. No terminal unless absolutely necessary.**

---

## PHASE 1: Create a GitHub Account (Skip if You Have One)

1. Open https://github.com
2. Click **"Sign up"** (top right)
3. Follow the wizard: email, password, username
4. Verify your email
5. You're in

---

## PHASE 2: Create an Atlassian Account (Skip if You Have One)

1. Open https://www.atlassian.com
2. Click **"Get it free"** or **"Sign up"**
3. Use your email, create a password
4. It will ask you to name a "site" — pick anything like `myteam` (your Jira will be at `myteam.atlassian.net`)
5. Complete the setup wizard — you'll get a free Jira board

---

## PHASE 3: Create an AWS Account (Skip if You Have One)

1. Open https://aws.amazon.com
2. Click **"Create an AWS Account"** (top right)
3. Fill in email, password, account name
4. Enter payment info (you won't be charged much — App Runner costs pennies)
5. Choose **"Basic support - Free"** plan
6. Wait for account activation (can take up to 24 hours but usually minutes)

---

## PHASE 4: Create the GitHub OAuth App

**What this does**: Gives your app permission to talk to GitHub on behalf of a user.

1. Open https://github.com/settings/developers
2. You'll see a page called **"Developer settings"**. On the left sidebar, click **"OAuth Apps"**
3. Click the green button **"New OAuth App"**
4. Fill in the form EXACTLY:
   - **Application name**: `AgentCore Identity Showcase`
   - **Homepage URL**: `http://localhost:8080`
   - **Application description**: (optional, write whatever)
   - **Authorization callback URL**: `http://localhost:8080/api/auth/github/callback`
5. Click **"Register application"**
6. You'll land on a page showing your app. You'll see:
   - **Client ID**: a string like `Iv1.abc123def456` — COPY THIS, paste it into a notepad/note
7. Click **"Generate a new client secret"**
   - A secret appears like `abcdef1234567890abcdef1234567890abcdef12` — COPY THIS IMMEDIATELY. You can only see it once.
8. Save both somewhere safe. Label them:
   ```
   GITHUB_CLIENT_ID=Iv1.abc123def456
   GITHUB_CLIENT_SECRET=abcdef1234567890abcdef1234567890abcdef12
   ```

---

## PHASE 5: Create the Atlassian (Jira) OAuth App

**What this does**: Same thing but for Jira.

1. Open https://developer.atlassian.com/console/myapps/
2. Log in with your Atlassian account
3. Click **"Create"** button (top right) then **"OAuth 2.0 integration"**
4. Name it: `AgentCore Identity Showcase`
5. Check **"I agree to the terms"** and click **"Create"**
6. You'll land on your app's page. Now do these things in order:

### 5a. Add Permissions
1. In the left sidebar, click **"Permissions"**
2. Find **"Jira API"** in the list
3. Click **"Add"** next to it
4. Click **"Configure"** next to Jira API
5. Under **"Classic scopes"**, make sure these are checked:
   - `read:jira-work`
   - `read:jira-user`
6. Click **"Save"**

### 5b. Set the Callback URL
1. In the left sidebar, click **"Authorization"**
2. Next to **"OAuth 2.0 (3LO)"**, click **"Add"**
3. In the **Callback URL** field, type:
   ```
   http://localhost:8080/api/auth/jira/callback
   ```
4. Click **"Save changes"**

### 5c. Copy Your Credentials
1. In the left sidebar, click **"Settings"**
2. You'll see:
   - **Client ID**: a string like `aBcDeFgHiJkLmNoPqRsT` — COPY THIS
   - **Secret**: click **"Show secret"** — COPY THIS
3. Save both:
   ```
   JIRA_CLIENT_ID=aBcDeFgHiJkLmNoPqRsT
   JIRA_CLIENT_SECRET=xYzAbCdEfGhIjKlMnOpQrStUvWx
   ```

---

## PHASE 6: Set Up AWS (Console GUI — No Terminal Yet)

### 6a. Set Your Region
1. Log into https://console.aws.amazon.com
2. In the top-right corner, you'll see a region name (like "N. Virginia"). Click it.
3. Select **"US East (N. Virginia) us-east-1"** — this is where Bedrock AgentCore lives

### 6b. Create an IAM User (So You Can Use AWS CLI Later)
1. In the search bar at the top, type **"IAM"** and click the result
2. In the left sidebar, click **"Users"**
3. Click **"Create user"**
4. Username: `agentcore-deployer`
5. Click **"Next"**
6. Select **"Attach policies directly"**
7. Search for and check these policies:
   - `AdministratorAccess` (yes, this is broad — you can tighten later)
8. Click **"Next"** then **"Create user"**
9. Click on the user name `agentcore-deployer`
10. Click the **"Security credentials"** tab
11. Scroll down to **"Access keys"** and click **"Create access key"**
12. Select **"Command Line Interface (CLI)"**
13. Check the confirmation checkbox and click **"Next"**
14. Click **"Create access key"**
15. You'll see:
    - **Access key ID**: like `AKIA1234567890ABCDEF`
    - **Secret access key**: click "Show" to see it
16. COPY BOTH. Save them:
    ```
    AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF
    AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    ```
17. Click **"Done"**

### 6c. Create an ECR Repository (Where Your Docker Image Goes)
1. In the AWS search bar, type **"ECR"** and click **"Elastic Container Registry"**
2. Click **"Get started"** or **"Create repository"**
3. Visibility: **Private**
4. Repository name: `agentcore-identity-showcase`
5. Leave everything else as default
6. Click **"Create repository"**
7. You'll see your repo. Note the **URI** — it looks like:
   ```
   123456789012.dkr.ecr.us-east-1.amazonaws.com/agentcore-identity-showcase
   ```

---

## PHASE 7: Install Tools on Your Computer

You need 4 things installed. Here's how for each OS:

### 7a. Install Python 3.11+

**Mac:**
1. Open Terminal (Cmd+Space, type "Terminal")
2. Run: `brew install python@3.11` (if you don't have brew: https://brew.sh)

**Windows:**
1. Go to https://www.python.org/downloads/
2. Download Python 3.11+
3. Run installer — CHECK THE BOX "Add Python to PATH"
4. Click "Install Now"

**Verify:** Open terminal/command prompt, type `python3 --version`. Should say 3.11+.

### 7b. Install Docker Desktop

1. Go to https://www.docker.com/products/docker-desktop/
2. Download for your OS
3. Install and start Docker Desktop
4. Wait until the whale icon in your taskbar/menubar shows "Docker Desktop is running"

**Verify:** Terminal: `docker --version`

### 7c. Install AWS CLI v2

1. Go to https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
2. Follow instructions for your OS (it's just a download + install)

**Verify:** Terminal: `aws --version`

### 7d. Install Git

**Mac:** It's probably already installed. Type `git --version` in Terminal.
**Windows:** Download from https://git-scm.com/download/win

### 7e. Install GitHub CLI (Optional but Makes Life Easier)

1. Go to https://cli.github.com
2. Download and install
3. Run `gh auth login` and follow the prompts

---

## PHASE 8: Configure AWS CLI

1. Open your terminal
2. Run:
   ```bash
   aws configure
   ```
3. It will ask you 4 things. Type them in:
   ```
   AWS Access Key ID: (paste your AKIA... key from Phase 6b)
   AWS Secret Access Key: (paste your secret key from Phase 6b)
   Default region name: us-east-1
   Default output format: json
   ```
4. Done. AWS CLI now talks to your account.

---

## PHASE 9: Get the Code

### Option A: Clone from GitHub (If You've Already Pushed It)
```bash
git clone https://github.com/YOUR_USERNAME/agentcore-identity-showcase.git
cd agentcore-identity-showcase
```

### Option B: Use the Files from This Chat
Download the project from this conversation and unzip it, then:
```bash
cd agentcore-identity-showcase
```

---

## PHASE 10: Set Up Your Environment File

1. In the project folder, copy the example:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` in any text editor (VS Code, Notepad, TextEdit, whatever)
3. Fill in every value using the stuff you saved earlier:
   ```env
   AWS_REGION=us-east-1

   GITHUB_AGENT_IDENTITY_ARN=placeholder-fill-after-phase-11
   JIRA_AGENT_IDENTITY_ARN=placeholder-fill-after-phase-11

   GITHUB_CLIENT_ID=Iv1.abc123def456
   GITHUB_CLIENT_SECRET=abcdef1234567890abcdef1234567890abcdef12

   JIRA_CLIENT_ID=aBcDeFgHiJkLmNoPqRsT
   JIRA_CLIENT_SECRET=xYzAbCdEfGhIjKlMnOpQrStUvWx

   APP_URL=http://localhost:8080
   FLASK_SECRET_KEY=just-type-any-random-long-string-here-like-this-one
   ```
4. Save the file.

---

## PHASE 11: Create AgentCore Identities

### If the AgentCore Console is Available:

1. Go to https://console.aws.amazon.com
2. Search for **"Bedrock"** and click it
3. In the left sidebar, look for **"AgentCore"** then **"Identities"**
4. Click **"Create identity"**
5. For the FIRST identity:
   - Name: `github-agent-identity`
   - Description: `OAuth identity for GitHub Agent - scoped to GitHub only`
   - Add an OAuth credential:
     - Provider: Custom
     - Auth URL: `https://github.com/login/oauth/authorize`
     - Token URL: `https://github.com/login/oauth/access_token`
     - Client ID: (your GitHub client ID)
     - Client Secret: (your GitHub client secret)
     - Scopes: `repo read:user read:org`
   - Click **Create**
   - COPY the Identity ARN — it looks like `arn:aws:bedrock:us-east-1:123456:agent-identity/github-agent-xxx`
6. Click **"Create identity"** again for the SECOND:
   - Name: `jira-agent-identity`
   - Description: `OAuth identity for Jira Agent - scoped to Jira only`
   - Add an OAuth credential:
     - Provider: Custom
     - Auth URL: `https://auth.atlassian.com/authorize`
     - Token URL: `https://auth.atlassian.com/oauth/token`
     - Client ID: (your Jira client ID)
     - Client Secret: (your Jira client secret)
     - Scopes: `read:jira-work read:jira-user offline_access`
   - Click **Create**
   - COPY the Identity ARN

### If Using the CLI Script Instead:
```bash
chmod +x scripts/setup-agentcore-identities.sh
./scripts/setup-agentcore-identities.sh
```
It will prompt you for all the values and output the ARNs.

### Update Your .env:
Open `.env` again and replace the placeholder ARNs:
```env
GITHUB_AGENT_IDENTITY_ARN=arn:aws:bedrock:us-east-1:123456:agent-identity/github-agent-xxx
JIRA_AGENT_IDENTITY_ARN=arn:aws:bedrock:us-east-1:123456:agent-identity/jira-agent-xxx
```
Save.

---

## PHASE 12: Run Locally (Test It First!)

```bash
cd backend
pip install -r requirements.txt
python app.py
```

You should see a wall of logs like:
```
======================================================================
  AGENTCORE IDENTITY SHOWCASE — STARTING UP
======================================================================
  AWS_REGION:                us-east-1
  GITHUB_AGENT_IDENTITY_ARN: arn:aws:bedrock:us-east-1:...
  ...
  Starting Flask on 0.0.0.0:8080
  Open http://localhost:8080
```

Open http://localhost:8080 in your browser. You'll see the UI with two agent cards.

### Test It:
1. Paste `https://github.com/langchain-ai/langgraph` and click "Run Agents"
2. GitHub Agent should show ACCEPTED (or AUTH_REQUIRED)
3. Jira Agent should show REJECTED
4. Paste `https://myteam.atlassian.net/browse/PROJ-42`
5. Jira Agent should show ACCEPTED (or AUTH_REQUIRED)
6. GitHub Agent should show REJECTED

### Check the Terminal Logs:
You'll see the full agent execution trace:
```
==================================================================
  /api/process  —  DUAL AGENT EXECUTION START
==================================================================
  Input URL:    'https://github.com/langchain-ai/langgraph'

  +-------------------------------------------------+
  |  INVOKING AGENT A  —  GitHub Agent (LangGraph)  |
  +-------------------------------------------------+

  GITHUB AGENT — NODE: scope_check
  Calling AgentCore Identity enforce_scope()...
  Testing pattern 'github.com' in URL... YES
  SCOPE CHECK: *** AUTHORIZED ***

  +-------------------------------------------------+
  |  INVOKING AGENT B  —  Jira Agent (LangGraph)    |
  +-------------------------------------------------+

  JIRA AGENT — NODE: scope_check
  Calling AgentCore Identity enforce_scope()...
  Testing pattern 'atlassian.net' in URL... no
  Testing pattern 'github.com' in URL... YES
  SCOPE CHECK: *** REJECTED ***

==================================================================
  EXECUTION SUMMARY
  Agent A:  AUTH_REQUIRED (GitHub Agent)
  Agent B:  REJECTED      (Jira Agent)
==================================================================
```

---

## PHASE 13: Deploy to App Runner (GUI Way)

### 13a. Build and Push Docker Image

In your terminal, from the project root:

```bash
# Find your account ID (12-digit number)
aws sts get-caller-identity --query Account --output text
# Example output: 123456789012

# Log Docker into ECR (replace 123456789012 with YOUR account ID)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build the image
docker build -t agentcore-identity-showcase .

# Tag it for ECR (replace 123456789012)
docker tag agentcore-identity-showcase:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/agentcore-identity-showcase:latest

# Push it (replace 123456789012)
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/agentcore-identity-showcase:latest
```

### 13b. Create App Runner Service (In AWS Console)

1. Go to https://console.aws.amazon.com
2. Search for **"App Runner"** and click it
3. Click **"Create service"**

**Source and deployment:**

4. Source: **"Container registry"**
5. Provider: **"Amazon ECR"**
6. Click **"Browse"** and find your image: `agentcore-identity-showcase` then tag `latest`
7. Deployment trigger: **"Manual"**
8. ECR access role: Click **"Create new service role"**
9. Click **"Next"**

**Configure service:**

10. Service name: `agentcore-identity-showcase`
11. CPU: **1 vCPU**
12. Memory: **2 GB**
13. Port: **8080**
14. Scroll down to **"Environment variables"** and click **"Add environment variable"** for EACH of these:

    | Key | Value |
    |-----|-------|
    | `AWS_REGION` | `us-east-1` |
    | `GITHUB_AGENT_IDENTITY_ARN` | your ARN from Phase 11 |
    | `JIRA_AGENT_IDENTITY_ARN` | your ARN from Phase 11 |
    | `GITHUB_CLIENT_ID` | your GitHub client ID |
    | `GITHUB_CLIENT_SECRET` | your GitHub client secret |
    | `JIRA_CLIENT_ID` | your Jira client ID |
    | `JIRA_CLIENT_SECRET` | your Jira client secret |
    | `APP_URL` | `https://placeholder` (you'll update this) |
    | `FLASK_SECRET_KEY` | any random string |

15. Under **"Instance role"** — you need a role with Bedrock permissions:
    - Open a new browser tab
    - Go to IAM > Roles > Create role
    - Trusted entity: AWS service
    - Use case: search "App Runner", select it
    - Click **"Next"**
    - Search for `AmazonBedrockFullAccess` and check it
    - Click **"Next"**
    - Role name: `AppRunnerBedrockRole`
    - Click **"Create role"**
    - Go back to the App Runner tab, refresh the role dropdown, select `AppRunnerBedrockRole`

16. Click **"Next"**

**Health check:**

17. Protocol: **HTTP**
18. Path: `/health`
19. Click **"Next"**

**Review and create:**

20. Review everything
21. Click **"Create & deploy"**
22. WAIT 3-5 minutes. Status goes from "Operation in progress" to **"Running"**.

### 13c. Get Your URL and Update Everything

1. Once running, copy the **"Default domain"** from the top of the page:
   ```
   https://abcdef1234.us-east-1.awsapprunner.com
   ```

2. **Update APP_URL in App Runner:**
   - Click **"Configuration"** tab
   - Click **"Edit"**
   - Change `APP_URL` to your actual URL: `https://abcdef1234.us-east-1.awsapprunner.com`
   - Click **"Save changes"** (triggers a redeploy, wait again)

3. **Update GitHub OAuth callback:**
   - Go to https://github.com/settings/developers
   - Click your OAuth app
   - Change **Authorization callback URL** to:
     `https://abcdef1234.us-east-1.awsapprunner.com/api/auth/github/callback`
   - Update **Homepage URL** too
   - Click **"Update application"**

4. **Update Jira OAuth callback:**
   - Go to https://developer.atlassian.com/console/myapps/
   - Click your app > **Authorization** > edit the callback URL to:
     `https://abcdef1234.us-east-1.awsapprunner.com/api/auth/jira/callback`
   - Click **"Save changes"**

---

## PHASE 14: Push to GitHub

```bash
cd agentcore-identity-showcase
git init
git add .
git commit -m "AgentCore Identity showcase - dual agent OAuth scoping"

# Easiest way (with GitHub CLI):
gh repo create agentcore-identity-showcase --public --source=. --push

# OR manually:
# 1. Go to github.com, click "+" > "New repository"
# 2. Name it agentcore-identity-showcase, make it public, DON'T add README
# 3. Follow the commands GitHub shows you
```

---

## PHASE 15: Verify Everything Works

1. Open your App Runner URL in a browser
2. Paste `https://github.com/langchain-ai/langgraph`
3. Expected:
   - **GitHub Agent**: AUTH_REQUIRED (green-ish, with authorize link) or SUCCESS
   - **Jira Agent**: REJECTED (red, showing scope mismatch)
4. Paste `https://myteam.atlassian.net/browse/PROJ-42`
5. Expected: opposite results
6. Check logs: App Runner console > your service > **Logs** tab

---

## Troubleshooting

**"I see the UI but agents show ERROR"**
Check your .env / App Runner env vars. The extreme logging tells you exactly what's wrong.

**"OAuth keeps redirecting in a loop"**
Callback URLs don't match. Must be EXACT — http vs https, trailing slashes, typos.

**"Docker push fails with 'no basic auth credentials'"**
Run the ECR login command again (the token expires after 12 hours).

**"App Runner stuck on 'Operation in progress'"**
Wait up to 10 minutes. Check CloudWatch logs for the real error.

**"Cannot find AgentCore in the Bedrock console"**
Make sure you're in us-east-1. AgentCore may need preview access — check AWS docs.

**"pip install fails"**
Try `pip3 install -r requirements.txt` or `python3 -m pip install -r requirements.txt`

---

## What Did We Just Build?

Two agents. Same URL goes to both. AgentCore Identity decides who can touch what.

- Agent A's identity ARN is linked to a GitHub OAuth credential. It can ONLY get GitHub tokens.
- Agent B's identity ARN is linked to a Jira OAuth credential. It can ONLY get Jira tokens.
- The `scope_check` node in each LangGraph agent calls `enforce_scope()` which checks: does this agent's identity allow this provider? Yes = proceed. No = hard reject.
- That's the whole demo. The identity layer is the bouncer. The agents don't decide — AgentCore Identity does.
