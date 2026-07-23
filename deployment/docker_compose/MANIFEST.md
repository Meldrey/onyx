# Onyx — Deployment Manifest

## Image

`onyxdotapp/onyx-backend:latest` — currently running a **local build** from
`PRJ-onyx/onyx-src/backend/` (2026-07-11). Not a registry pull.

## Compose

- **Active dir:** `~/Projects/PRJ-onyx/onyx-src/deployment/docker_compose/`
- **Override:** `docker-compose.override.yml` (copied from `~/docker/onyx/`)
- **Env:** `~/docker/onyx/.env` (symlinked into compose dir)
- Code-interpreter and MinIO disabled via `profiles: ["disabled"]`

## Patches (12 files modified from upstream)

All patches live in the source tree at `PRJ-onyx/onyx-src/backend/`. They are
baked into the current image AND hot-mounted via the override. If you pull
upstream without the override active, all patches are lost.

| Container Path | Purpose |
|----------------|---------|
| `onyx/tools/tool_implementations/mcp/mcp_client.py` | MCP structuredContent + double-serialization fix |
| `onyx/tools/tool_implementations/mcp/mcp_tool.py` | MCP tool result fix |
| `onyx/chat/chat_utils.py` | MCP history replay fix + ChatFileType use_metadata_only |
| `onyx/server/features/mcp/models.py` | MCP auth template — literal headers without admin_credentials |
| `onyx/server/features/mcp/api.py` | MCP auth template fix |
| `onyx/chat/image_utils.py` | Image size guard — resize before base64 |
| `onyx/file_processing/file_types.py` | GIF support — image/gif in accepted types |
| `onyx/chat/llm_step.py` | GIF/image support + onyx-file:// URI injection |
| `onyx/tools/tool_constructor.py` | Per-agent + per-user MCP identity headers |
| `onyx/llm/models.py` | Native PDF document blocks |
| `onyx/chat/models.py` | Native PDF document blocks + ChatFileType TABULAR |
| `onyx/chat/llm_loop.py` | Native PDF document blocks |

## Hot-Mounts

- `home-lab-ca.crt` → `/usr/local/share/ca-certificates/` (ro) — Home Lab Root CA
- All 12 patch files mounted `:ro` on `api_server` and `background` (see override)

## Environment

| Var | Value/Purpose |
|-----|---------------|
| `AUTH_TYPE` | `oidc` — Authentik SSO at auth.arktechnwa.com |
| `WEB_DOMAIN` | `https://onyx.arktechnwa.com` |
| `HOST_PORT_80` / `HOST_PORT` | `8026` / `8027` — behind Kronos Caddy proxy |
| `DISABLE_TELEMETRY` | `true` |
| `FILE_STORE_BACKEND` | `postgres` — no MinIO |
| `OPENSEARCH_FOR_ONYX_ENABLED` | `true` |
| `SESSION_EXPIRE_TIME_SECONDS` | `604800` (7 days) |

## MCP Servers (13 registered, 4 disconnected)

Connected: Brick KG, Haugen KG, Saltman KG, Boinx KG, Grok Imagine (n8n),
Web Search, and others.

Disconnected: Zulip Chat, Vikunja, ocis-mcp, Boinx KG (duplicate).

## Containers

api_server, background, web_server, nginx, inference_model_server,
indexing_model_server, relational_db (postgres:15.2-alpine),
cache (redis:7.4-alpine), opensearch (3.4.0), index (vespa:8.609.39)

## Dependencies

- **Depends on:** johnny5-memory (agent KGs on port 3101), SFTPGo (Brick file storage)
- **Connects to:** n8n on Kronos (Grok Imagine MCP), Authentik (SSO)

---

## Agents

All agents are Onyx personas with `replace_base_system_prompt=true`.
Prompts are auto-synced from KG boot entities via systemd watchers.

