# vault-demo-web

A demo web application (Python / Flask backend + HTML/CSS/JS frontend) that
illustrates how secrets delivered by **Vault Agent** or the
**Vault Secrets Operator** are consumed by an application.

> **The app does not connect to Vault directly.**  
> Secrets are injected into the container by Vault Agent (rendered files) or
> the Vault Secrets Operator (environment variables / mounted K8s Secrets).
> The app simply reads and displays what has been injected.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Pod / Container                                     │
│                                                      │
│  ┌─────────────────┐    /vault/secrets/   ┌───────┐ │
│  │  Vault Agent    │──────────────────────▶       │ │
│  │  (sidecar)      │   rendered files     │  App  │ │
│  └─────────────────┘                      │       │ │
│                                           │       │ │
│  ┌─────────────────┐    env vars /        │       │ │
│  │  Vault Secrets  │──────────────────────▶       │ │
│  │  Operator       │   K8s Secret mount   └───────┘ │
│  └─────────────────┘                                 │
└──────────────────────────────────────────────────────┘
```

---

## Repository layout

```
vault-demo-web/
├── backend/
│   ├── app.py              Flask application entry point
│   ├── config.py           Configuration loader (env + file)
│   ├── secrets_reader.py   Reads injected secrets (files or env vars)
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── config/
│   └── config.yaml.example
├── vault-agent/
│   ├── agent.hcl.example   Starter Vault Agent config
│   ├── db-creds.tpl.example
│   └── app-config.tpl.example
├── openshift/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── route.yaml
│   ├── configmap.yaml
│   └── secret.yaml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Configuration

The app supports **two ways** to pass configuration (env vars take priority):

### 1. Environment variables

| Variable             | Default          | Description                                               |
|----------------------|------------------|-----------------------------------------------------------|
| `CONFIG_FILE`        | *(auto-search)*  | Explicit path to a YAML config file                       |
| `SERVER_HOST`        | `0.0.0.0`        | Bind address                                              |
| `SERVER_PORT`        | `8080`           | Listen port                                               |
| `SERVER_DEBUG`       | `false`          | Flask debug mode                                          |
| `SECRETS_SOURCE`     | `file`           | `file` \| `env` \| `both`                                |
| `SECRETS_PATH`       | `/vault/secrets` | Directory of Vault-Agent-rendered files                   |
| `SECRETS_ENV_PREFIX` | `SECRET_`        | Prefix of env vars injected by the Vault Secrets Operator |

### 2. Config file (YAML)

Copy `config/config.yaml.example` → `config/config.yaml` (or any path), then
either place it in one of the auto-searched locations or set `CONFIG_FILE`:

```yaml
server:
  host: 0.0.0.0
  port: 8080
  debug: false

secrets:
  source: file           # file | env | both
  path: /vault/secrets
  env_prefix: SECRET_
```

Auto-searched locations (first match wins):

1. `/etc/vault-demo/config.yaml`
2. `./config/config.yaml`
3. `./config.yaml`

---

## Running locally (Windows / any OS)

### Prerequisites

- Python 3.11+
- pip

### Steps

```powershell
# 1. Clone the repo
git clone https://github.com/chinnonae/vault-demo-web.git
cd vault-demo-web

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Create some fake injected secrets for local testing
mkdir C:\tmp\vault-secrets
echo {"username": "admin", "password": "s3cr3t"} > C:\tmp\vault-secrets\db-creds

# 4a. Configure via env vars
$env:SECRETS_SOURCE = "file"
$env:SECRETS_PATH   = "C:\tmp\vault-secrets"
$env:SERVER_DEBUG   = "true"

# 4b. OR via a config file
copy config\config.yaml.example config\config.yaml
# edit config\config.yaml as needed
$env:CONFIG_FILE = "config\config.yaml"

# 5. Start the app
cd backend
python app.py
```

Open http://localhost:8080 in your browser.

---

## Running with Docker Compose

The compose file starts:
- A Vault dev-mode server
- A Vault Agent container writing secrets to a shared volume
- The vault-demo-web application reading from that volume

```bash
# Copy and edit the Vault Agent config
cp vault-agent/agent.hcl.example vault-agent/agent.hcl
cp vault-agent/db-creds.tpl.example vault-agent/db-creds.tpl
cp vault-agent/app-config.tpl.example vault-agent/app-config.tpl

# Put a dev token where the agent can find it
echo root > vault-agent/.vault-token

# Build and start
docker compose up --build
```

Open http://localhost:8080.

---

## Running on OpenShift

### Option A – Vault Agent sidecar (file-based secrets)

The Vault Agent Injector adds a sidecar to the pod via admission webhook.
Annotate the Deployment pod template to trigger injection:

```yaml
annotations:
  vault.hashicorp.com/agent-inject: "true"
  vault.hashicorp.com/role: "vault-demo-web"
  vault.hashicorp.com/agent-inject-secret-db-creds: "secret/data/myapp/db"
  vault.hashicorp.com/agent-inject-template-db-creds: |
    {{- with secret "secret/data/myapp/db" -}}
    username={{ .Data.data.username }}
    password={{ .Data.data.password }}
    {{- end }}
```

The agent writes the rendered file to `/vault/secrets/db-creds`.  
Set `SECRETS_SOURCE=file` and `SECRETS_PATH=/vault/secrets` on the container.

See the commented-out annotations block in `openshift/deployment.yaml`.

### Option B – Vault Secrets Operator (env var-based secrets)

The Vault Secrets Operator syncs Vault secrets into a Kubernetes Secret.
Mount that Secret as environment variables with the `SECRET_` prefix:

```yaml
envFrom:
  - secretRef:
      name: vault-demo-secrets   # managed by VSO
env:
  - name: SECRETS_SOURCE
    value: "env"
  - name: SECRETS_ENV_PREFIX
    value: "SECRET_"
```

See `openshift/secret.yaml` for the K8s Secret template.

### Deploy

```bash
# Build and push the image to your registry
docker build -t <registry>/vault-demo-web:latest .
docker push <registry>/vault-demo-web:latest

# Edit openshift/deployment.yaml – update the image name
# Then apply all manifests
oc apply -f openshift/
```

---

## API reference

| Method | Path                  | Description                               |
|--------|-----------------------|-------------------------------------------|
| GET    | `/api/health`         | Application health status                 |
| GET    | `/api/config`         | Active configuration                      |
| GET    | `/api/secrets`        | List all injected secrets (name + source) |
| GET    | `/api/secrets/<name>` | Read fields of a specific injected secret |
