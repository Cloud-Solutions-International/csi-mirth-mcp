# Plan: Mirth Connect Read-Only MCP Server

Build a new Python FastMCP server (`mirth_server.py`) mirroring the architecture of the existing [server.py](/home/bilal/repo/csi-mirth-mcp/server.py). It will expose ~69 read-only GET endpoints from the Mirth Connect API as MCP tools, authenticate via cookie-based login at startup, and support multi-instance deployment via `ENV_PREFIX`-based dynamic tool naming. Only stdlib + `mcp` dependencies will be used.

Transport: The MCP server communicates over stdio (MCP over stdio) only; it does not open any network ports.

## Steps

### 1. Create the project scaffold and config block

Create a new file `mirth_server.py`. Read `MIRTH_URL`, `MIRTH_USERNAME`, `MIRTH_PASSWORD`, and `ENV_PREFIX` from environment variables. Set up `ssl`, `http.cookiejar`, and `urllib` opener exactly as done in [server.py](/home/bilal/repo/csi-mirth-mcp/server.py) lines 22–32. Instantiate `FastMCP("mirth")`.

### 2. Implement `_login()` and `_get()` helpers

`_login()` must POST to `/api/users/_login` with `application/x-www-form-urlencoded` body (`username=...&password=...`). The Mirth API uses cookie-based auth (JSESSIONID), so the cookie jar from the opener will retain the session. Unlike the DPA example which has CSRF, Mirth's login is simpler — just POST credentials and store the cookie. `_get()` should be a generic helper that GETs `MIRTH_URL + path`, passes `Accept: application/json`, handles query params, and auto-re-logins on 401/redirect. Call `_login()` at module level on startup (line 102 pattern in the example). In `_get()`, ensure boolean query parameter values are converted to lowercase `'true'/'false'` strings before URL encoding.

### 3. Register all read-only GET tools with `ENV_PREFIX` prefixing

For every GET endpoint identified below, register it as `@mcp.tool(name=f"{PREFIX}tool_name")`. Each tool function wraps `_get(path, params)`. Group the ~69 tools into logical sections with clear docstrings. The full list of tools to register is:

#### Channels (5 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_channels` | GET | `/api/channels` | `channelId`, `pollingOnly`, `includeCodeTemplateLibraries` |
| `get_channel` | GET | `/api/channels/{channelId}` | `includeCodeTemplateLibraries` |
| `get_channel_ids_and_names` | GET | `/api/channels/idsAndNames` | — |
| `get_connector_names` | GET | `/api/channels/{channelId}/connectorNames` | — |
| `get_metadata_columns` | GET | `/api/channels/{channelId}/metaDataColumns` | — |

#### Channel Groups (1 tool)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_channel_groups` | GET | `/api/channelgroups` | `channelGroupId` |

#### Channel Statistics (2 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_channel_statistics` | GET | `/api/channels/statistics` | `channelId`, `includeUndeployed`, `includeMetadataId`, `excludeMetadataId`, `aggregateStats` |
| `get_channel_statistics_by_id` | GET | `/api/channels/{channelId}/statistics` | — |

#### Channel Status (3 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_channel_status_list` | GET | `/api/channels/statuses` | `channelId`, `filter`, `includeUndeployed` |
| `get_channel_status` | GET | `/api/channels/{channelId}/status` | — |
| `get_dashboard_channel_info` | GET | `/api/channels/statuses/initial` | `fetchSize`, `filter` |

#### Alerts (4 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_alerts` | GET | `/api/alerts` | `alertId` |
| `get_alert` | GET | `/api/alerts/{alertId}` | — |
| `get_alert_protocol_options` | GET | `/api/alerts/options` | — |
| `get_alert_status_list` | GET | `/api/alerts/statuses` | — |

#### Code Templates (4 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_code_templates` | GET | `/api/codeTemplates` | `codeTemplateId` |
| `get_code_template` | GET | `/api/codeTemplates/{codeTemplateId}` | — |
| `get_code_template_libraries` | GET | `/api/codeTemplateLibraries` | `libraryId`, `includeCodeTemplates` |
| `get_code_template_library` | GET | `/api/codeTemplateLibraries/{libraryId}` | `includeCodeTemplates` |

