# Privacy Policy

## Data Collection

Document-Index-MCP processes and stores document content locally. It does not:

- Transmit data to external services
- Use AI/LLM APIs for processing
- Collect telemetry or usage analytics
- Store data outside the configured SQLite database path

## Data Storage

- All document content is stored in a local SQLite database
- The database path is configurable via `DOCUMENT_INDEX_DB_PATH` environment variable
- Data is stored unencrypted on disk (rely on filesystem/volume encryption)

## Data Deletion

- Use the `delete_document` tool to permanently remove a document and all its indexed sections
- Deletion cascades to the FTS5 search index
- SQLite `VACUUM` can be run manually to reclaim disk space after deletions

## Data Isolation

- Each deployment has its own isolated SQLite database
- HTTP and STDIO operations require tenant context (`org_id`) for document access
- Conversation-scoped documents are further isolated by `user_id`
- Legacy unscoped rows are migrated to a non-routable `legacy_unassigned` tenant until re-indexed
