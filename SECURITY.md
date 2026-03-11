# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it to: security@ansvar.eu

Do not open a public issue for security vulnerabilities.

## Security Measures

### Input Validation
- **File path traversal:** STDIO paths are resolved and validated against `ALLOWED_UPLOAD_DIR`
- **SQL injection:** All database queries use parameterized statements
- **FTS5 injection:** Search queries are tokenized and sanitized before MATCH (raw input never reaches FTS5)
- **File size:** Enforced before parsing via `MAX_FILE_SIZE_MB` env var
- **Base64 overflow:** HTTP endpoint validates encoded size before decoding

### Runtime
- Docker container runs as non-root user (`appuser`, UID 1000)
- No network egress required (all processing is local)
- SQLite WAL journal mode for data integrity
- Foreign key constraints with ON DELETE CASCADE
- HTTP endpoints require `X-API-Key` unless `MCP_AUTH_DISABLED=true`
- HTTP and STDIO document operations are tenant-scoped by `org_id`
- Conversation-scoped documents require matching `user_id`; organisation-wide writes require explicit caller approval

### Dependencies
- Minimal dependency set (pdfplumber, python-docx, openpyxl, python-pptx, beautifulsoup4, pytesseract, Pillow)
- No credential storage within the MCP
- HTTP authentication is enforced at the MCP level; platform callers must still supply the correct tenant/user context
