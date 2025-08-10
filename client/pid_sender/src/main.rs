use futures::{stream, StreamExt};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::{error::Error, time::Duration};
use tokio::time::sleep;

const RUST_SERVER_URL: &str = "http://localhost:7878";
const API_KEY: &str = "debugger";
const ANALYZER_INGRESS_URL: &str = "http://analyzer.example.com/analyze";
const MAX_CONCURRENT_REQUESTS: usize = 10; // tune concurrency here

#[derive(Deserialize)]
struct PidResponse {
    pids: Vec<String>,
}

#[derive(Serialize)]
struct AnalyzeRequest {
    pid: String,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let client = Client::new();

    loop {
        let pids = get_pids(&client).await?;
        println!("Found {} PIDs to analyze.", pids.len());

        stream::iter(pids)
            .map(|pid| {
                let client = &client;
                async move {
                    send_pid(client, pid).await;
                    sleep(Duration::from_millis(100)).await; // small delay between starts if needed
                }
            })
            .buffer_unordered(MAX_CONCURRENT_REQUESTS)
            .for_each(|_| async {})
            .await;

        println!("Cycle complete, sleeping for 10 seconds...");
        sleep(Duration::from_secs(10)).await;
    }
}

async fn get_pids(client: &Client) -> Result<Vec<u32>, Box<dyn Error>> {
    let url = format!("{}/proc?key={}", RUST_SERVER_URL, API_KEY);
    let resp = client.get(&url).send().await?;

    if !resp.status().is_success() {
        Err(format!("Failed to fetch PIDs: HTTP {}", resp.status()))?
    }

    let json: PidResponse = resp.json().await?;
    let mut result = Vec::new();
    for pid_str in json.pids {
        match pid_str.parse::<u32>() {
            Ok(pid) => result.push(pid),
            Err(_) => eprintln!("Warning: invalid pid string '{}', skipping", pid_str),
        }
    }
    Ok(result)
}

async fn send_pid(client: &Client, pid: u32) {
    let payload = AnalyzeRequest { pid: pid.to_string() };

    match client.post(ANALYZER_INGRESS_URL).json(&payload).send().await {
        Ok(resp) => {
            if resp.status().is_success() {
                match resp.json::<serde_json::Value>().await {
                    Ok(json) => {
                        println!("PID {} analyzed successfully.", pid);
                        println!("Response: {}", json);
                    }
                    Err(e) => eprintln!("Failed to parse JSON response for PID {}: {}", pid, e),
                }
            } else {
                let status = resp.status();
                let text = resp.text().await.unwrap_or_default();
                eprintln!("Failed to analyze PID {}: {} - {}", pid, status, text);
            }
        }
        Err(e) => eprintln!("Error sending PID {}: {}", pid, e),
    }
}