#### Server Configuration (24 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_server_version` | GET | `/api/server/version` | — |
| `get_server_id` | GET | `/api/server/id` | — |
| `get_server_status` | GET | `/api/server/status` | — |
| `get_server_about` | GET | `/api/server/about` | — |
| `get_server_jvm` | GET | `/api/server/jvm` | — |
| `get_server_build_date` | GET | `/api/server/buildDate` | — |
| `get_server_time` | GET | `/api/server/time` | — |
| `get_server_timezone` | GET | `/api/server/timezone` | — |
| `get_license_info` | GET | `/api/server/licenseInfo` | — |
| `get_server_settings` | GET | `/api/server/settings` | — |
| `get_update_settings` | GET | `/api/server/updateSettings` | — |
| `get_configuration_map` | GET | `/api/server/configurationMap` | — |
| `get_channel_metadata` | GET | `/api/server/channelMetadata` | — |
| `get_channel_tags` | GET | `/api/server/channelTags` | — |
| `get_global_scripts` | GET | `/api/server/globalScripts` | — |
| `get_channel_dependencies` | GET | `/api/server/channelDependencies` | — |
| `get_rhino_language_version` | GET | `/api/server/rhinoLanguageVersion` | — |
| `get_charsets` | GET | `/api/server/charsets` | — |
| `get_encryption_settings` | GET | `/api/server/encryption` | — |
| `get_database_drivers` | GET | `/api/server/databaseDrivers` | — |
| `get_server_configuration` | GET | `/api/server/configuration` | `initialState`, `pollingOnly`, `disableAlerts` |
| `get_password_requirements` | GET | `/api/server/passwordRequirements` | — |
| `get_resources` | GET | `/api/server/resources` | — |
| `get_protocols_and_cipher_suites` | GET | `/api/server/protocolsAndCipherSuites` | — |

#### Events (4 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_events` | GET | `/api/events` | `maxEventId`, `minEventId`, `level`, `startDate`, `endDate`, `name`, `outcome`, `userId`, `ipAddress`, `serverId`, `offset`, `limit` |
| `get_event` | GET | `/api/events/{eventId}` | — |
| `get_max_event_id` | GET | `/api/events/maxEventId` | — |
| `get_event_count` | GET | `/api/events/count` | same filter params as `get_events` |

#### Messages (6 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_messages` | GET | `/api/channels/{channelId}/messages` | `minMessageId`, `maxMessageId`, `startDate`, `endDate`, `textSearch`, `status`, `includeContent`, `offset`, `limit` (curated subset — see note below) |
| `get_message_content` | GET | `/api/channels/{channelId}/messages/{messageId}` | `metaDataId` |
| `get_message_count` | GET | `/api/channels/{channelId}/messages/count` | same filter params as `get_messages` |
| `get_max_message_id` | GET | `/api/channels/{channelId}/messages/maxMessageId` | — |
| `get_message_attachments` | GET | `/api/channels/{channelId}/messages/{messageId}/attachments` | `includeContent` |
| `get_message_attachment` | GET | `/api/channels/{channelId}/messages/{messageId}/attachments/{attachmentId}` | — |

#### Database Tasks (2 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_database_tasks` | GET | `/api/databaseTasks` | — |
| `get_database_task` | GET | `/api/databaseTasks/{databaseTaskId}` | — |

#### Extensions (5 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_extension_metadata` | GET | `/api/extensions/{extensionName}` | — |
| `get_connector_metadata` | GET | `/api/extensions/connectors` | — |
| `get_plugin_metadata` | GET | `/api/extensions/plugins` | — |
| `get_plugin_properties` | GET | `/api/extensions/{extensionName}/properties` | `propertyKeys` |
| `is_extension_enabled` | GET | `/api/extensions/{extensionName}/enabled` | — |

