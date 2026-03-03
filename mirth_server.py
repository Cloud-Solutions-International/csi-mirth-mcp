"""
Mirth Connect Read-Only MCP Server — FastMCP over stdio.
Auth: cookie-based session (POST /api/users/_login with username/password).
Only stdlib + mcp are used; all tools are GET/read-only.
"""

import os
import json
import ssl
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

# ── Config (env vars) ────────────────────────────────────────────────────────
MIRTH_URL = os.environ.get("MIRTH_URL", "").rstrip("/")
MIRTH_USER = os.environ.get("MIRTH_USERNAME", "")
MIRTH_PASS = os.environ.get("MIRTH_PASSWORD", "")
PREFIX = os.environ.get("ENV_PREFIX", "")

# ── HTTP session (ignore self-signed certs by default) ───────────────────────
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=_ssl_ctx),
    urllib.request.HTTPCookieProcessor(_cookie_jar),
)

# ── Helpers ──────────────────────────────────────────────────────────────────
def _prepare_params(params: Optional[dict]) -> Optional[dict]:
    """Convert booleans to lowercase strings and join list-like params."""
    if not params:
        return None
    out: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            # Join lists by comma for convenience unless caller pre-encoded
            out[k] = ",".join(str(x) for x in v)
        else:
            out[k] = v
    return out or None