| Agent | Persona ID | Model | Boot Entity | Sync Unit | Dirty File |
|-------|-----------|-------|-------------|-----------|------------|
| Brick | 2 | claude-sonnet-4-6 | `MY_BOOT` | `brick-boot-watcher` | `~/.cache/brick-boot-dirty` |
| Haugen | 5 | claude-opus-4-6 | `HAUGEN_NETWORK_BOOT` | `haugen-boot-watcher` | `~/.cache/haugen-boot-dirty` |
| Saltman | 6 | claude-sonnet-4-6 | `SALTMAN_NETWORK_BOOT` | `saltman-boot-watcher` | `~/.cache/saltman-boot-dirty` |

### Boot-Sync Architecture (Onyx Agents)

```
KG write hook (hooks.env)
  → touches dirty file (~/.cache/<agent>-boot-dirty)
  → systemd .path unit fires
  → sync script reads boot entity from KG
  → renders into prompt template
  → writes to Onyx postgres `persona.system_prompt` via docker exec psql
```

- **hooks.env:** `~/.config/johnny5-memory/hooks.env`
- **Sync scripts:** `PRJ-Brick-ISO/bin/brick-boot-sync`, `PRJ-haugen/bin/haugen-boot-sync`, `PRJ-Saltman-ISO/bin/saltman-boot-sync`
- All watchers use the dirty-file pattern (not WAL). Fixed 2026-07-11.

---

## J5 Boot Sequence

J5 (Johnny5) boots via Claude Code, not Onyx. Same KG-driven architecture,
different sync target: a hot-cached markdown file instead of a postgres row.

| Component | Path |
|-----------|------|
| Boot entity | `J5_NETWORK_BOOT` in KG |
| Cache file | `~/.claude/CLAUDE.J5_CACHE.md` |
| Cache sentinel | `<!-- J5:CACHE:v1 -->` |
| Generator | `PRJ-psychological-reinforcement/bin/j5-cache-gen` |
| Watcher | `j5-cache-watcher.path` → watches `~/.cache/j5-boot-dirty` |
| Fallback | MCP slow path: `read_graph()` + `open_nodes(["J5_NETWORK_BOOT"])` |

### Boot Flow

```
Session starts
  → CLAUDE.md loads boot harness
  → Fast path: CLAUDE.J5_CACHE.md exists with sentinel?
    YES → identity pre-loaded, skip MCP. "BOOTED. Johnny5 is alive."
    NO  → Slow path: read_graph() + open_nodes(["J5_NETWORK_BOOT"]) via MCP
  → First real message determines domain
  → Open relevant KG indices
```

### Cache Regeneration

```
KG write to J5_NETWORK_BOOT or any knowledge_index
  → hook touches ~/.cache/j5-boot-dirty
  → j5-cache-watcher.path fires
  → j5-cache-gen reads SQLite directly (no MCP, no network)
  → content-hashes to skip no-op regeneration
  → writes CLAUDE.J5_CACHE.md with sentinel
  → next Claude Code session boots instantly
```

The first hot-cached cloud prompt in the ArkTech ecosystem.
Paved the way for Brick, Haugen, and Saltman boot-sync.

### LibreChat Sync (legacy)

`j5-librechat-boot-watcher.path` also syncs J5 boot to LibreChat.
**WARNING:** Still uses the old WAL-watching pattern — may hit the same
burst limit that killed Brick's watcher. Should migrate to dirty-file.

---

## Rebuild Warnings

1. **`docker compose pull` will destroy all 12 patches** unless hot-mounts are active via the override
2. **Override must be in the active compose dir** — it only auto-loads from the working directory
3. **`docker compose restart` ≠ `up -d`** — restart ignores env/compose changes
4. **Image is currently a local build** — pulling upstream replaces it with whatever `latest` is
5. **Boot-sync watchers are independent** — rebuilding Onyx doesn't break them, but check `systemctl --user status *-boot-watcher.path` after any systemd changes
