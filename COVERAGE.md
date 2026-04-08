# Document-Index-MCP — Coverage

## Supported Formats

| Extension | Parser | Notes |
|-----------|--------|-------|
| `.pdf` | pdfplumber | Cross-page section merging; requires pdfplumber |
| `.docx` | python-docx | Heading-based section splitting; table extraction |
| `.xlsx` | openpyxl | One section per sheet |
| `.csv` | stdlib csv | Single section with full content |
| `.pptx` | python-pptx | One section per slide |
| `.html` / `.htm` | BeautifulSoup | Heading-based section splitting |
| `.txt` | stdlib | Heading detection heuristics |
| `.md` | stdlib | Markdown heading detection |
| `.png` / `.jpg` / `.jpeg` / `.tiff` / `.tif` / `.bmp` / `.gif` / `.webp` | pytesseract | OCR; requires Tesseract installed |

## Known Limitations

- **PDF**: Scanned PDFs without embedded text are not supported (use image formats with OCR instead).
- **Images / OCR**: Quality depends on Tesseract version and image resolution. Low-resolution scans may produce poor results.
- **XLSX**: Merged cells may produce incomplete section content.
- **PPTX**: Speaker notes are not indexed.
- **HTML**: JavaScript-rendered content is not executed; only static HTML is parsed.
- **File size**: Default maximum is 50 MB (configurable via `MAX_FILE_SIZE_MB` env var).
- **Languages**: FTS5 tokeniser is ASCII/Unicode; non-Latin scripts index correctly but stemming is English-only.

## Machine-Readable Coverage

See [`data/coverage.json`](data/coverage.json) for a structured format map used by fleet tooling.
