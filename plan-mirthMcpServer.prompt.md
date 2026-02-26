# Plan: Mirth Connect Read-Only MCP Server

Build a new Python FastMCP server (`mirth_server.py`) mirroring the architecture of the existing [server.py](/home/bilal/repo/csi-mirth-mcp/server.py). It will expose ~69 read-only GET endpoints from the Mirth Connect API as MCP tools, authenticate via cookie-based login at startup, and support multi-instance deployment via `ENV_PREFIX`-based dynamic tool naming. Only stdlib + `mcp` dependencies will be used.

## Steps

### 1. Create the project scaffold and config block

Create a new file `mirth_server.py`. Read `MIRTH_URL`, `MIRTH_USERNAME`, `MIRTH_PASSWORD`, and `ENV_PREFIX` from environment variables. Set up `ssl`, `http.cookiejar`, and `urllib` opener exactly as done in [server.py](/home/bilal/repo/csi-mirth-mcp/server.py) lines 22–32. Instantiate `FastMCP("mirth")`.

### 2. Implement `_login()` and `_get()` helpers

`_login()` must POST to `/api/users/_login` with `application/x-www-form-urlencoded` body (`username=...&password=...`). The Mirth API uses cookie-based auth (JSESSIONID), so the cookie jar from the opener will retain the session. Unlike the DPA example which has CSRF, Mirth's login is simpler — just POST credentials and store the cookie. `_get()` should be a generic helper that GETs `MIRTH_URL + path`, passes `Accept: application/json`, handles query params, and auto-re-logins on 401/redirect. Call `_login()` at module level on startup (line 102 pattern in the example).

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
