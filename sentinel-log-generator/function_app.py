import azure.functions as func
import logging
import json
import os
import random
import string
import time
import requests
from datetime import datetime, timezone

app = func.FunctionApp()

# ---------------------------------------------------------------------------
# Token cache (module-level so it persists across warm invocations)
# ---------------------------------------------------------------------------
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _get_bearer_token() -> str:
    """Return a cached OAuth 2.0 bearer token, refreshing when necessary."""
    now = time.time()
    # Refresh 60 seconds before actual expiry to avoid edge-case 401s
    if _token_cache["access_token"] and _token_cache["expires_at"] - now > 60:
        return _token_cache["access_token"]

    tenant_id = os.environ["TENANT_ID"]
    client_id = os.environ["CLIENT_ID"]
    client_secret = os.environ["CLIENT_SECRET"]

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://monitor.azure.com/.default",
    }

    response = requests.post(url, data=payload, timeout=30)
    response.raise_for_status()
    token_data = response.json()

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + int(token_data.get("expires_in", 3600))
    logging.info("Acquired new bearer token (expires in %ss)", token_data.get("expires_in"))
    return _token_cache["access_token"]


# ---------------------------------------------------------------------------
# Log generation helpers
# ---------------------------------------------------------------------------
_SEVERITIES = ["Low", "Medium", "High"]
_MESSAGES = [
    "Suspicious login attempt detected",
    "Port scan activity observed",
    "Brute-force attack blocked",
    "Malware signature matched in network traffic",
    "Unauthorized API call from unknown IP",
    "Privilege escalation attempt detected",
    "Data exfiltration pattern identified",
    "SQL injection probe blocked",
    "Unusual outbound traffic volume",
    "Command-and-control beacon detected",
]


def _random_device_id(length: int = 8) -> str:
    return "DEV-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _generate_log_batch(count: int) -> list[dict]:
    """Generate *count* fake security log records."""
    return [
        {
            "TimeGenerated": datetime.now(timezone.utc).isoformat(),
            "DeviceId": _random_device_id(),
            "Severity": random.choice(_SEVERITIES),
            "EventMessage": random.choice(_MESSAGES),
        }
        for _ in range(count)
    ]


# ---------------------------------------------------------------------------
# Ingestion with retry logic
# ---------------------------------------------------------------------------
def _send_logs(logs: list[dict]) -> None:
    """POST a batch of logs to the Azure Monitor Logs Ingestion endpoint."""
    dce = os.environ["DATA_COLLECTION_ENDPOINT"].rstrip("/")
    dcr_id = os.environ["DATA_COLLECTION_RULE_ID"]
    stream_name = os.environ["STREAM_NAME"]

    url = f"{dce}/dataCollectionRules/{dcr_id}/streams/{stream_name}?api-version=2023-01-01"
    body = json.dumps(logs)

    max_attempts = 5
    base_delay = 2  # seconds

    for attempt in range(1, max_attempts + 1):
        token = _get_bearer_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, data=body, timeout=30)

            if resp.status_code == 204:
                logging.info("Successfully ingested %d log(s) on attempt %d", len(logs), attempt)
                return

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", base_delay * attempt))
                logging.warning(
                    "Rate-limited (429). Waiting %ds before retry %d/%d",
                    retry_after, attempt, max_attempts,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code in {500, 502, 503, 504}:
                delay = base_delay * (2 ** (attempt - 1))  # exponential back-off
                logging.warning(
                    "Transient error %d. Waiting %ds before retry %d/%d",
                    resp.status_code, delay, attempt, max_attempts,
                )
                time.sleep(delay)
                continue

            # Non-retryable error
            resp.raise_for_status()

        except requests.exceptions.Timeout:
            delay = base_delay * (2 ** (attempt - 1))
            logging.warning("Request timed out. Waiting %ds before retry %d/%d", delay, attempt, max_attempts)
            time.sleep(delay)

        except requests.exceptions.RequestException as exc:
            logging.error("Non-retryable request error: %s", exc)
            raise

    raise RuntimeError(f"Failed to ingest logs after {max_attempts} attempts")


# ---------------------------------------------------------------------------
# Timer-triggered Azure Function (runs every minute)
# ---------------------------------------------------------------------------
@app.timer_trigger(
    schedule="0 */1 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=False,
)
def log_generator(timer: func.TimerRequest) -> None:
    """Generate fake security logs and push them to Microsoft Sentinel via DCE."""
    if timer.past_due:
        logging.info("Timer is past due — running now.")

    batch_size = random.randint(5, 10)
    logging.info("Generating a batch of %d security log(s)...", batch_size)

    logs = _generate_log_batch(batch_size)
    logging.debug("Sample log: %s", json.dumps(logs[0], indent=2))

    _send_logs(logs)
    logging.info("Log ingestion complete.")