def _login() -> None:
    """Log in to Mirth Connect; cookie jar will retain JSESSIONID."""
    if not MIRTH_URL or not MIRTH_USER:
        raise RuntimeError("MIRTH_URL/MIRTH_USERNAME not set in environment")

    data = urllib.parse.urlencode(
        {"username": MIRTH_USER, "password": MIRTH_PASS}
    ).encode()
    req = urllib.request.Request(
        MIRTH_URL + "/api/users/_login",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        # Open and drain response; cookies captured by HTTPCookieProcessor
        with _opener.open(req, timeout=15) as _:
            pass
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        raise RuntimeError(f"Login failed HTTP {e.code}: {body or e.reason}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Login failed: {getattr(e, 'reason', str(e))}") from None


def _get(path: str, params: Optional[dict] = None, raw: bool = False, _retried: bool = False) -> Any:
    """Generic GET helper for Mirth API. Handles 401 by re-login once."""
    if not MIRTH_URL:
        raise RuntimeError("MIRTH_URL not set in environment")
    q = _prepare_params(params)
    url = MIRTH_URL + path
    if q:
        url += "?" + urllib.parse.urlencode(q)
    headers = {"Accept": "text/plain" if raw else "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _opener.open(req, timeout=20) as resp:
            data = resp.read()
            text = data.decode(errors="replace")
            if raw:
                return text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Some endpoints may reply with text/plain unexpectedly
                return text
    except urllib.error.HTTPError as e:
        if e.code == 401 and not _retried:
            _login()
            return _get(path, params, raw=raw, _retried=True)
        # Some deployments might redirect; attempt a re-login on 302 as a fallback
        if e.code in (301, 302, 303, 307, 308) and not _retried:
            _login()
            return _get(path, params, raw=raw, _retried=True)
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} for {path}: {body or e.reason}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error for {path}: {getattr(e, 'reason', str(e))}") from None


# ── MCP server (stdio) ───────────────────────────────────────────────────────
mcp = FastMCP("mirth")

# Login on startup
_login()

# ── Channels (5) ─────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_channels")
def get_channels(
    channelId: Optional[str] = None,
    pollingOnly: Optional[bool] = None,
    includeCodeTemplateLibraries: Optional[bool] = None,
):
    """List channels."""
    return _get(
        "/api/channels",
        {
            "channelId": channelId,
            "pollingOnly": pollingOnly,
            "includeCodeTemplateLibraries": includeCodeTemplateLibraries,
        },
    )


@mcp.tool(name=f"{PREFIX}-get_channel")
def get_channel(channelId: str, includeCodeTemplateLibraries: Optional[bool] = None):
    """Get a specific channel by ID."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}",
        {"includeCodeTemplateLibraries": includeCodeTemplateLibraries},
    )


@mcp.tool(name=f"{PREFIX}-get_channel_ids_and_names")
def get_channel_ids_and_names():
    """Get channel IDs and names."""
    return _get("/api/channels/idsAndNames")


@mcp.tool(name=f"{PREFIX}-get_connector_names")
def get_connector_names(channelId: str):
    """Get connector names for a channel."""
    return _get(f"/api/channels/{urllib.parse.quote(channelId)}/connectorNames")


@mcp.tool(name=f"{PREFIX}-get_metadata_columns")
def get_metadata_columns(channelId: str):
    """Get metadata columns for a channel."""
    return _get(f"/api/channels/{urllib.parse.quote(channelId)}/metaDataColumns")


# ── Channel Groups (1) ───────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_channel_groups")
def get_channel_groups(channelGroupId: Optional[str] = None):
    """List channel groups or get by ID."""
    return _get("/api/channelgroups", {"channelGroupId": channelGroupId})


# ── Channel Statistics (2) ───────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_channel_statistics")
def get_channel_statistics(
    channelId: Optional[str] = None,
    includeUndeployed: Optional[bool] = None,
    includeMetadataId: Optional[str] = None,
    excludeMetadataId: Optional[str] = None,
    aggregateStats: Optional[bool] = None,
):
    """Get channel statistics (optionally filtered)."""
    return _get(
        "/api/channels/statistics",
        {
            "channelId": channelId,
            "includeUndeployed": includeUndeployed,
            "includeMetadataId": includeMetadataId,
            "excludeMetadataId": excludeMetadataId,
            "aggregateStats": aggregateStats,
        },
    )


@mcp.tool(name=f"{PREFIX}-get_channel_statistics_by_id")
def get_channel_statistics_by_id(channelId: str):
    """Get statistics for a specific channel."""
    return _get(f"/api/channels/{urllib.parse.quote(channelId)}/statistics")


# ── Channel Status (3) ───────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_channel_status_list")
def get_channel_status_list(
    channelId: Optional[str] = None,
    filter: Optional[str] = None,
    includeUndeployed: Optional[bool] = None,
):
    """Get channel status list (with optional filter)."""
    return _get(
        "/api/channels/statuses",
        {"channelId": channelId, "filter": filter, "includeUndeployed": includeUndeployed},
    )


@mcp.tool(name=f"{PREFIX}-get_channel_status")
def get_channel_status(channelId: str):
    """Get status for a channel."""
    return _get(f"/api/channels/{urllib.parse.quote(channelId)}/status")


@mcp.tool(name=f"{PREFIX}-get_dashboard_channel_info")
def get_dashboard_channel_info(
    fetchSize: Optional[int] = None, filter: Optional[str] = None
):
    """Initial dashboard channel info."""
    return _get("/api/channels/statuses/initial", {"fetchSize": fetchSize, "filter": filter})


# ── Alerts (4) ───────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_alerts")
def get_alerts(alertId: Optional[str] = None):
    """List alerts or get by ID via parameter."""
    return _get("/api/alerts", {"alertId": alertId})


@mcp.tool(name=f"{PREFIX}-get_alert")
def get_alert(alertId: str):
    """Get an alert by ID."""
    return _get(f"/api/alerts/{urllib.parse.quote(alertId)}")


@mcp.tool(name=f"{PREFIX}-get_alert_protocol_options")
def get_alert_protocol_options():
    """Get alert protocol options."""
    return _get("/api/alerts/options")


@mcp.tool(name=f"{PREFIX}-get_alert_status_list")
def get_alert_status_list():
    """Get alert statuses."""
    return _get("/api/alerts/statuses")


# ── Code Templates (4) ───────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_code_templates")
def get_code_templates(codeTemplateId: Optional[str] = None):
    """List code templates or filter by ID."""
    return _get("/api/codeTemplates", {"codeTemplateId": codeTemplateId})


@mcp.tool(name=f"{PREFIX}-get_code_template")
def get_code_template(codeTemplateId: str):
    """Get a code template by ID."""
    return _get(f"/api/codeTemplates/{urllib.parse.quote(codeTemplateId)}")


@mcp.tool(name=f"{PREFIX}-get_code_template_libraries")
def get_code_template_libraries(
    libraryId: Optional[str] = None, includeCodeTemplates: Optional[bool] = None
):
    """List code template libraries."""
    return _get(
        "/api/codeTemplateLibraries",
        {"libraryId": libraryId, "includeCodeTemplates": includeCodeTemplates},
    )


@mcp.tool(name=f"{PREFIX}-get_code_template_library")
def get_code_template_library(
    libraryId: str, includeCodeTemplates: Optional[bool] = None
):
    """Get a code template library by ID."""
    return _get(
        f"/api/codeTemplateLibraries/{urllib.parse.quote(libraryId)}",
        {"includeCodeTemplates": includeCodeTemplates},
    )


# ── Server Configuration (24) ────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_server_version")
def get_server_version():
    """Get server version (text)."""
    return _get("/api/server/version", raw=True)


@mcp.tool(name=f"{PREFIX}-get_server_id")
def get_server_id():
    """Get server ID (text)."""
    return _get("/api/server/id", raw=True)


@mcp.tool(name=f"{PREFIX}-get_server_status")
def get_server_status():
    """Get server status."""
    return _get("/api/server/status")


@mcp.tool(name=f"{PREFIX}-get_server_about")
def get_server_about():
    """Get server about info."""
    return _get("/api/server/about")




@mcp.tool(name=f"{PREFIX}-get_server_build_date")
def get_server_build_date():
    """Get server build date (text)."""
    return _get("/api/server/buildDate", raw=True)


@mcp.tool(name=f"{PREFIX}-get_server_time")
def get_server_time():
    """Get server time."""
    return _get("/api/server/time")


@mcp.tool(name=f"{PREFIX}-get_server_timezone")
def get_server_timezone():
    """Get server timezone (text)."""
    return _get("/api/server/timezone", raw=True)


@mcp.tool(name=f"{PREFIX}-get_license_info")
def get_license_info():
    """Get license info."""
    return _get("/api/server/licenseInfo")


@mcp.tool(name=f"{PREFIX}-get_server_settings")
def get_server_settings():
    """Get server settings."""
    return _get("/api/server/settings")


@mcp.tool(name=f"{PREFIX}-get_update_settings")
def get_update_settings():
    """Get update settings."""
    return _get("/api/server/updateSettings")


@mcp.tool(name=f"{PREFIX}-get_configuration_map")
def get_configuration_map():
    """Get configuration map."""
    return _get("/api/server/configurationMap")


@mcp.tool(name=f"{PREFIX}-get_channel_metadata")
def get_channel_metadata():
    """Get channel metadata."""
    return _get("/api/server/channelMetadata")


@mcp.tool(name=f"{PREFIX}-get_channel_tags")
def get_channel_tags():
    """Get channel tags."""
    return _get("/api/server/channelTags")


@mcp.tool(name=f"{PREFIX}-get_global_scripts")
def get_global_scripts():
    """Get global scripts."""
    return _get("/api/server/globalScripts")


@mcp.tool(name=f"{PREFIX}-get_channel_dependencies")
def get_channel_dependencies():
    """Get channel dependencies."""
    return _get("/api/server/channelDependencies")








@mcp.tool(name=f"{PREFIX}-get_database_drivers")
def get_database_drivers():
    """Get database drivers."""
    return _get("/api/server/databaseDrivers")


@mcp.tool(name=f"{PREFIX}-get_server_configuration")
def get_server_configuration(
    initialState: Optional[str] = None,
    pollingOnly: Optional[bool] = None,
    disableAlerts: Optional[bool] = None,
):
    """Get full server configuration with optional flags."""
    return _get(
        "/api/server/configuration",
        {
            "initialState": initialState,
            "pollingOnly": pollingOnly,
            "disableAlerts": disableAlerts,
        },
    )


@mcp.tool(name=f"{PREFIX}-get_password_requirements")
def get_password_requirements():
    """Get password requirements."""
    return _get("/api/server/passwordRequirements")


@mcp.tool(name=f"{PREFIX}-get_resources")
def get_resources():
    """Get server resources."""
    return _get("/api/server/resources")




# ── Events (4) ───────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_events")
def get_events(
    maxEventId: Optional[int] = None,
    minEventId: Optional[int] = None,
    level: Optional[str] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    name: Optional[str] = None,
    outcome: Optional[str] = None,
    userId: Optional[str] = None,
    ipAddress: Optional[str] = None,
    serverId: Optional[str] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
):
    """List events (curated/common filters supported)."""
    return _get(
        "/api/events",
        {
            "maxEventId": maxEventId,
            "minEventId": minEventId,
            "level": level,
            "startDate": startDate,
            "endDate": endDate,
            "name": name,
            "outcome": outcome,
            "userId": userId,
            "ipAddress": ipAddress,
            "serverId": serverId,
            "offset": offset,
            "limit": limit,
        },
    )


@mcp.tool(name=f"{PREFIX}-get_event")
def get_event(eventId: str):
    """Get event by ID."""
    return _get(f"/api/events/{urllib.parse.quote(eventId)}")


@mcp.tool(name=f"{PREFIX}-get_max_event_id")
def get_max_event_id():
    """Get max event ID."""
    return _get("/api/events/maxEventId")


@mcp.tool(name=f"{PREFIX}-get_event_count")
def get_event_count(
    maxEventId: Optional[int] = None,
    minEventId: Optional[int] = None,
    level: Optional[str] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    name: Optional[str] = None,
    outcome: Optional[str] = None,
    userId: Optional[str] = None,
    ipAddress: Optional[str] = None,
    serverId: Optional[str] = None,
):
    """Get event count (uses same filters as events)."""
    return _get(
        "/api/events/count",
        {
            "maxEventId": maxEventId,
            "minEventId": minEventId,
            "level": level,
            "startDate": startDate,
            "endDate": endDate,
            "name": name,
            "outcome": outcome,
            "userId": userId,
            "ipAddress": ipAddress,
            "serverId": serverId,
        },
    )


# ── Messages (6) ─────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_messages")
def get_messages(
    channelId: str,
    minMessageId: Optional[int] = None,
    maxMessageId: Optional[int] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    textSearch: Optional[str] = None,
    status: Optional[str] = None,
    includeContent: Optional[bool] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
):
    """List messages for a channel (curated subset of filters)."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}/messages",
        {
            "minMessageId": minMessageId,
            "maxMessageId": maxMessageId,
            "startDate": startDate,
            "endDate": endDate,
            "textSearch": textSearch,
            "status": status,
            "includeContent": includeContent,
            "offset": offset,
            "limit": limit,
        },
    )


