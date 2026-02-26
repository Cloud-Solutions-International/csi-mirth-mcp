"""
DPA MCP Server — read-only tools for SolarWinds Database Performance Analyzer.
Auth: session cookie (username/password login via /iwc/login.iwc).
"""

import os
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import http.cookiejar
from typing import Any

from mcp.server.fastmcp import FastMCP

# ── Config (env vars with fallbacks) ─────────────────────────────────────────
DPA_BASE = os.environ.get("DPA_BASE_URL", "https://10.4.41.188:8124")
DPA_USER = os.environ.get("DPA_USERNAME", "dbmon121")
DPA_PASS = os.environ.get("DPA_PASSWORD", "")

# ── HTTP session ──────────────────────────────────────────────────────────────
# Ignore self-signed cert
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=_ssl_ctx),
    urllib.request.HTTPCookieProcessor(_cookie_jar),
)


def _get(path: str, params: dict | None = None) -> Any:
    """GET a /iwc/rest/ endpoint, auto-login if needed. Returns parsed JSON data."""
    url = DPA_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with _opener.open(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            # If we got redirected to the login page the session expired
            if isinstance(body, dict) and "data" in body:
                return body["data"]
            # Unexpected shape — return raw
            return body
    except urllib.error.HTTPError as e:
        if e.code == 302:
            _login()
            return _get(path, params)
        raise RuntimeError(f"HTTP {e.code} from {path}: {e.read().decode()[:200]}")


def _login() -> None:
    """Log in to DPA and populate the cookie jar with a valid JSESSIONID."""
    # Step 1: GET login page to get JSESSIONID + CSRF token
    req = urllib.request.Request(
        DPA_BASE + "/iwc/login.iwc",
        headers={"Accept": "text/html"},
    )
    with _opener.open(req, timeout=10) as resp:
        html = resp.read().decode()

    # Extract CSRF token
    csrf = ""
    marker = 'name="_csrf" value="'
    idx = html.find(marker)
    if idx != -1:
        start = idx + len(marker)
        end = html.index('"', start)
        csrf = html[start:end]

    # Step 2: POST login
    data = urllib.parse.urlencode({
        "user": DPA_USER,
        "password": DPA_PASS,
        "_csrf": csrf,
    }).encode()

    req = urllib.request.Request(
        DPA_BASE + "/iwc/login.iwc",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Don't follow the redirect — we just want the Set-Cookie header
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def http_error_302(self, req, fp, code, msg, headers):
            return fp

    no_redirect_opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_ctx),
        urllib.request.HTTPCookieProcessor(_cookie_jar),
        _NoRedirect(),
    )
    no_redirect_opener.open(req, timeout=10)


# Login on startup
_login()

# ── MCP server ────────────────────────────────────────────────────────────────
mcp = FastMCP("dpa")


@mcp.tool()
def get_server_info() -> dict:
    """
    Return DPA server metadata: version, timezone, license state,
    repository type, and server time.
    """
    return _get("/iwc/rest/server-info")


@mcp.tool()
def get_user_info() -> dict:
    """
    Return information about the currently authenticated DPA user,
    including their role and permissions flags.
    """
    return _get("/iwc/rest/user-info")


@mcp.tool()
def get_database_permissions() -> dict:
    """
    Return the current user's per-database permissions: which database IDs
    they can view performance data for, manage alerts on, etc.
    """
    return _get("/iwc/rest/databases/permissions/details")


@mcp.tool()
def list_databases() -> list:
    """
    List all databases monitored by DPA.
    Each entry includes: id, name, type, version, monitoringState,
    deployment, host, lastDataPoint, and feature flags (PDB, RAC, etc.).
    """
    return _get("/iwc/rest/databases")


