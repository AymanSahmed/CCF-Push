# Sentinel Log Generator — Azure Function

An Azure Function (Python, v2 programming model) that generates fake security logs every minute and pushes them to **Microsoft Sentinel** via the **Azure Monitor Logs Ingestion API** (CCF Push / DCE).

### One-click deploy

> Replace `<YOUR_GITHUB_USERNAME>` and `<YOUR_REPO_NAME>` in the URL below with your GitHub details, then commit `azuredeploy.json` to your repo — the button will go live automatically.

[![Deploy to Azure](https://aka.ms/deploytoazure)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FAymanSahmed%2FCCF-Push%2Fmain%2Fsentinel-log-generator%2Fazuredeploy.json)
[![Visualize](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/visualizebutton.svg)](http://armviz.io/#/?load=https%3A%2F%2Fraw.githubusercontent.com%2FAymanSahmed%2FCCF-Push%2Fmain%2Fsentinel-log-generator%2Fazuredeploy.json)

The portal wizard will prompt for all required parameters (Function App name, storage account name, DCE/DCR details, and credentials). All Azure resources are created in one click.

---

## Folder structure

```
sentinel-log-generator/
├── function_app.py       # Timer-triggered function + all logic
├── host.json             # Azure Functions host configuration
├── requirements.txt      # Python dependencies
└── local.settings.json   # Local dev config (never commit secrets)
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Azure Functions Core Tools | v4 |
| Azure CLI | 2.50+ |
| An Azure subscription | — |

---

## 1 — Azure pre-requisites

### 1a. Create an App Registration (Service Principal)

```bash
# Create the app registration
az ad app create --display-name "SentinelLogGenerator"

# Note the appId (CLIENT_ID) and tenantId (TENANT_ID) from output

# Create a client secret
az ad app credential reset \
  --id <appId> \
  --append \
  --display-name "loggen-secret"
# Note the password (CLIENT_SECRET) from output

# Create a service principal for the app
az ad sp create --id <appId>
```

### 1b. Grant the service principal the Monitoring Metrics Publisher role on the DCR

```bash
DCR_RESOURCE_ID=$(az monitor data-collection rule show \
  --name <dcr-name> \
  --resource-group <rg-name> \
  --query id -o tsv)

SP_OBJECT_ID=$(az ad sp show --id <appId> --query id -o tsv)

az role assignment create \
  --role "Monitoring Metrics Publisher" \
  --assignee-object-id "$SP_OBJECT_ID" \
  --scope "$DCR_RESOURCE_ID"
```

### 1c. Collect required values

From the Azure portal or CLI, note:

| Variable | Where to find it |
|----------|-----------------|
| `TENANT_ID` | Azure AD → Overview |
| `CLIENT_ID` | App Registration → Overview |
| `CLIENT_SECRET` | App Registration → Certificates & secrets |
| `DATA_COLLECTION_ENDPOINT` | DCE → Overview → Logs Ingestion URI |
| `DATA_COLLECTION_RULE_ID` | DCR → Overview → Immutable ID (starts with `dcr-`) |
| `STREAM_NAME` | DCR → JSON view → `streams[*].name` (e.g. `Custom-SecurityEvents_CL`) |

---

## 2 — Local development

### 2a. Configure local settings

Edit `local.settings.json` and replace all `<placeholder>` values with your real credentials.

> **Important:** `local.settings.json` is intentionally excluded from source control.  
> Add it to `.gitignore` if it isn't already.

### 2b. Install dependencies and run

```bash
cd sentinel-log-generator

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

func start
```

The timer runs every minute. To trigger it immediately for testing:

```bash
# In a second terminal
curl -X POST http://localhost:7071/admin/functions/log_generator \
  -H "Content-Type: application/json" \
  -d "{}"
```

---

## 3 — Deploy to Azure

### 3a. Create Azure resources

```bash
RG="rg-sentinel-loggen"
LOCATION="eastus"
STORAGE="stloggen$RANDOM"          # must be globally unique
FUNCAPP="func-sentinel-loggen-$RANDOM"

# Resource group
az group create --name "$RG" --location "$LOCATION"

# Storage account (required by Azure Functions)
az storage account create \
  --name "$STORAGE" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard_LRS

# Function App (Python 3.11, consumption plan)
az functionapp create \
  --name "$FUNCAPP" \
  --resource-group "$RG" \
  --storage-account "$STORAGE" \
  --consumption-plan-location "$LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type linux
```

### 3b. Set application settings (environment variables)

```bash
az functionapp config appsettings set \
  --name "$FUNCAPP" \
  --resource-group "$RG" \
  --settings \
    TENANT_ID="<your-tenant-id>" \
    CLIENT_ID="<your-client-id>" \
    CLIENT_SECRET="<your-client-secret>" \
    DATA_COLLECTION_ENDPOINT="https://<dce-name>.<region>.ingest.monitor.azure.com" \
    DATA_COLLECTION_RULE_ID="dcr-<your-dcr-immutable-id>" \
    STREAM_NAME="Custom-<your-table-name>_CL"
```

> **Tip:** For production, store `CLIENT_SECRET` in Azure Key Vault and reference it via a Key Vault reference:  
> `@Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/<name>/)`

### 3c. Publish the function

```bash
cd sentinel-log-generator

func azure functionapp publish "$FUNCAPP" --python
```

---

## 4 — Verify logs in Microsoft Sentinel / Log Analytics

Open **Log Analytics workspace** → **Logs** and run:

```kql
// Replace with your actual table name
SecurityEvents_CL
| project TimeGenerated, DeviceId, Severity, EventMessage
| order by TimeGenerated desc
| take 10
```

> Logs may take **3–5 minutes** to appear after the first successful ingestion.

### Check function execution in Application Insights

```kql
traces
| where message contains "Successfully ingested"
| project timestamp, message
| order by timestamp desc
| take 20
```

---

## 5 — Timer schedule reference

The function uses a **6-field NCrontab** expression:

```
0 */1 * * * *
│ └─── every 1 minute (minute field)
└──── 0 seconds
```

To change the cadence, update the `schedule` parameter in `function_app.py`:

| Schedule | Expression |
|----------|-----------|
| Every 1 minute | `0 */1 * * * *` |
| Every 5 minutes | `0 */5 * * * *` |
| Every hour | `0 0 * * * *` |

---

## 6 — GitHub setup (CI/CD + Deploy to Azure button)

### 6a. Push the repo to GitHub

```bash
cd "c:\Users\aymans\OneDrive - Microsoft\AMM\Demo\Demo"   # repo root

git init
git add .
git commit -m "feat: Sentinel log generator Azure Function"

# Create the repo on GitHub first, then:
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
git branch -M main
git push -u origin main
```

### 6b. Add the publish profile as a GitHub secret

1. In the Azure portal, open your Function App → **Get publish profile** (download the `.PublishSettings` file).
2. In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.
3. Name: `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` — paste the full XML content.

### 6c. Set your Function App name in the workflow

Edit [.github/workflows/deploy-sentinel-loggen.yml](../.github/workflows/deploy-sentinel-loggen.yml) and replace:

```yaml
AZURE_FUNCTIONAPP_NAME: "<your-function-app-name>"
```

with the actual name of your Function App.

### 6d. How it works from here

| Event | What happens |
|-------|-------------|
| `git push` to `main` (any file under `sentinel-log-generator/`) | GitHub Actions runs, installs deps, and publishes to Azure automatically |
| Manual trigger | Go to **Actions → Deploy Sentinel Log Generator → Run workflow** |
| First-time deploy | Click the **Deploy to Azure** button at the top of this README |

### 6e. Activate the Deploy to Azure button

In [README.md](README.md) replace both occurrences of:

```
<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>
```

The button is already live — it points to `AymanSahmed/CCF-Push`.

---

## 7 — Security notes

- Never commit `local.settings.json` or any file containing `CLIENT_SECRET`.
- Rotate the client secret regularly (recommended: 90 days).
- Use Managed Identity instead of client credentials where possible.
- Restrict the service principal to only the DCR resource via a scoped role assignment.
