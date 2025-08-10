from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
from openai import OpenAI

app = FastAPI()

BASE_URL = os.getenv("SERVER_URL")
ACCESS_KEY = "debugger"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "llama3-70b-8192"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

class AnalyzeRequest(BaseModel):
    pid: str

SKIP_FILES = {
    "task", "fd", "map_files", "fdinfo", "ns", "net",
    "mem", "pagemap", "cwd", "root", "exe", "stack",
    "smaps", "smaps_rollup", "mountstats", "clear_refs",
    # add more if needed
}

MAX_CONTENT_LENGTH = 2000  # max chars per file to send

def send_slack_alert(message: str):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL not set, skipping Slack alert.")
        return
    payload = {"text": message}
    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if resp.status_code == 200:
            print("Slack alert sent successfully.")
        else:
            print(f"Slack alert failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Error sending Slack alert: {e}")

def analyze_with_groq(pid: str, name: str, combined_content: str) -> str:
    prompt = f"""
You are a Linux diagnostics assistant. Here is combined content of various /proc/{pid} files for process '{name}':

{combined_content}

Analyze the content carefully.

- If you detect any anomaly (e.g., zombie state, crash, high memory usage, unusual threads), start your response with the word `ANOMALY:` followed by your detailed diagnosis and suggested next steps.
- If everything looks normal, start your response with `OK:` followed by a short confirmation.

Please keep your answer concise and structured accordingly.
"""
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
    return choice.message.content.strip()

@app.post("/analyze")
def analyze_pid(request: AnalyzeRequest):
    pid = request.pid

    # Fetch file list under /proc/{pid}
    files_resp = requests.get(f"{BASE_URL}/proc/{pid}?key={ACCESS_KEY}")
    if files_resp.status_code != 200:
        raise HTTPException(status_code=404, detail="PID not found or cannot list files")

    files_json = files_resp.json()
    files = files_json.get("files")
    if not files:
        raise HTTPException(status_code=404, detail="No files found for PID")

    combined_contents = []

    status_resp = requests.get(f"{BASE_URL}/proc/{pid}/status?key={ACCESS_KEY}")
    if status_resp.status_code == 200:
        proc_status = status_resp.json()
        name = proc_status.get("Name", f"pid_{pid}")
    else:
        name = f"pid_{pid}"

    for filename in files:
        if filename in SKIP_FILES:
            continue
        try:
            file_resp = requests.get(f"{BASE_URL}/proc/{pid}/{filename}?key={ACCESS_KEY}")
            if file_resp.status_code == 200:
                content = file_resp.text
                if len(content) > MAX_CONTENT_LENGTH:
                    content = content[:MAX_CONTENT_LENGTH] + "\n...[truncated]..."
                combined_contents.append(f"Filename: {filename}\nContent:\n{content}\n\n")
            else:
                combined_contents.append(f"Filename: {filename}\nContent: [Failed to read: status {file_resp.status_code}]\n\n")
        except Exception as e:
            combined_contents.append(f"Filename: {filename}\nContent: [Error reading file: {e}]\n\n")

    if not combined_contents:
        raise HTTPException(status_code=404, detail="No readable files found for PID")

    combined_text = "\n".join(combined_contents)

    try:
        analysis = analyze_with_groq(pid, name, combined_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq API error: {e}")

    if analysis.startswith("ANOMALY:"):
        alert_msg = f"*Alert:* Anomaly detected in PID {pid} ({name})\n\n{analysis}"
        send_slack_alert(alert_msg)

    return {"pid": pid, "name": name, "analysis": analysis}

