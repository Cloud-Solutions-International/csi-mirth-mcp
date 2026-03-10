"""
Mirth Connect Read-Only MCP Server — FastMCP over stdio.
Auth: cookie-based session (POST /api/users/_login with username/password). Read-only GET tools.

Setup:
- Install: pip install mcp
"""

import os
import json
import ssl
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
import concurrent.futures
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
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        },
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

# ── Channels ─────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_channel")
def get_channel(channelId: str, includeCodeTemplateLibraries: Optional[bool] = None):
    """Get a specific channel by ID."""
    return _get(
        f"/api/channels/{urllib.parse.quote(channelId)}",
        {"includeCodeTemplateLibraries": includeCodeTemplateLibraries},
    )


@mcp.tool(name=f"{PREFIX}-get_channel_groups_channel_names_to_ids")
def get_channel_groups_channel_names_to_ids(search: Optional[str] = None):
    """
    Combine channel IDs+names with channel groups, returning:
    { "<channelGroupName>": { "<channelName>": "<channelId>", ... }, ... }
    Channels not present in any group will be placed under "Default Group".
    If 'search' is provided (case-insensitive substring), results are filtered:
      - For non-default groups: include the full group if the group name or any channel (name or ID) matches.
      - For "Default Group": include only the matching channel(s) under that group.
    """
    # Fetch channel IDs and names + channel groups in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        names_future = executor.submit(_get, "/api/channels/idsAndNames")
        groups_future = executor.submit(_get, "/api/channelgroups")

        # Wait for both requests to complete
        names_data = names_future.result()
        groups_data = groups_future.result()

    # Build a mapping of channelId -> channelName
    name_by_id: dict[str, str] = {}
    try:
        entries = names_data.get("map", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        if entries:
            for ent in entries:
                pair = ent.get("string")
                if isinstance(pair, list) and len(pair) >= 2:
                    cid = str(pair[0])
                    cname = str(pair[1])
                    name_by_id[cid] = cname
        else:
            channels_list = names_data.get("list", {}).get("channel", [])
            if isinstance(channels_list, dict):
                channels_list = [channels_list]
            for ch in channels_list:
                if isinstance(ch, dict) and "id" in ch and "name" in ch:
                    name_by_id[str(ch["id"])] = str(ch["name"])
    except Exception:
        name_by_id = {}

    # Build the final mapping: groupName -> { channelName: channelId }
    result: dict[str, dict[str, str]] = {}
    try:
        groups = groups_data.get("list", {}).get("channelGroup", [])
        if isinstance(groups, dict):
            groups = [groups]
        grouped_ids: set[str] = set()
        for g in groups:
            if not isinstance(g, dict):
                continue
            group_name = g.get("name")
            if group_name is None:
                continue
            channels = g.get("channels", {}).get("channel", [])
            if isinstance(channels, dict):
                channels = [channels]
            group_map: dict[str, str] = {}
            for ch in channels:
                if isinstance(ch, dict) and "id" in ch:
                    cid = str(ch["id"])
                    cname = name_by_id.get(cid, cid)
                    group_map[cname] = cid
                    grouped_ids.add(cid)
            result[str(group_name)] = group_map

        # Add channels not found in any group under "Default Group"
        all_ids = set(name_by_id.keys())
        ungrouped_ids = all_ids - grouped_ids
        if ungrouped_ids:
            default_map: dict[str, str] = {}
            for cid in sorted(ungrouped_ids):
                cname = name_by_id.get(cid, cid)
                default_map[cname] = cid
            result["Default Group"] = default_map
    except Exception:
        result = {}

    # Optional filtering by search keyword
    if search is not None:
        s = search.strip().lower()
        if s:
            filtered: dict[str, dict[str, str]] = {}
            for group_name, group_map in result.items():
                if group_name == "Default Group":
                    # Only include matching channels from Default Group
                    matched = {
                        cname: cid
                        for cname, cid in group_map.items()
                        if s in cname.lower() or s in str(cid).lower()
                    }
                    if matched:
                        filtered["Default Group"] = matched
                else:
                    # Include full group if group name or any channel matches
                    group_matches = (
                        s in group_name.lower()
                        or any(s in cname.lower() or s in str(cid).lower() for cname, cid in group_map.items())
                    )
                    if group_matches:
                        filtered[group_name] = group_map
            return filtered

    return result


# ── Channel Statistics ───────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_channel_statistics")
def get_channel_statistics(
    channelId: Optional[str] = None,
    includeUndeployed: Optional[bool] = None,
    includeMetadataId: Optional[str] = None,
    excludeMetadataId: Optional[str] = None,
    aggregateStats: Optional[bool] = None,
):
    """
    Get channel statistics as a mapping from channelId to counters.
    Returns: { "<channelId>": {"received": int, "sent": int, "error": int, "filtered": int, "queued": int}, ... }
    """
    data = _get(
        "/api/channels/statistics",
        {
            "channelId": channelId,
            "includeUndeployed": includeUndeployed,
            "includeMetadataId": includeMetadataId,
            "excludeMetadataId": excludeMetadataId,
            "aggregateStats": aggregateStats,
        },
    )
    result: dict[str, dict[str, int]] = {}

    def _to_int(x):
        try:
            return int(x)
        except Exception:
            try:
                return int(float(x))
            except Exception:
                return 0

    try:
        stats = data.get("list", {}).get("channelStatistics", [])
        if isinstance(stats, dict):
            stats = [stats]
        for s in stats:
            if not isinstance(s, dict):
                continue
            cid = s.get("channelId")
            if cid is None:
                continue
            result[str(cid)] = {
                "received": _to_int(s.get("received", 0)),
                "sent": _to_int(s.get("sent", 0)),
                "error": _to_int(s.get("error", 0)),
                "filtered": _to_int(s.get("filtered", 0)),
                "queued": _to_int(s.get("queued", 0)),
            }
    except Exception:
        result = {}
    return result


# ── Code Templates ───────────────────────────────────────────────────────
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


# ── Server Configuration ────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_global_scripts")
def get_global_scripts():
    """
    Get global scripts as a mapping of name -> script content.
    """
    data = _get("/api/server/globalScripts")
    result: dict[str, str] = {}
    try:
        entries = data.get("map", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        for ent in entries:
            pair = ent.get("string")
            if isinstance(pair, list) and len(pair) >= 2:
                key = str(pair[0])
                value = str(pair[1])
                result[key] = value
    except Exception:
        result = {}
    return result


@mcp.tool(name=f"{PREFIX}-get_channel_dependencies")
def get_channel_dependencies():
    """Get channel dependencies."""
    return _get("/api/server/channelDependencies")


# ── Messages ─────────────────────────────────────────────────────────────
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
    """
    Get maximum message ID for a channel as a raw integer.
    """
    data = _get(f"/api/channels/{urllib.parse.quote(channelId)}/messages/maxMessageId")
    def _to_int(x):
        try:
            return int(x)
        except Exception:
            try:
                return int(float(x))
            except Exception:
                return 0
    value = data.get("long") if isinstance(data, dict) else data
    return _to_int(value)


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


# ── System ───────────────────────────────────────────────────────────────
@mcp.tool(name=f"{PREFIX}-get_system_stats")
def get_system_stats():
    """Get system stats like server time, timezone, memory usage, etc."""
    return _get("/api/system/stats")


# ── Entry point (stdio) ─────────────────────────────────────────────────────-
if __name__ == "__main__":
    import logging

    # Globally disable all logging at the core level to prevent FastMCP's 'rich'
    # handler from writing plain-text log lines to stdout and corrupting the JSON stream.
    logging.disable(logging.CRITICAL)

    mcp.run()
