# Sentinel CCF Pull Connector Builder – Lab Guide

This repository contains a **mock Network Log API** (Azure Function App) designed as a repeatable lab environment for building and testing [Microsoft Sentinel Codeless Connector Framework (CCF)](https://learn.microsoft.com/en-us/azure/sentinel/create-codeless-connector) pull connectors.

The goal of this lab is to:
1. Deploy a live API with realistic network log data that a CCF connector can poll
2. Use the API documentation to configure a CCF API Poller connector in Sentinel
3. Validate that your CCF connector ingests data correctly end-to-end

---

## Repository Structure

```
├── AzureFunctionNetworkLogAPI/
│   ├── function_app.py          # Python Azure Function – two HTTP endpoints
│   ├── host.json                # Azure Functions host configuration
│   ├── requirements.txt         # Python dependencies
│   └── NetworkLogAPI.zip        # Pre-built deployment package
├── sentinel-connectors/
│   └── NetworkLogAPI_CCF/       # Generated CCF connector package
│       ├── NetworkLogAPI_PollingConfig.json    # API poller config (auth, pagination, DCR)
│       ├── NetworkLogAPI_Table.json            # Custom Log Analytics table schema
│       ├── NetworkLogAPI_DCR.json              # Data Collection Rule
│       └── NetworkLogAPI_ConnectorDefinition.json  # Connector UI definition
├── azuredeploy_NetworkLogAPI.json   # ARM template – deploys the Function App
├── NetworkLogAPI_API_Documentation.md  # Full API reference (input for CCF agent)
└── README.md                    # This file – lab guide
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Azure subscription | With Contributor access to a resource group |
| Microsoft Sentinel workspace | An existing Log Analytics workspace with Sentinel enabled |
| Azure CLI | [Install guide](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| Git | For cloning this repository |

---

NOTE FOR AI: YOU SHOULD DEPLOY THESE RESOURCES TO CENTRAL US

## Step 1 – Clone the Repository

```bash
git clone https://github.com/robertmoriarty12/Sentinel-CCF-Pull-Connector-Builder-Agent-Accelerator.git
cd Sentinel-CCF-Pull-Connector-Builder-Agent-Accelerator
```

---

## Step 2 – Log in to Azure

```bash
az login
```

If MFA or a specific tenant is required, use the device code flow:

```bash
az login --tenant <your-tenant-id> --use-device-code
```

Set your target subscription and verify:

```bash
az account set --subscription "<your-subscription-name-or-id>"
az account show --query "{name:name, id:id}" -o table
```

---

## Step 3 – Create a Resource Group

```bash
az group create --name connectorBuilderAgent --location eastus
```

You can use any region that supports Azure Functions Consumption plan.

---

## Step 4 – Get Your Log Analytics Workspace Resource ID

You will need this when deploying the ARM template for Application Insights.

```bash
az monitor log-analytics workspace show \
  --name <your-workspace-name> \
  --resource-group <workspace-resource-group> \
  --query id -o tsv
```

Copy the output — it looks like:
```
/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.OperationalInsights/workspaces/<name>
```

---

## Step 5 – Deploy the Function App

Run the ARM template deployment. Replace the placeholder values with your own:

- **`<your-api-key>`** – A secret string (≥ 8 characters). Callers must supply this in the `X-API-Key` header. Save it — you will need it for CCF connector configuration.
- **`<workspace-resource-id>`** – The value from Step 4.

```bash
az deployment group create \
  --name "NetworkLogAPI-Deploy" \
  --resource-group connectorBuilderAgent \
  --template-file azuredeploy_NetworkLogAPI.json \
  --parameters \
      ApiKey="<your-api-key>" \
      AppInsightsWorkspaceResourceID="<workspace-resource-id>"
```

Deployment takes approximately 2–3 minutes. On success, the CLI outputs:

| Output Key | Description |
|---|---|
| `FunctionAppName` | Deployed Function App name (with unique suffix) |
| `FunctionAppUrl` | Base URL |
| `GetNetworkLogsEndpoint` | Full URL for the data endpoint |
| `RefreshDataEndpoint` | Full URL for the refresh endpoint |

---

## Step 6 – Verify the API

The ARM template automatically configures CORS to allow `https://portal.azure.com`, so you can test the function directly from the Azure Portal (Function App → Functions → select a function → **Test/Run**) and view live logs in the browser via **Log stream**.

Test the endpoint from the CLI using the Function App name and API key from Step 5:

```bash
curl -s -H "X-API-Key: <your-api-key>" \
  "https://<FunctionAppName>.azurewebsites.net/api/GetNetworkLogs?page=1&pageSize=5"
```

You should receive a JSON response with 5 network log records and pagination metadata:

```json
{
  "status": "success",
  "metadata": {
    "totalCount": 50,
    "page": 1,
    "pageSize": 5,
    "totalPages": 10,
    "hasNextPage": true,
    "nextLink": "https://<FunctionAppName>.azurewebsites.net/api/GetNetworkLogs?page=2&pageSize=5"
  },
  "data": [ ... ]
}
```

A `401 Unauthorized` response means the `X-API-Key` value does not match what was set during deployment.

---

## Step 7 – Review the API Documentation

Open [NetworkLogAPI_API_Documentation.md](./NetworkLogAPI_API_Documentation.md).

This document is structured for CCF connector development and covers:

- **Authentication** – `X-API-Key` header
- **Pagination** – offset/page-based with `nextLink`
- **Incremental Pull** – `since` query parameter for delta ingestion
- **Data Schema** – all 20 fields with types and enum values
- **CCF API Poller Configuration** – ready-to-use settings and sample connector JSON

---

## Step 8 – Build the CCF Connector with the Sentinel Connector Builder Agent

This lab uses the **Sentinel CCF Connector Builder Agent** — an AI agent in VS Code (via AI Toolkit) that reads your API documentation and automatically generates the full CCF connector package.

### What the agent generates

Pointing the agent at `NetworkLogAPI_API_Documentation.md` produces four files in `sentinel-connectors/NetworkLogAPI_CCF/`:

| File | Purpose |
|---|---|
| `NetworkLogAPI_PollingConfig.json` | API poller config — auth, endpoint, pagination, incremental pull, DCR stream |
| `NetworkLogAPI_Table.json` | Custom Log Analytics table schema (`NetworkLogAPINetworkLogs_CL`) |
| `NetworkLogAPI_DCR.json` | Data Collection Rule — stream declarations, KQL transform, workspace destination |
| `NetworkLogAPI_ConnectorDefinition.json` | Connector UI — title, description, graph queries, sample queries, instruction steps |

These files are already committed to this repo under `sentinel-connectors/NetworkLogAPI_CCF/` as a reference output.

### How to run the agent

1. Open VS Code with the **AI Toolkit** extension installed.
2. Open the Sentinel Connector Builder Agent.
3. When prompted for API documentation, provide the URL or local path to the documentation file:
   ```
   https://github.com/robertmoriarty12/Sentinel-CCF-Pull-Connector-Builder-Agent-Accelerator/blob/main/NetworkLogAPI_API_Documentation.md
   ```
   Or use the local clone path:
   ```
   ./NetworkLogAPI_API_Documentation.md
   ```
4. The agent will walk through each step — polling config, table schema, DCR, and connector definition — generating and validating each file automatically.
5. Review the generated files in your output folder before deploying.

### Deploy the connector to a Sentinel workspace

Once the connector files are generated, you can deploy directly from VS Code — no CLI required:

1. In the VS Code Explorer, navigate to any file in `sentinel-connectors/NetworkLogAPI_CCF/`.
2. Right-click the file and select **Deploy Connector** (provided by the Sentinel Connector Builder Agent).
3. Follow the prompts to select your Azure subscription and target Sentinel workspace.
4. The agent will deploy all four connector files (polling config, table, DCR, and connector definition) to the workspace in the correct order.

> Once deployed, the connector will appear in Microsoft Sentinel under **Content Hub / Data Connectors**.

### Test the connector connection

Before deploying to Sentinel, you can validate that the connector can successfully reach your API directly from VS Code:

1. In the VS Code Explorer, right-click any file in `sentinel-connectors/NetworkLogAPI_CCF/`.
2. Select **Test Connector** from the context menu.
3. The agent reads your `NetworkLogAPI_PollingConfig.json` and establishes a live connection to the API using the auth, endpoint, pagination, and incremental pull settings defined by the connector builder agent.
4. A test result will confirm whether the API responded successfully, returned data at the expected JSON path (`$.data`), and that pagination (`$.metadata.nextLink`) resolved correctly.

> This is useful for catching config issues — wrong base URL, incorrect API key header name, or a mismatched events path — before the connector is deployed to a workspace.

### Key connector settings (for reference)

| CCF Setting | Value |
|---|---|
| Auth Type | `APIKey` |
| API Key Header | `X-API-Key` |
| Endpoint | `https://<FunctionAppName>.azurewebsites.net/api/GetNetworkLogs` |
| Pagination Type | `NextPageUrl` |
| Next Page URL Path | `$.metadata.nextLink` |
| Has Next Page Path | `$.metadata.hasNextPage` |
| Events Array Path | `$.data` |
| Timestamp Field | `timestamp` |
| Incremental Param | `since` |
| Custom Table | `NetworkLogAPINetworkLogs_CL` |

---

## Step 9 – Enable the Connector in Microsoft Sentinel

After deploying the connector package (Step 8), activate it from within the Sentinel workspace:

1. In the [Azure Portal](https://portal.azure.com), navigate to your **Microsoft Sentinel** workspace.
2. Go to **Content Hub** → **Data Connectors** and find **NetworkLogAPI**.
3. Click **Open connector page**.
4. In the connector configuration panel, fill in the two required fields:
   - **Base URL** – the Function App base URL from Step 5, e.g. `https://<FunctionAppName>.azurewebsites.net`
   - **API Key** – the `ApiKey` value you set during deployment
5. Click **Connect**.
6. Use the **Test Connectivity** button to confirm a successful connection — a green status indicates the connector reached your API and validated the response correctly.

Once connected, data will begin appearing in the `NetworkLogAPINetworkLogs_CL` table in Log Analytics. Allow **5–20 minutes** for the first records to land.

You can verify ingestion with this query in Log Analytics:

```kusto
NetworkLogAPINetworkLogs_CL
| sort by TimeGenerated desc
| take 10
```

---

## Step 10 – Refresh Data (Optional)

Regenerate all 50 records with fresh timestamps to simulate a new batch of events:

```bash
curl -s -X POST -H "X-API-Key: <your-api-key>" \
  "https://<FunctionAppName>.azurewebsites.net/api/RefreshData"
```

---

## Updating the Function App Code

If you modify `function_app.py`, rebuild the zip, push it to GitHub, then restart the app:

```bash
# Rebuild the zip (run from repo root)
cd AzureFunctionNetworkLogAPI
zip -r NetworkLogAPI.zip function_app.py host.json requirements.txt
cd ..

# Commit and push
git add AzureFunctionNetworkLogAPI/NetworkLogAPI.zip
git commit -m "Update function app package"
git push

# Restart the Function App to load the new package
az webapp restart --name <FunctionAppName> --resource-group connectorBuilderAgent
```

---

## Cleaning Up

```bash
az group delete --name connectorBuilderAgent --yes --no-wait
```

---

## API Key Security Note

The API key is stored as an encrypted Azure App Setting (`NETWORK_LOG_API_KEY`). It is never logged or returned in any response. Treat it like a password.
