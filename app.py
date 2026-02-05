import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
import psycopg2
from flask import Flask, jsonify, request

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("flexis-orders")

app = Flask(__name__)

ORDERS: list[Dict[str, Any]] = []

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
SQS_POLL_SECONDS = int(os.getenv("SQS_POLL_SECONDS", "10"))
SQS_ENABLED = bool(SQS_QUEUE_URL)

sqs_client = boto3.client("sqs") if SQS_ENABLED else None


INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Flexicx Order Processing</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 32px; }
      h1 { margin-bottom: 8px; }
      .card { border: 1px solid #ddd; padding: 16px; border-radius: 8px; max-width: 720px; }
      label { display: block; margin-top: 12px; }
      input, textarea { width: 100%; padding: 8px; margin-top: 4px; }
      button { margin-top: 12px; padding: 10px 16px; }
      .orders { margin-top: 24px; }
      .order { padding: 8px 0; border-bottom: 1px solid #eee; }
      .muted { color: #666; font-size: 12px; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Flexicx Order Processing</h1>
      <p class="muted">This is a simple demo app that submits orders and pushes them to SQS.</p>
      <form id="order-form">
        <label>Customer Name
          <input name="customer" required />
        </label>
        <label>Order Notes
          <textarea name="notes" rows="3"></textarea>
        </label>
        <button type="submit">Submit Order</button>
      </form>
      <div class="orders">
        <h3>Recent Orders</h3>
        <div id="orders"></div>
      </div>
    </div>
    <script>
      async function loadOrders() {
        const res = await fetch('/api/orders');
        const data = await res.json();
        const container = document.getElementById('orders');
        container.innerHTML = '';
        (data.orders || []).forEach(order => {
          const div = document.createElement('div');
          div.className = 'order';
          div.innerHTML = `<strong>${order.customer}</strong> - ${order.id}<div class="muted">${order.createdAt}</div>`;
          container.appendChild(div);
        });
      }

      document.getElementById('order-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = event.target;
        const payload = {
          customer: form.customer.value,
          notes: form.notes.value
        };
        await fetch('/api/orders', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        form.reset();
        await loadOrders();
      });

      loadOrders();
    </script>
  </body>
</html>
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_config() -> Optional[dict[str, Any]]:
    host = os.getenv("DB_HOST")
    if not host:
        return None

    return {
        "host": host,
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "orders"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD"),
        "connect_timeout": 5,
    }


def send_to_sqs(order: dict[str, Any]) -> None:
    if not SQS_ENABLED or sqs_client is None:
        return

    try:
        sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(order),
        )
    except Exception:
        logger.exception("failed to send order to SQS")


def poll_sqs() -> None:
    if not SQS_ENABLED or sqs_client is None:
        return

    logger.info("starting SQS poller")
    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=SQS_POLL_SECONDS,
                VisibilityTimeout=30,
            )
            for message in response.get("Messages", []):
                logger.info("received order message: %s", message.get("Body"))
                sqs_client.delete_message(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                )
        except Exception:
            logger.exception("error while polling SQS")
            time.sleep(5)


@app.route("/")
def index() -> str:
    return INDEX_HTML


@app.route("/api/orders", methods=["GET"])
def list_orders() -> Any:
    return jsonify({"orders": ORDERS[:20]})


@app.route("/api/orders", methods=["POST"])
def create_order() -> Any:
    payload = request.get_json(silent=True) or request.form or {}
    order = {
        "id": str(uuid.uuid4()),
        "customer": payload.get("customer", "anonymous"),
        "notes": payload.get("notes", ""),
        "createdAt": now_iso(),
    }
    ORDERS.insert(0, order)
    send_to_sqs(order)
    return jsonify(order), 201


@app.route("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.route("/db-check")
def db_check() -> Any:
    cfg = db_config()
    if not cfg or not cfg.get("password"):
        return jsonify({"status": "skipped", "reason": "missing db env"})

    try:
        conn = psycopg2.connect(**cfg)
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as exc:
        logger.exception("db check failed")
        return jsonify({"status": "error", "error": str(exc)}), 503


if SQS_ENABLED:
    thread = threading.Thread(target=poll_sqs, daemon=True)
    thread.start()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
