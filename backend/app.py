"""Flask entry point for the course project scaffold."""

import os
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify

from backend.shared.catalog import MODULES
from backend.shared.db import database_ready

app = Flask(__name__)


def response(data, status=200):
    return jsonify(data=data, request_id=uuid4().hex), status


@app.get("/api/v1/health")
def health():
    db_path = Path(os.environ.get("DATABASE_PATH", "instance/app.db"))
    db_ready = database_ready(db_path)
    jar_path = os.environ.get("LOGISIM_JAR_PATH")
    # The worker and sandbox are not implemented yet; a JAR alone is not readiness.
    grader_ready = False
    status = "ready" if db_ready and grader_ready else "degraded"
    return response(
        {
            "web_ready": True,
            "db_ready": db_ready,
            "grader_ready": grader_ready,
            "status": status,
            "grader_configured": bool(jar_path and Path(jar_path).is_file()),
        },
        200 if status == "ready" else 503,
    )


@app.get("/api/v1/modules")
def modules():
    return response(MODULES)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
