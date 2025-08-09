import os
import time
import requests
from openai import OpenAI

# CONFIGURATION
BASE_URL = "http://localhost:7878"
ACCESS_KEY = "debugger"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "llama3-70b-8192"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

def send_slack_alert(message: str):
    if not SLACK_WEBHOOK_URL:
        print("WARNING: SLACK_WEBHOOK_URL not set. Skipping Slack alert.")
        return

    payload = {"text": message}

    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if resp.status_code == 200:
            print("Slack alert sent.")
        else:
            print(f"Slack alert failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Error sending Slack alert: {e}")

def fetch_process_list():
    try:
        response = requests.get(f"{BASE_URL}/?key={ACCESS_KEY}")
        if response.status_code == 200:
            return response.json().get("processes", [])
    except Exception as e:
        print(f"Failed to fetch process list: {e}")
    return []

def fetch_proc_status(pid):
    try:
        response = requests.get(f"{BASE_URL}/proc/{pid}/status?key={ACCESS_KEY}")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Failed to fetch /proc/{pid}/status: {e}")
    return None

def analyze_with_groq(pid, name, proc_status):
    prompt = f"""
You are a Linux diagnostics assistant. Here is `/proc/{pid}/status` for process '{name}':

{proc_status}

Analyze it carefully.

- If you detect any anomaly (e.g., zombie state, crash, high memory usage, unusual threads), start your response with the word `ANOMALY:` followed by your detailed diagnosis and suggested next steps.
- If everything looks normal, start your response with `OK:` followed by a short confirmation.

Please keep your answer concise and structured accordingly.
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful Linux diagnostics assistant who provides detailed and complete explanations."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.3,
        )
        choice = response.choices[0]
        print("Finish reason:", choice.finish_reason)  # For debugging
        return choice.message.content.strip()
    except Exception as e:
        print(f"Groq API error (PID {pid}): {e}")
        return None

def main():
    while True:
        print("Fetching process list...")
        procs = fetch_process_list()
        if not procs:
            print("WARNING: No processes found or failed to fetch.")
            time.sleep(60)
            continue

        for proc in procs:
            pid = proc.get("pid")
            name = proc.get("name", "unknown")
            if not pid:
                continue

            status = fetch_proc_status(pid)
            if not status:
                print(f"WARNING: Skipping PID {pid} ({name}) — no status.")
                continue

            print(f"Analyzing PID {pid} ({name})...")
            analysis = analyze_with_groq(pid, name, status)
            if analysis:
                if analysis.startswith("ANOMALY:"):
                    alert_msg = f"*Alert:* Issue detected on PID {pid} ({name})\n\n{analysis}"
                    send_slack_alert(alert_msg)
                else:
                    print(f"No anomaly for PID {pid} ({name}): {analysis}")
            else:
                print(f"No analysis for PID {pid} ({name})")

        print("Sleeping 60 seconds...\n")
        time.sleep(60)

if __name__ == "__main__":
    required_env = ["GROQ_API_KEY", "SLACK_WEBHOOK_URL"]
    missing = [var for var in required_env if not os.getenv(var)]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}")
    else:
        main()