#### Extension Services — Dashboard Status (5 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_dashboard_channel_states` | GET | `/api/extensions/dashboardstatus/channelStates` | — |
| `get_dashboard_channel_state` | GET | `/api/extensions/dashboardstatus/channelStates/{channelId}` | — |
| `get_dashboard_connector_states` | GET | `/api/extensions/dashboardstatus/connectorStates` | `serverId` |
| `get_all_channel_logs` | GET | `/api/extensions/dashboardstatus/connectionLogs` | `serverId`, `fetchSize`, `lastLogId` |
| `get_channel_log` | GET | `/api/extensions/dashboardstatus/connectionLogs/{channelId}` | `serverId`, `fetchSize`, `lastLogId` |

#### Extension Services — Data Pruner (1 tool)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_data_pruner_status` | GET | `/api/extensions/datapruner/status` | — |

#### Extension Services — Other (4 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_directory_resource_libraries` | GET | `/api/extensions/directoryresource/resources/{resourceId}/libraries` | — |
| `get_global_map` | GET | `/api/extensions/globalmapviewer/maps/global` | — |
| `get_global_channel_map` | GET | `/api/extensions/globalmapviewer/maps/{channelId}` | — |
| `get_all_maps` | GET | `/api/extensions/globalmapviewer/maps/all` | `channelId`, `includeGlobalMap` |

#### Extension Services — Server Log (1 tool)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_server_logs` | GET | `/api/extensions/serverlog` | `fetchSize`, `lastLogId` |

#### System (2 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_system_stats` | GET | `/api/system/stats` | — |
| `get_system_info` | GET | `/api/system/info` | — |

#### Users (6 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_all_users` | GET | `/api/users` | — |
| `get_current_user` | GET | `/api/users/current` | — |
| `get_user` | GET | `/api/users/{userIdOrName}` | — |
| `is_user_logged_in` | GET | `/api/users/{userId}/loggedIn` | — |
| `get_user_preferences` | GET | `/api/users/{userId}/preferences` | `name` |
| `get_user_preference` | GET | `/api/users/{userId}/preferences/{name}` | — |

#### JMS Connector Templates (2 tools)

| Tool Name | HTTP | Path | Parameters |
|-----------|------|------|------------|
| `get_jms_templates` | GET | `/api/connectors/jms/templates` | — |
| `get_jms_template` | GET | `/api/connectors/jms/templates/{templateName}` | — |

**Total: ~69 tools.**

### 4. Handle `ENV_PREFIX` for dynamic tool naming

At the top of `mirth_server.py`, read `PREFIX = os.environ.get("ENV_PREFIX", "")`. For every `@mcp.tool()` decorator, use `name=f"{PREFIX}tool_name"`. This ensures when the client runs `dev_get_channels` vs `prod_get_channels`, tools don't collide.

Example:
```python
@mcp.tool(name=f"{PREFIX}get_channels")
```

### 5. Handle Mirth API response format

Unlike the DPA example which unwraps `body["data"]`, Mirth's API returns JSON directly (or XML — we request JSON via `Accept: application/json`). The `_get()` helper should simply parse and return the JSON body. For endpoints returning `text/plain` (e.g., `getVersion`, `getServerId`, `getBuildDate`, `getServerTimezone`, `getJVMName`), `_get()` should handle the response as a string rather than parsing JSON. Consider adding a `raw=True` flag or a separate `_get_text()` helper for these.

### 6. Add `__main__` block to run the server

At the bottom: `if __name__ == "__main__": mcp.run()`. This is identical to the example pattern.

## Further Considerations

1. **Message/Event tools have many optional params** — for tools like `get_messages` and `get_events` with 20+ optional query parameters, expose only the most commonly used params as tool arguments (e.g., `startDate`, `endDate`, `status`, `textSearch`, `offset`, `limit`) and omit rarely-used ones to keep the tool schema manageable. Alternatively, accept a `**kwargs` or a dict. **Recommendation:** Expose a curated subset (~8-10 most useful params) per tool.

