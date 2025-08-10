# AI_debugger

**AI_debugger** is a diagnostics toolkit designed to automate and enhance Linux process analysis using AI. It provides a distributed system for collecting process data, exposing system internals via HTTP, and analyzing them with an LLM (Groq API), optionally sending alerts to Slack.

## Features

- **Rust HTTP Server**: Exposes endpoints to list running processes, inspect `/proc/{pid}` directories, and read process status and files (with authentication).
- **Python FastAPI Analyzer**: Collects `/proc/{pid}` file contents, summarizes and analyzes with an LLM for anomalies, and can alert via Slack.
- **PID Sender**: Rust client to regularly fetch process IDs from the server and send them for analysis.
- **Docker Support**: Analyzer runs in a container for easy deployment.

## Architecture

```
+----------------------+
|   Rust HTTP Server   | <-- `/proc` data exposed via HTTP (port 7878)
+----------------------+
          ^
          |
          v
+----------------------+
|   PID Sender (Rust)  | <-- Scans server, sends PIDs to analyzer
+----------------------+
          |
          v
+----------------------+
| Python Analyzer API  | <-- Analyzes process files with Groq LLM, sends Slack alerts
+----------------------+
```

## Setup

### 1. Rust HTTP Server

- Navigate to `server/http_serv/`
- Build and run:
  ```sh
  cargo run
  ```
- Server listens on `0.0.0.0:7878`
- Endpoints:
  - `/` : List running processes and their resource usage
  - `/proc` : List all numeric PIDs
  - `/proc/{pid}` : List files in `/proc/{pid}`
  - `/proc/{pid}/{file}` : Read file contents (JSON for `status`, plain text otherwise)
- **Access control**: All endpoints require `?key=debugger` in the query string.

### 2. Python Analyzer (FastAPI)

- Navigate to `client/`
- Build Docker image
- Push to a container repository, or build with minikube's docker
- Add secret.yaml with the appropriate fields in k8s-resources
- Run:
  ```sh
  kubectl apply -f k8s-resources/
  ```
- API endpoint: `POST /analyze` with JSON `{ "pid": <pid> }`
- The analyzer:
  - Fetches all readable `/proc/{pid}` files and status
  - Summarizes and analyzes via Groq LLM
  - Detects anomalies (e.g. zombie process, high memory, crash)
  - Sends Slack alerts if configured

### 3. PID Sender

- Navigate to `client/pid_sender/`
- Build and run:
  ```sh
  cargo run
  ```
- Periodically fetches PIDs from server and requests analysis via Analyzer API.

## Environment Variables

- `SERVER_URL` — URL for Rust HTTP server (e.g., http://localhost:7878)
- `GROQ_API_KEY` — Groq LLM API key
- `SLACK_WEBHOOK_URL` — Slack webhook for alerts (optional)

## Security

- All API calls require the access key `debugger`.
- Analyzer skips sensitive or large `/proc/{pid}` files by default.
