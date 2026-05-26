# zsxq-cli POC Plan

## Goal

Evaluate whether the official `zsxq-cli` / `zsxq-skill` stack can replace or partially replace the current cookie-based ZsxqCrawler ingestion path.

## Scope

- Keep this POC read-only.
- Do not modify existing crawler runtime, PostgreSQL writes, frontend routes, or task runtime.
- Do not read or print `.env`, cookies, tokens, or local account secrets.
- Compare only the official CLI availability and topic-read surface first.
- For the configured `zsxq-topic` MCP server, read the URL from `codex mcp get` but never write the URL or API key into probe output.

## Docs Checked

- `README.md`
- `docs/project-architecture-roadmap.md`
- `docs/postgres_core_reader_usage.md`
- `docs/group_scope_audit.md`
- External reference checkout: `C:\Dev\_external\zsxq-skill`

## Execution Steps

1. Verify the installed official CLI binary can run on Windows.
2. Verify local OAuth login state.
3. If logged in, fetch one page with `group +topics --json`.
4. If topics are returned, fetch `topic +detail --json` for the first topic.
5. Compare the observed output shape with the fields ZsxqCrawler needs for ingestion.

## Verification Plan

```powershell
uv run python scripts\probe_zsxq_cli_topics.py
uv run python scripts\probe_zsxq_cli_topics.py --group-id 51111112855254 --limit 3 --detail
uv run python scripts\probe_zsxq_mcp_topics.py --group-id 51111112855254 --limit 3 --comments
uv run python scripts\probe_zsxq_mcp_import_coverage.py --group-id 51111112855254 --per-category 2 --latest-limit 5 --begin-time "2026-05-20T10:00:00.000+0800" --end-time "2026-05-20T23:59:59.999+0800"
uv run python scripts\probe_zsxq_mcp_range_pull.py --group-id 51111112855254 --days 30 --limit 30 --max-pages 10000
uv run python -m py_compile scripts\probe_zsxq_mcp_import_coverage.py scripts\probe_zsxq_mcp_topics.py scripts\probe_zsxq_cli_topics.py
```

## Progress

- Created `scripts/probe_zsxq_cli_topics.py` as a read-only CLI probe.
- Direct `zsxq-cli.exe --help` works when called from the installed platform binary under the npm cache.
- `npx zsxq-cli@latest --help` fails in this Windows environment because the shim does not resolve `zsxq-cli`, even though the platform binary exists.
- `auth status --json` returns `loggedIn: false`, so live topic-fetch validation is currently blocked on OAuth login.
- `uv run python scripts\probe_zsxq_cli_topics.py` found the cached official Windows binary and returned blocked status because no OAuth user is logged in.
- `uv run python scripts\probe_zsxq_cli_topics.py --group-id 51111112855254 --limit 3 --detail` reached the same auth gate before any topic read.
- `uv run python -m py_compile scripts\probe_zsxq_cli_topics.py` passed.
- After global installation and OAuth login, `zsxq-cli auth status --json` returned `loggedIn: true` for user `28888121888141`.
- `zsxq-cli group +list --limit 200 --json` returned 7 joined groups, including group `51111112855254`.
- `zsxq-cli group +topics --group-id 51111112855254 --limit 3 --json` and `zsxq-cli api call get_group_topics --params '{"group_id":"51111112855254","limit":3,"scope":"all"}'` both returned 3 live topics.
- Fixed `scripts/probe_zsxq_cli_topics.py` to parse the official `topics_brief` key; it now returns topic summaries and detail status through the global CLI.
- Added `zsxq-topic` as a Codex MCP server and verified the streamable HTTP handshake manually from this session.
- MCP `initialize` returned server `TopicServer` version `1.26.0`.
- MCP `tools/list` returned 21 tools, including read tools `get_group_topics`, `get_topic_info`, `get_topic_comments`, and `call_zsxq_api`.
- `uv run python scripts\probe_zsxq_mcp_topics.py --group-id 51111112855254 --limit 3 --comments` passed. It returned 3 latest topics with `has_more` / `next_end_time`, topic counters, owner/group metadata, content, images, and file metadata.
- The 3-topic latest sample had no comments. A manual 5-page scan over 150 latest topics also found no topic with `comments_count > 0`, so `get_topic_comments` remains tool-listed but not yet payload-validated on a live commented topic.
- Added `scripts/probe_zsxq_mcp_import_coverage.py` to compare MCP topic/detail/comment payloads against the existing `import_topic_data()` expectations without writing to PostgreSQL.
- The coverage probe selected local samples for comments, q&a, images, tags, and files, then fetched 14 topic details through MCP. Local article samples were absent for group `51111112855254`.
- `get_topic_comments` is now payload-validated on two live topics with `comments_count = 1`; payload keys were `comments`, `count`, `has_more`, `index`, and `success`.
- A q&a sample was fetched and can map to a basic `question` row, but no `answer` payload was observed.
- Image and file metadata were observed in MCP topic details and can map to existing `images`, `topic_files`, and `files` rows after shape conversion.
- Direct `call_zsxq_api` probes for `/v2/groups/{group_id}/topics` returned `404`, so raw begin/end topic API parity is not available through that path.
- Passing `begin_time` to `get_group_topics` appears ignored; `end_time` works. Time-range crawling would need end-time paging plus local filtering, not a direct begin/end request.
- Added `scripts/probe_zsxq_mcp_range_pull.py` to test read-only time-window pulls using `end_time` paging and local filtering.
- A 30-day read-only pull for group `51111112855254` scanned 145 pages / 4350 topic rows in about 146 seconds, matched 4328 rows before de-duplication, and stopped cleanly when the oldest page crossed `2026-04-21T00:00:00.000+0800`.
- The 30-day pull had no API failures, empty-page failures, rate-limit errors, or cursor-stall stop. It did show 144 duplicate topic rows because the next page commonly repeats the previous page's last topic at the boundary.
- A 3-day follow-up pull confirmed the boundary duplication pattern: 27 pages / 810 scanned rows / 769 unique matched topics / 26 duplicate matched rows.