2. **Auto-retry on session expiry** — Mirth sessions can expire. The `_get()` helper should catch 401 responses (Mirth returns HTTP 401 for expired sessions, unlike DPA's 302 redirect), re-call `_login()`, and retry the request once. Verify the exact HTTP status Mirth returns for expired sessions.

3. **SSL verification** — Like the DPA example, self-signed certs are common in Mirth environments. Keep `ssl.CERT_NONE` as the default, matching the existing pattern in `server.py`.

## Detailed To-Do (Phased)

Phase 0 — Readiness and environment
- Confirm MCP runs over stdio only; no network listener will be created.
- Ensure required environment variables are available: MIRTH_URL, MIRTH_USERNAME, MIRTH_PASSWORD, ENV_PREFIX (optional). NOTE: If the environment variables are not set, you may temporarily set dummy values for testing, however in actual use, the environment variables are guaranteed to be set by the MCP client.
- Verify mcp package is available; use only Python standard library modules otherwise. NOTE: When we say 'mcp' package we are referring to 'FastMCP', more specifically 'from mcp.server.fastmcp import FastMCP' from server.py, reference server.py again if you need a refresher.
- Validate Mirth base URL format (no trailing slash assumptions) and reachability.

Phase 1 — Project scaffold
- Create mirth_server.py and add module-level imports for stdlib networking, SSL, cookies, typing, and JSON handling.
- Read MIRTH_URL, MIRTH_USERNAME, MIRTH_PASSWORD, and ENV_PREFIX from environment variables.
- Build SSL context with certificate verification disabled by default (consistent with plan).
- Create a shared CookieJar and urllib opener using the SSL context and cookie processor.
- Instantiate FastMCP("mirth") for stdio-based MCP.

Phase 2 — Authentication helper
- Implement _login():
  - POST to /api/users/_login with application/x-www-form-urlencoded body: username, password.
  - Allow the cookie jar to capture JSESSIONID; do not implement CSRF handling.
  - Handle non-2xx responses by raising a clear RuntimeError with truncated response text.
  - Keep timeouts reasonable (e.g., ~10–15s).

Phase 3 — HTTP GET helper
- Implement _get(path, params=None, raw=False):
  - Construct URL as MIRTH_URL + path; URL-encode query parameters when provided.
  - Convert Python boolean parameters to lowercase 'true'/'false' strings before encoding.
  - Add Accept: application/json header by default.
  - On success:
    - If raw=True, decode and return text content.
    - Otherwise, attempt to parse JSON and return parsed data; if parsing fails, return raw text.
  - On HTTP 401, call _login() once and retry the request; return the retried result.
  - On other HTTP errors, raise a RuntimeError with code and a truncated response body.
  - Ensure consistent timeouts and minimal redirects (default opener behavior is fine for GETs).

Phase 4 — Tool registration scaffolding
- Read PREFIX = os.environ.get("ENV_PREFIX", "").
- For every MCP tool decorator, set name=f"{PREFIX}tool_name".
- Use clear docstrings per tool describing purpose, parameters, and Mirth path.
- Keep function argument names aligned with documented query parameter names (camelCase as needed) and use Optional defaults for optional parameters.
- For endpoints that return text/plain, call _get with raw=True (as specified in the plan).

Phase 5 — Implement tools by category
- Channels:
  - get_channels(params: channelId=None, pollingOnly=None, includeCodeTemplateLibraries=None) -> wrap GET /api/channels.
  - get_channel(channelId, includeCodeTemplateLibraries=None) -> GET /api/channels/{channelId}.
  - get_channel_ids_and_names() -> GET /api/channels/idsAndNames.
  - get_connector_names(channelId) -> GET /api/channels/{channelId}/connectorNames.
  - get_metadata_columns(channelId) -> GET /api/channels/{channelId}/metaDataColumns.
- Channel Groups:
  - get_channel_groups(channelGroupId=None) -> GET /api/channelgroups.
- Channel Statistics:
  - get_channel_statistics(channelId=None, includeUndeployed=None, includeMetadataId=None, excludeMetadataId=None, aggregateStats=None) -> GET /api/channels/statistics.
  - get_channel_statistics_by_id(channelId) -> GET /api/channels/{channelId}/statistics.
- Channel Status:
  - get_channel_status_list(channelId=None, filter=None, includeUndeployed=None) -> GET /api/channels/statuses.
  - get_channel_status(channelId) -> GET /api/channels/{channelId}/status.
  - get_dashboard_channel_info(fetchSize=None, filter=None) -> GET /api/channels/statuses/initial.
- Alerts:
  - get_alerts(alertId=None) -> GET /api/alerts.
  - get_alert(alertId) -> GET /api/alerts/{alertId}.
  - get_alert_protocol_options() -> GET /api/alerts/options.
  - get_alert_status_list() -> GET /api/alerts/statuses.
- Code Templates:
  - get_code_templates(codeTemplateId=None) -> GET /api/codeTemplates.
  - get_code_template(codeTemplateId) -> GET /api/codeTemplates/{codeTemplateId}.
  - get_code_template_libraries(libraryId=None, includeCodeTemplates=None) -> GET /api/codeTemplateLibraries.
  - get_code_template_library(libraryId, includeCodeTemplates=None) -> GET /api/codeTemplateLibraries/{libraryId}.
- Server Configuration:
  - get_server_version(raw text) -> GET /api/server/version (raw=True).
  - get_server_id(raw text) -> GET /api/server/id (raw=True).
  - get_server_status() -> GET /api/server/status.
  - get_server_about() -> GET /api/server/about.
  - get_server_jvm() -> GET /api/server/jvm.
  - get_server_build_date(raw text) -> GET /api/server/buildDate (raw=True).
  - get_server_time() -> GET /api/server/time.
  - get_server_timezone(raw text) -> GET /api/server/timezone (raw=True).
  - get_license_info() -> GET /api/server/licenseInfo.
  - get_server_settings() -> GET /api/server/settings.
  - get_update_settings() -> GET /api/server/updateSettings.
  - get_configuration_map() -> GET /api/server/configurationMap.
  - get_channel_metadata() -> GET /api/server/channelMetadata.
  - get_channel_tags() -> GET /api/server/channelTags.
  - get_global_scripts() -> GET /api/server/globalScripts.
  - get_channel_dependencies() -> GET /api/server/channelDependencies.
  - get_rhino_language_version() -> GET /api/server/rhinoLanguageVersion.
  - get_charsets() -> GET /api/server/charsets.
  - get_encryption_settings() -> GET /api/server/encryption.
  - get_database_drivers() -> GET /api/server/databaseDrivers.
  - get_server_configuration(initialState=None, pollingOnly=None, disableAlerts=None) -> GET /api/server/configuration.
  - get_password_requirements() -> GET /api/server/passwordRequirements.
  - get_resources() -> GET /api/server/resources.
  - get_protocols_and_cipher_suites() -> GET /api/server/protocolsAndCipherSuites.
- Events:
  - get_events(maxEventId=None, minEventId=None, level=None, startDate=None, endDate=None, name=None, outcome=None, userId=None, ipAddress=None, serverId=None, offset=None, limit=None; curated to common params if desired) -> GET /api/events.
  - get_event(eventId) -> GET /api/events/{eventId}.
  - get_max_event_id() -> GET /api/events/maxEventId.
  - get_event_count(same filter subset as get_events) -> GET /api/events/count.
- Messages:
  - get_messages(channelId, minMessageId=None, maxMessageId=None, startDate=None, endDate=None, textSearch=None, status=None, includeContent=None, offset=None, limit=None) -> GET /api/channels/{channelId}/messages.
  - get_message_content(channelId, messageId, metaDataId=None) -> GET /api/channels/{channelId}/messages/{messageId}.
  - get_message_count(channelId, same subset as get_messages) -> GET /api/channels/{channelId}/messages/count.
  - get_max_message_id(channelId) -> GET /api/channels/{channelId}/messages/maxMessageId.
  - get_message_attachments(channelId, messageId, includeContent=None) -> GET /api/channels/{channelId}/messages/{messageId}/attachments.
  - get_message_attachment(channelId, messageId, attachmentId) -> GET /api/channels/{channelId}/messages/{messageId}/attachments/{attachmentId}.
- Database Tasks:
  - get_database_tasks() -> GET /api/databaseTasks.
  - get_database_task(databaseTaskId) -> GET /api/databaseTasks/{databaseTaskId}.
- Extensions:
  - get_extension_metadata(extensionName) -> GET /api/extensions/{extensionName}.
  - get_connector_metadata() -> GET /api/extensions/connectors.
  - get_plugin_metadata() -> GET /api/extensions/plugins.
  - get_plugin_properties(extensionName, propertyKeys=None) -> GET /api/extensions/{extensionName}/properties.
  - is_extension_enabled(extensionName) -> GET /api/extensions/{extensionName}/enabled.
- Extension Services — Dashboard Status:
  - get_dashboard_channel_states() -> GET /api/extensions/dashboardstatus/channelStates.
  - get_dashboard_channel_state(channelId) -> GET /api/extensions/dashboardstatus/channelStates/{channelId}.
  - get_dashboard_connector_states(serverId=None) -> GET /api/extensions/dashboardstatus/connectorStates.
  - get_all_channel_logs(serverId=None, fetchSize=None, lastLogId=None) -> GET /api/extensions/dashboardstatus/connectionLogs.
  - get_channel_log(channelId, serverId=None, fetchSize=None, lastLogId=None) -> GET /api/extensions/dashboardstatus/connectionLogs/{channelId}.
- Extension Services — Data Pruner:
  - get_data_pruner_status() -> GET /api/extensions/datapruner/status.
- Extension Services — Other:
  - get_directory_resource_libraries(resourceId) -> GET /api/extensions/directoryresource/resources/{resourceId}/libraries.
  - get_global_map() -> GET /api/extensions/globalmapviewer/maps/global.
  - get_global_channel_map(channelId) -> GET /api/extensions/globalmapviewer/maps/{channelId}.
  - get_all_maps(channelId=None, includeGlobalMap=None) -> GET /api/extensions/globalmapviewer/maps/all.
- Extension Services — Server Log:
  - get_server_logs(fetchSize=None, lastLogId=None) -> GET /api/extensions/serverlog.
- System:
  - get_system_stats() -> GET /api/system/stats.
  - get_system_info() -> GET /api/system/info.
- Users:
  - get_all_users() -> GET /api/users.
  - get_current_user() -> GET /api/users/current.
  - get_user(userIdOrName) -> GET /api/users/{userIdOrName}.
  - is_user_logged_in(userId) -> GET /api/users/{userId}/loggedIn.
  - get_user_preferences(userId, name=None) -> GET /api/users/{userId}/preferences.
  - get_user_preference(userId, name) -> GET /api/users/{userId}/preferences/{name}.
- JMS Connector Templates:
  - get_jms_templates() -> GET /api/connectors/jms/templates.
  - get_jms_template(templateName) -> GET /api/connectors/jms/templates/{templateName}.

Phase 6 — Startup and runtime
- Call _login() at import time to establish an authenticated session.
- Add __main__ guard to run the FastMCP server over stdio: mcp.run().

Phase 7 — Testing and validation
- Verify login succeeds with valid credentials and that the cookie jar is populated.
- Exercise representative tools from each category and confirm expected JSON or text responses.
- Confirm boolean query params are sent as lowercase strings.
- Simulate/observe an expired session and confirm a 401 triggers a single re-login and retry.
- Validate dynamic naming works by setting ENV_PREFIX and confirming tool discovery.

Phase 8 — Robustness and quality
- Add minimal logging (stdlib logging) for startup, login, retries, and HTTP errors.
- Ensure clear error messages bubble up via RuntimeError with truncated bodies.
- Validate timeouts are applied and no unexpected redirects break flows.

Phase 9 — Documentation
- Ensure each tool has a concise docstring: purpose, parameters, and endpoint path.
- Document environment variables, stdio transport requirement, and usage instructions in the module docstring or a README if needed.

Phase 10 — Final review
- Re-check adherence to constraints: read-only GETs only, stdlib + mcp, stdio-only transport, ENV_PREFIX tool naming.
- Spot-check endpoint parameter names for exact casing and mapping.