@mcp.tool(name=f"{PREFIX}-get_message_content")
def get_message_content(channelId: str, messageId: str, metaDataId: Optional[int] = None):
    """Get message content by channel/message ID, optionally by metadata ID."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}/messages/{urllib.parse.quote(messageId)}",
        {"metaDataId": metaDataId},
    )


@mcp.tool(name=f"{PREFIX}-get_message_count")
def get_message_count(
    channelId: str,
    minMessageId: Optional[int] = None,
    maxMessageId: Optional[int] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    textSearch: Optional[str] = None,
    status: Optional[str] = None,
    includeContent: Optional[bool] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
):
    """Get message count for a channel (same filter subset as messages)."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}/messages/count",
        {
            "minMessageId": minMessageId,
            "maxMessageId": maxMessageId,
            "startDate": startDate,
            "endDate": endDate,
            "textSearch": textSearch,
            "status": status,
            "includeContent": includeContent,
            "offset": offset,
            "limit": limit,
        },
    )


@mcp.tool(name=f"{PREFIX}-get_max_message_id")
def get_max_message_id(channelId: str):
    """Get maximum message ID for a channel."""
    return _get(f"/api/channels/{urllib.parse.quote(channelId)}/messages/maxMessageId")


@mcp.tool(name=f"{PREFIX}-get_message_attachments")
def get_message_attachments(
    channelId: str, messageId: str, includeContent: Optional[bool] = None
):
    """List message attachments for a message."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}/messages/{urllib.parse.quote(messageId)}/attachments",
        {"includeContent": includeContent},
    )


@mcp.tool(name=f"{PREFIX}-get_message_attachment")
def get_message_attachment(channelId: str, messageId: str, attachmentId: str):
    """Get a specific message attachment."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}/messages/{urllib.parse.quote(messageId)}/attachments/{urllib.parse.quote(attachmentId)}"
    )


