"""Generate HTML reports for load testing results."""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LoadTestReportGenerator:
    """Generates comprehensive HTML reports for load test results."""

    def __init__(self, output_dir: str = "./load_test_reports"):
        """Initialize report generator.

        Args:
            output_dir: Directory to save reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_summary_report(self, metrics: dict[str, Any]) -> str:
        """Generate HTML summary report.

        Args:
            metrics: Dictionary containing test metrics

        Returns:
            Path to generated report
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"load_test_report_{timestamp}.html"

        auth_metrics = metrics.get("auth", {})
        generation_metrics = metrics.get("generation", {})
        payments_metrics = metrics.get("payments", {})

        html_content = self._generate_html(
            auth_metrics, generation_metrics, payments_metrics
        )

        with open(report_path, "w") as f:
            f.write(html_content)

        logger.info("report_generated", path=str(report_path))
        return str(report_path)

    @staticmethod
    def _generate_html(
        auth_metrics: dict[str, Any],
        generation_metrics: dict[str, Any],
        payments_metrics: dict[str, Any],
    ) -> str:
        """Generate HTML report content.

        Args:
            auth_metrics: Authentication API metrics
            generation_metrics: Generation API metrics
            payments_metrics: Payments API metrics

        Returns:
            HTML content as string
        """
        timestamp = datetime.now(UTC).isoformat()

        auth_pass = (
            auth_metrics.get("success_rate", 0) >= 99
            if auth_metrics else False
        )
        gen_pass = (
            generation_metrics.get("success_rate", 0) >= 95
            and generation_metrics.get("p95_response_time_ms", float("inf")) <= 500
            if generation_metrics else False
        )
        payment_pass = (
            payments_metrics.get("success_rate", 0) >= 95
            if payments_metrics else False
        )

        overall_pass = auth_pass and gen_pass and payment_pass

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Load Testing Report</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 40px;
                    text-align: center;
                }}
                .header h1 {{
                    font-size: 2.5em;
                    margin-bottom: 10px;
                }}
                .header p {{
                    font-size: 1.1em;
                    opacity: 0.9;
                }}
                .overall-status {{
                    display: flex;
                    justify-content: center;
                    gap: 20px;
                    margin-top: 20px;
                    flex-wrap: wrap;
                }}
                .status-badge {{
                    padding: 10px 20px;
                    border-radius: 20px;
                    font-weight: bold;
                    font-size: 1.1em;
                }}
                .status-pass {{
                    background: #4ade80;
                    color: white;
                }}
                .status-fail {{
                    background: #f87171;
                    color: white;
                }}
                .content {{
                    padding: 40px;
                }}
                .section {{
                    margin-bottom: 40px;
                }}
                .section-title {{
                    font-size: 1.8em;
                    margin-bottom: 20px;
                    color: #333;
                    border-bottom: 3px solid #667eea;
                    padding-bottom: 10px;
                }}
                .metrics-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-top: 15px;
                }}
                .metric-card {{
                    background: #f5f5f5;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .metric-label {{
                    font-size: 0.9em;
                    color: #666;
                    margin-bottom: 8px;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .metric-value {{
                    font-size: 1.8em;
                    font-weight: bold;
                    color: #333;
                }}
                .metric-unit {{
                    font-size: 0.8em;
                    color: #999;
                    margin-left: 5px;
                }}
                .success {{
                    color: #22c55e;
                }}
                .warning {{
                    color: #f59e0b;
                }}
                .error {{
                    color: #ef4444;
                }}
                .footer {{
                    background: #f5f5f5;
                    padding: 20px;
                    text-align: center;
                    color: #666;
                    font-size: 0.9em;
                    border-top: 1px solid #ddd;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                thead {{
                    background: #f5f5f5;
                }}
                th {{
                    padding: 12px;
                    text-align: left;
                    font-weight: bold;
                    color: #333;
                    border-bottom: 2px solid #ddd;
                }}
                td {{
                    padding: 12px;
                    border-bottom: 1px solid #eee;
                }}
                tr:hover {{
                    background: #f9f9f9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 Load Testing Report</h1>
                    <p>Performance Analysis - Auth, Generation & Payments APIs</p>
                    <div class="overall-status">
                        <div class="status-badge {'status-pass' if overall_pass else 'status-fail'}">
                            Overall: {'✓ PASS' if overall_pass else '✗ FAIL'}
                        </div>
                    </div>
                </div>

                <div class="content">
                    <p style="color: #666; margin-bottom: 30px;">
                        <strong>Generated:</strong> {timestamp}
                    </p>

                    {LoadTestReportGenerator._generate_section('Authentication API', auth_metrics, 'auth')}
                    {LoadTestReportGenerator._generate_section('Generation API', generation_metrics, 'generation')}
                    {LoadTestReportGenerator._generate_section('Payments API', payments_metrics, 'payments')}

                    <div class="section">
                        <h2 class="section-title">📋 Acceptance Criteria</h2>
                        <table>
                            <thead>
                                <tr>
                                    <th>Criterion</th>
                                    <th>Required</th>
                                    <th>Actual</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td>Auth Success Rate</td>
                                    <td>≥ 99%</td>
                                    <td>{auth_metrics.get('success_rate', 0):.2f}%</td>
                                    <td class="{'success' if auth_pass else 'error'}">{'✓' if auth_pass else '✗'}</td>
                                </tr>
                                <tr>
                                    <td>Generation Success Rate</td>
                                    <td>≥ 95%</td>
                                    <td>{generation_metrics.get('success_rate', 0):.2f}%</td>
                                    <td class="{'success' if gen_pass else 'error'}">{'✓' if gen_pass else '✗'}</td>
                                </tr>
                                <tr>
                                    <td>Generation P95 Latency</td>
                                    <td>≤ 500ms</td>
                                    <td>{generation_metrics.get('p95_response_time_ms', 0):.2f}ms</td>
                                    <td class="{'success' if generation_metrics.get('p95_response_time_ms', float('inf')) <= 500 else 'error'}">{'✓' if generation_metrics.get('p95_response_time_ms', float('inf')) <= 500 else '✗'}</td>
                                </tr>
                                <tr>
                                    <td>Payments Success Rate</td>
                                    <td>≥ 95%</td>
                                    <td>{payments_metrics.get('success_rate', 0):.2f}%</td>
                                    <td class="{'success' if payment_pass else 'error'}">{'✓' if payment_pass else '✗'}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="footer">
                    <p>Load Testing Report | Generated on {timestamp}</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    @staticmethod
    def _generate_section(
        title: str, metrics: dict[str, Any], section_id: str
    ) -> str:
        """Generate a metrics section.

        Args:
            title: Section title
            metrics: Metrics data
            section_id: Section identifier

        Returns:
            HTML for the section
        """
        if not metrics:
            return ""

        return f"""
            <div class="section">
                <h2 class="section-title">{title}</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">Total Requests</div>
                        <div class="metric-value">{metrics.get('total_requests', 0)}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Success Rate</div>
                        <div class="metric-value">
                            <span class="{'success' if metrics.get('success_rate', 0) >= 95 else 'warning'}">{metrics.get('success_rate', 0):.2f}%</span>
                        </div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Error Rate</div>
                        <div class="metric-value">
                            <span class="{'success' if metrics.get('error_rate', 0) < 5 else 'error'}">{metrics.get('error_rate', 0):.2f}%</span>
                        </div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Avg Response Time</div>
                        <div class="metric-value">{metrics.get('avg_response_time_ms', 0):.2f}<span class="metric-unit">ms</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">P95 Response Time</div>
                        <div class="metric-value">{metrics.get('p95_response_time_ms', 0):.2f}<span class="metric-unit">ms</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">P99 Response Time</div>
                        <div class="metric-value">{metrics.get('p99_response_time_ms', 0):.2f}<span class="metric-unit">ms</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Min Response Time</div>
                        <div class="metric-value">{metrics.get('min_response_time_ms', 0):.2f}<span class="metric-unit">ms</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Max Response Time</div>
                        <div class="metric-value">{metrics.get('max_response_time_ms', 0):.2f}<span class="metric-unit">ms</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Test Duration</div>
                        <div class="metric-value">{metrics.get('test_duration_seconds', 0):.2f}<span class="metric-unit">s</span></div>
                    </div>
                </div>
            </div>
        """

    @staticmethod
    def generate_json_report(metrics: dict[str, Any], output_path: str) -> None:
        """Generate JSON report for CI/CD integration.

        Args:
            metrics: Metrics data
            output_path: Path to save JSON report
        """
        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": metrics,
            "thresholds": {
                "auth_success_rate": 0.99,
                "generation_success_rate": 0.95,
                "generation_p95_latency_ms": 500,
                "payments_success_rate": 0.95,
            },
            "pass": (
                metrics.get("auth", {}).get("success_rate", 0) >= 99
                and metrics.get("generation", {}).get("success_rate", 0) >= 95
                and metrics.get("generation", {}).get("p95_response_time_ms", float("inf")) <= 500
                and metrics.get("payments", {}).get("success_rate", 0) >= 95
            ),
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info("json_report_generated", path=output_path)