@mcp.tool()
def get_database(db_id: int) -> dict:
    """
    Return full detail for a single monitored database.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}")


@mcp.tool()
def get_top_instances() -> dict:
    """
    Return the 'Instances with highest wait time' dashboard chart data.
    Shows daily average wait time (seconds) per database over the last ~14 days.
    Useful for identifying which database is performing worst.
    """
    return _get("/iwc/rest/dashboards/top-instances", {"pm": "P"})


@mcp.tool()
def get_upward_trends() -> dict:
    """
    Return databases with the greatest upward (worsening) wait time trend.
    Shows the percentage increase in wait time per day over the last ~14 days.
    """
    return _get("/iwc/rest/dashboards/upwards-trends", {"pm": "P"})


@mcp.tool()
def get_downward_trends() -> dict:
    """
    Return databases with the greatest downward (improving) wait time trend.
    Shows the percentage decrease in wait time per day over the last ~14 days.
    """
    return _get("/iwc/rest/dashboards/downwards-trends", {"pm": "P"})


@mcp.tool()
def get_database_tab_health(db_id: int) -> dict:
    """
    Return the health/alarm level for each main tab of a database:
    tuning, trends, resources, and AG (availability group) health.
    Useful for a quick status overview before drilling in.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/super-tab", {"pmCode": "P"})


@mcp.tool()
def get_database_permissions_detail(db_id: int) -> dict:
    """
    Return the current user's permissions for a specific database:
    viewPerformanceData, viewAlerts, manageAlerts, manageMonitoring, manageReporting.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/permissions")


@mcp.tool()
def list_metric_categories(db_id: int) -> list:
    """
    Return all available performance metric categories and metric names for a database.
    Use this to discover valid metric names before calling get_metric_data.
    Categories include: Connections, CPU, Memory, Disk, Network, Sessions, Waits, etc.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/metrics/categories", {"require": "metrics"})


@mcp.tool()
def get_metric_data(db_id: int, metrics: str, start_time: str, end_time: str) -> list:
    """
    Return time-series data for one or more performance metrics.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
        metrics: Comma-separated metric names, e.g. "CPU Utilization,Total User Sessions".
                 Use list_metric_categories to discover valid names.
        start_time: ISO 8601 start time, e.g. "2026-02-24T05:00:00Z".
        end_time:   ISO 8601 end time,   e.g. "2026-02-24T08:00:00Z".
    """
    return _get(f"/iwc/rest/databases/{db_id}/metrics/data", {
        "metrics": metrics,
        "startTime": start_time,
        "endTime": end_time,
        "useResourceGranularities": "true",
        "baseline": "false",
    })


@mcp.tool()
def get_tuning_dates(db_id: int) -> list:
    """
    Return a list of recent dates with tuning advice available, including:
    alarm level (WARNING/NORMAL), query advice count, and index advice count per day.
    Use this to find which days had the most problems before fetching sql_advices.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/dates/tuning")


@mcp.tool()
def get_sql_advices(db_id: int, date: str) -> dict:
    """
    Return the top problematic SQL queries for a given date, including:
    sqlHash, sqlName, status (WARNING/etc), execution percentage, and
    human-readable problem summaries (e.g. "Had high executions during 4:00 AM hour").

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
        date:  Date in YYYY-MM-DD format, e.g. "2026-02-24".
               Use get_tuning_dates to find dates with issues.
    """
    return _get(f"/iwc/rest/databases/{db_id}/problems/sql-advices", {"date": date})


@mcp.tool()
def get_index_recommendations(db_id: int, day: str) -> dict:
    """
    Return index recommendations (what-if analysis) for a given day, including:
    the CREATE INDEX SQL, estimated wait time savings, schema, and table name.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
        day:   Date in YYYY-MM-DD format, e.g. "2026-02-23".
               Use get_tuning_dates to find days with index advice.
    """
    return _get(f"/iwc/rest/databases/{db_id}/what-if", {"day": day})


@mcp.tool()
def list_sql_stat_types(db_id: int) -> list:
    """
    Return the available SQL statistic types for a database
    (e.g. Executions, Disk Reads, Buffer Gets, Rows Processed, Sorts, Parses).
    These IDs can be used when analysing SQL performance characteristics.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/sql-stats/types")


if __name__ == "__main__":
    mcp.run()