# ── Database Tasks (2) ───────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_database_tasks")
def get_database_tasks():
    """List database tasks."""
    return _get("/api/databaseTasks")


@mcp.tool(name=f"{PREFIX}-get_database_task")
def get_database_task(databaseTaskId: str):
    """Get a database task by ID."""
    return _get(f"/api/databaseTasks/{urllib.parse.quote(databaseTaskId)}")


# ── Extensions (5) ───────────────────────────────────────────────────────────


@mcp.tool(name=f"{PREFIX}-get_connector_metadata")
def get_connector_metadata():
    """List connector metadata."""
    return _get("/api/extensions/connectors")








# ── Extension Services — Dashboard Status (5) ────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_dashboard_channel_states")
def get_dashboard_channel_states():
    """Get dashboard channel states."""
    return _get("/api/extensions/dashboardstatus/channelStates")


@mcp.tool(name=f"{PREFIX}-get_dashboard_channel_state")
def get_dashboard_channel_state(channelId: str):
    """Get dashboard channel state by channel ID."""
    return _get(f"/api/extensions/dashboardstatus/channelStates/{urllib.parse.quote(channelId)}")


@mcp.tool(name=f"{PREFIX}-get_dashboard_connector_states")
def get_dashboard_connector_states(serverId: Optional[str] = None):
    """Get dashboard connector states (optionally filtered by serverId)."""
    return _get("/api/extensions/dashboardstatus/connectorStates", {"serverId": serverId})


