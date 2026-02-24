# Disclaimer

Document-Index-MCP provides deterministic full-text indexing and search of uploaded documents. It does not perform AI extraction, interpretation, or analysis of document content.

## Important

- This tool indexes document text as-is. It does not validate accuracy, completeness, or currency of document content.
- Search results are ranked by BM25 relevance. Ranking does not imply importance, correctness, or legal standing.
- OCR-processed documents (images) may contain recognition errors.
- Section detection is heuristic-based (heading patterns, styles). Complex document layouts may result in imperfect section boundaries.
- This software is provided "as is" without warranty of any kind.

## Data Handling

- All indexed content is stored locally in SQLite. No data is transmitted to external services.
- No AI/LLM processing is applied to document content during indexing.
- Documents can be permanently deleted via the `delete_document` tool.
