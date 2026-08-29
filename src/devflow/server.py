"""Simple HTTP server for Phase 6 interactive UI and analysis bridge."""

from __future__ import annotations

import json
import logging
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from devflow.config import Config
from devflow.input import accept_input
from devflow.context import build_context
from devflow.history import build_historical_context
from devflow.impact import build_impact_analysis
from devflow.risk import build_risk_analysis
from devflow.map import build_change_impact_map, write_frontend_graph_payload
from devflow.models.repository import RepositoryInputError
from devflow.models.change import ChangeRequestError
from devflow.report import build_developer_report, write_frontend_report_payload


logger = logging.getLogger(__name__)


class AnalysisResult:
    """Container for analysis results."""

    def __init__(self, success: bool, data: dict[str, Any] | None = None, error: str | None = None):
        self.success = success
        self.data = data or {}
        self.error = error


# Global analysis state
_analysis_in_progress = False
_analysis_result: AnalysisResult | None = None
_analysis_lock = threading.Lock()


def run_analysis(repository_url: str, change_description: str) -> AnalysisResult:
    """Execute the full Phase 1-6 pipeline for the given repository and change."""
    global _analysis_in_progress, _analysis_result

    with _analysis_lock:
        if _analysis_in_progress:
            return AnalysisResult(False, error="Analysis already in progress")
        _analysis_in_progress = True

    try:
        # Phase 1: Accept input
        try:
            repo, change = accept_input(repository_url, change_description)
        except (RepositoryInputError, ChangeRequestError) as exc:
            with _analysis_lock:
                _analysis_in_progress = False
            return AnalysisResult(False, error=f"Invalid input: {exc}")

        # Phase 2: Build context
        logger.info(f"Building context for {repo.owner}/{repo.name}")
        context = build_context(repo, change)
        if context.error:
            with _analysis_lock:
                _analysis_in_progress = False
            return AnalysisResult(False, error=f"Context error: {context.error}")

        # Phase 3: Build historical context
        logger.info("Building historical context")
        history = build_historical_context(repo, context)

        # Phase 4: Build impact analysis
        logger.info("Building impact analysis")
        impact = build_impact_analysis(context, history)
        if impact.error:
            with _analysis_lock:
                _analysis_in_progress = False
            return AnalysisResult(False, error=f"Impact analysis error: {impact.error}")

        # Phase 5: Build risk analysis
        logger.info("Building risk analysis")
        risk = build_risk_analysis(impact, context, history)

        # Phase 6: Build change impact map
        logger.info("Building change impact map")
        graph = build_change_impact_map(context, impact, risk, history)
        if graph.error:
            with _analysis_lock:
                _analysis_in_progress = False
            return AnalysisResult(False, error=f"Graph error: {graph.error}")

        report = build_developer_report(context, impact, risk, history)

        # Write payloads to frontend
        logger.info("Writing graph and report payloads to frontend")
        write_frontend_graph_payload(graph)
        write_frontend_report_payload(report)

        with _analysis_lock:
            _analysis_in_progress = False
            _analysis_result = AnalysisResult(
                True,
                data={
                    "graph": graph.to_dict(),
                    "report": report.to_dict(),
                },
            )

        return _analysis_result

    except Exception as exc:
        logger.error(f"Analysis failed: {exc}", exc_info=True)
        with _analysis_lock:
            _analysis_in_progress = False
        return AnalysisResult(False, error=f"Analysis failed: {exc}")


class DevFlowRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for DevFlow server."""

    # Disable logging to reduce noise
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Serve static analysis state
        if path == "/api/analysis-state":
            global _analysis_in_progress
            with _analysis_lock:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                result_data = _analysis_result.data if _analysis_result and _analysis_result.success else None
                graph_data = None
                report_data = None
                if isinstance(result_data, dict):
                    if "graph" in result_data:
                        graph_data = result_data.get("graph")
                        report_data = result_data.get("report")
                    else:
                        graph_data = result_data
                state = {
                    "in_progress": _analysis_in_progress,
                    "result": graph_data,
                    "report": report_data,
                    "error": _analysis_result.error if _analysis_result and not _analysis_result.success else None,
                }
                self.wfile.write(json.dumps(state).encode())
            return

        # Serve frontend files
        frontend_root = Path(__file__).resolve().parents[2] / "frontend"

        if path == "/devflow-report.json":
            report_file = frontend_root / "public" / "devflow-report.json"
            if report_file.exists():
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(report_file.read_bytes())
            else:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"findings":[],"next_actions":[],"evidence_gaps":[]}')
            return

        # Special handling for devflow-graph.json
        if path == "/devflow-graph.json":
            graph_file = frontend_root / "public" / "devflow-graph.json"
            if graph_file.exists():
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(graph_file.read_bytes())
            else:
                # No graph yet, return empty
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"nodes":[],"edges":[]}')
            return

        # Serve built frontend
        dist_dir = frontend_root / "dist"
        if dist_dir.exists():
            if path == "/":
                file_path = dist_dir / "index.html"
            else:
                file_path = dist_dir / path.lstrip("/")

            if file_path.is_file() and file_path.resolve().parent.resolve() == dist_dir.resolve():
                self.send_response(200)
                if path == "/" or path.endswith(".html"):
                    self.send_header("Content-type", "text/html")
                elif path.endswith(".js"):
                    self.send_header("Content-type", "application/javascript")
                elif path.endswith(".css"):
                    self.send_header("Content-type", "text/css")
                elif path.endswith(".json"):
                    self.send_header("Content-type", "application/json")
                else:
                    self.send_header("Content-type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
                return

            # Fall back to index.html for SPA routing
            if dist_dir.exists():
                index_file = dist_dir / "index.html"
                if index_file.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(index_file.read_bytes())
                    return

        # File not found
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        """Handle POST requests for analysis."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/api/analyze":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            try:
                payload = json.loads(body)
                repository_url = payload.get("repository_url", "").strip()
                change_description = payload.get("change_description", "").strip()

                if not repository_url or not change_description:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {"error": "Both repository_url and change_description are required"}
                        ).encode()
                    )
                    return

                # Run analysis in a background thread to avoid blocking
                result = run_analysis(repository_url, change_description)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()

                response = {
                    "success": result.success,
                    "data": result.data.get("graph") if result.success and isinstance(result.data, dict) else (result.data if result.success else None),
                    "report": result.data.get("report") if result.success and isinstance(result.data, dict) else None,
                    "error": result.error if not result.success else None,
                }
                self.wfile.write(json.dumps(response).encode())

            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        self.send_response(404)
        self.end_headers()


def start_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    auto_open_browser: bool = True,
    frontend_dir: Optional[str | Path] = None,
) -> HTTPServer:
    """Start the DevFlow HTTP server."""
    server = HTTPServer((host, port), DevFlowRequestHandler)
    url = f"http://{host}:{port}/"

    logger.info(f"DevFlow server starting at {url}")

    if auto_open_browser:
        # Give the server a moment to start before opening browser
        def open_browser():
            time.sleep(0.5)
            try:
                webbrowser.open(url)
                logger.info(f"Opened {url} in default browser")
            except Exception as exc:
                logger.warning(f"Could not open browser: {exc}")

        thread = threading.Thread(target=open_browser, daemon=True)
        thread.start()

    return server


def serve_forever(server: HTTPServer) -> None:
    """Run the server until interrupted."""
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDevFlow server stopped.")
        server.shutdown()