@mcp.tool(name=f"{PREFIX}-get_all_channel_logs")
def get_all_channel_logs(
    serverId: Optional[str] = None, fetchSize: Optional[int] = None, lastLogId: Optional[int] = None
):
    """Get all channel connection logs."""
    return _get(
        "/api/extensions/dashboardstatus/connectionLogs",
        {"serverId": serverId, "fetchSize": fetchSize, "lastLogId": lastLogId},
    )


@mcp.tool(name=f"{PREFIX}-get_channel_log")
def get_channel_log(
    channelId: str, serverId: Optional[str] = None, fetchSize: Optional[int] = None, lastLogId: Optional[int] = None
):
    """Get connection logs for a specific channel."""
    return _get(
        f"/api/extensions/dashboardstatus/connectionLogs/{urllib.parse.quote(channelId)}",
        {"serverId": serverId, "fetchSize": fetchSize, "lastLogId": lastLogId},
    )


# ── Extension Services — Data Pruner (1) ─────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_data_pruner_status")
def get_data_pruner_status():
    """Get data pruner status."""
    return _get("/api/extensions/datapruner/status")


# ── Extension Services — Other (4) ──────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_directory_resource_libraries")
def get_directory_resource_libraries(resourceId: str):
    """Get directory resource libraries for a resource ID."""
    return _get(
        f"/api/extensions/directoryresource/resources/{urllib.parse.quote(resourceId)}/libraries"
    )


@mcp.tool(name=f"{PREFIX}-get_global_map")
def get_global_map():
    """Get the global map."""
    return _get("/api/extensions/globalmapviewer/maps/global")


@mcp.tool(name=f"{PREFIX}-get_global_channel_map")
def get_global_channel_map(channelId: str):
    """Get the global channel map for a channel."""
    return _get(f"/api/extensions/globalmapviewer/maps/{urllib.parse.quote(channelId)}")


@mcp.tool(name=f"{PREFIX}-get_all_maps")
def get_all_maps(channelId: Optional[str] = None, includeGlobalMap: Optional[bool] = None):
    """Get all maps, optionally filtered."""
    return _get(
        "/api/extensions/globalmapviewer/maps/all",
        {"channelId": channelId, "includeGlobalMap": includeGlobalMap},
    )


# ── Extension Services — Server Log (1) ─────────────────────────────────────-
@mcp.tool(name=f"{PREFIX}-get_server_logs")
def get_server_logs(fetchSize: Optional[int] = None, lastLogId: Optional[int] = None):
    """Get server logs."""
    return _get("/api/extensions/serverlog", {"fetchSize": fetchSize, "lastLogId": lastLogId})


# ── System (2) ───────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_system_stats")
def get_system_stats():
    """Get system stats."""
    return _get("/api/system/stats")


@mcp.tool(name=f"{PREFIX}-get_system_info")
def get_system_info():
    """Get system info."""
    return _get("/api/system/info")


# ── Users (6) ────────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_all_users")
def get_all_users():
    """List all users."""
    return _get("/api/users")


@mcp.tool(name=f"{PREFIX}-get_current_user")
def get_current_user():
    """Get the current user."""
    return _get("/api/users/current")


@mcp.tool(name=f"{PREFIX}-get_user")
def get_user(userIdOrName: str):
    """Get user by ID or name."""
    return _get(f"/api/users/{urllib.parse.quote(userIdOrName)}")


@mcp.tool(name=f"{PREFIX}-is_user_logged_in")
def is_user_logged_in(userId: str):
    """Check if a user is logged in."""
    return _get(f"/api/users/{urllib.parse.quote(userId)}/loggedIn")


@mcp.tool(name=f"{PREFIX}-get_user_preferences")
def get_user_preferences(userId: str, name: Optional[str] = None):
    """Get user preferences, optionally filtered by name."""
    return _get(f"/api/users/{urllib.parse.quote(userId)}/preferences", {"name": name})


@mcp.tool(name=f"{PREFIX}-get_user_preference")
def get_user_preference(userId: str, name: str):
    """Get a single user preference by name."""
    return _get(
        f"/api/users/{urllib.parse.quote(userId)}/preferences/{urllib.parse.quote(name)}"
    )


# ── JMS Connector Templates (2) ─────────────────────────────────────────────




# ── Entry point (stdio) ─────────────────────────────────────────────────────-
if __name__ == "__main__":
    mcp.run()