## Verification Results

| Command | Result | Evidence |
| --- | --- | --- |
| `zsxq-cli.exe --help` | Passed | Direct platform binary prints command help. |
| `npx zsxq-cli@latest --help` | Failed | npm installs the package, but the npx shim reports `'zsxq-cli' is not recognized`. |
| `uv run python scripts\probe_zsxq_cli_topics.py` | Passed after OAuth login | CLI found; `auth.status` JSON says `loggedIn: true`. |
| `uv run python scripts\probe_zsxq_cli_topics.py --group-id 51111112855254 --limit 3 --detail` | Passed after parser fix | CLI returned 3 topics via `topics_brief` and detail top-level keys `success`, `topic`. |
| `uv run python scripts\probe_zsxq_mcp_topics.py --group-id 51111112855254 --limit 3 --comments` | Passed with comment caveat | MCP returned live topics and detail summary; comment fetch was skipped because returned topics had zero comments. |
| `uv run python scripts\probe_zsxq_mcp_import_coverage.py --group-id 51111112855254 --per-category 2 --latest-limit 5 --begin-time "2026-05-20T10:00:00.000+0800" --end-time "2026-05-20T23:59:59.999+0800"` | Passed with range caveat | MCP covered groups/users/topics/talks/comments/questions/images/files/topic_files after normalization; raw begin/end API probe returned 404. |
| `uv run python scripts\probe_zsxq_mcp_range_pull.py --group-id 51111112855254 --days 30 --limit 30 --max-pages 10000` | Passed | Read-only end-time paging reached the one-month window boundary after 145 pages; must de-duplicate by topic_id. |
| `uv run python -m py_compile scripts\probe_zsxq_mcp_import_coverage.py scripts\probe_zsxq_mcp_topics.py scripts\probe_zsxq_cli_topics.py` | Passed | Script syntax is valid. |

## Current Finding

The official CLI is usable as a local binary and now works after OAuth login. The configured `zsxq-topic` MCP server also provides authenticated read access in the current environment. Both routes can fetch live group topics with the same broad payload shape.

MCP topic payload coverage observed:

- Supported: paged topic list, `has_more`, `next_end_time`, topic id, type, title, content, owner, group, create/modify time, digested flag, engagement counts, images, and file metadata.
- Supported: topic detail shape for a returned topic, with the same core topic keys.
- Supported after coverage probe: comment payload shape for simple comments, with comment id, text, owner, create time, likes/rewards, and sticky fields.
- Partially supported after normalization: q&a question rows, topic images, topic files, core file metadata, and topic counters.
- Not yet validated on live data: article rows, answer rows, latest likes, like emojis, user-liked emojis, and tag extraction. The local group had tag sample ids, but MCP topic payload did not expose explicit hashtag metadata in the tested detail payload.
- Not covered by current MCP topic tools: downloading file bytes or signed file download URLs, unless a future `call_zsxq_api` probe confirms the exact endpoint and permission behavior.
- Not equivalent to current range crawler: `get_group_topics` supports `end_time`, while `begin_time` was ignored in the probe. Existing time-range behavior can be approximated by paging and local filtering, but direct API parity is unproven.
- Practical range pull result: one month of `51111112855254` was readable without observed rate limits, but it required 145 requests at page size 30 and returned duplicate boundary rows. Any adapter must de-duplicate by `topic_id`, persist the last cursor for resume, and stop by local `begin_time` comparison.

## Replacement Boundary

The MCP server is now a stronger candidate than the local CLI for replacing the low-level topic-list/topic-detail read adapter. It should still not replace ZsxqCrawler's PostgreSQL ownership, task runtime, file download/status workflow, AI reports, A-share extraction, or group workbench product surfaces.

Recommended next slice:

1. Build an opt-in adapter that maps `get_group_topics` payloads into the existing `import_topic_data()` input shape.
2. Run a dry-run comparison for one historical page: existing crawler API payload vs MCP normalized payload.
3. Add unit tests for the MCP-to-import normalization shape before wiring it into any runtime.
4. Probe file download URL support separately before considering downloader replacement.
