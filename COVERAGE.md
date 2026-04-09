# Document-Index-MCP Coverage

## Supported Formats

| Extension | Parser Library | Notes |
|-----------|---------------|-------|
| `.pdf` | pdfplumber | Cross-page section merging; multi-column layouts may produce merged text |
| `.docx` | python-docx | Heading-based section splitting; table extraction included |
| `.xlsx` | openpyxl | One section per sheet; cell values concatenated |
| `.csv` | built-in csv | Single section containing all rows |
| `.pptx` | python-pptx | One section per slide; speaker notes included |
| `.html` / `.htm` | beautifulsoup4 | Heading-based (`h1`–`h6`) section splitting |
| `.txt` | built-in | Heading detection via capitalised/underlined lines |
| `.md` | built-in | `#` heading detection |
| `.png` / `.jpg` / `.jpeg` / `.tiff` / `.tif` / `.bmp` / `.gif` / `.webp` | pytesseract + Pillow | OCR; requires Tesseract to be installed |

## Known Limitations

- **OCR quality**: Image-based PDFs or low-resolution scans may produce poor OCR output. Tesseract accuracy depends on image quality and language.
- **Multi-column PDF layouts**: pdfplumber reads text in stream order; columns may be interleaved. Column-detection is not applied.
- **Maximum file size**: Configurable via `MAX_FILE_SIZE_MB` environment variable (default 50 MB).
- **Password-protected documents**: Not supported. Files encrypted with a password will fail to parse.
- **Scanned PDFs without embedded text**: Treated as images only if converted first; otherwise pdfplumber returns empty text. Use an image format instead.
- **XLSX formulas**: Only computed cell values are indexed, not the formula strings.
- **Right-to-left languages**: OCR and parser libraries have limited RTL support.

## Data Provenance

All documents are **user-provided**. There is no external data feed or scheduled refresh. Data freshness is entirely dependent on manual uploads via the `/index` or `/index-file` endpoints.

## Search

Full-text search uses SQLite FTS5 with BM25 ranking. Snippets are extracted at the section level (not page level for PDFs).
