# Invoice Extraction Project

This project extracts tabular data from Amazon and Flipkart invoice PDFs and exports them to Excel files.

## Features

- Automatically detects Amazon and Flipkart invoices.
- Extracts order ID, seller, and line items from each invoice.
- Handles multiple PDFs in batch.
- Logs processing details and errors.

## Requirements

- Python 3.8+
- See `code/requirements.txt` for dependencies:
  - pdfplumber
  - camelot-py
  - pandas
  - openpyxl

## Setup

1. Install dependencies:
   ```bash
   pip install -r code/requirements.txt
   ```

2. Place your invoice PDFs in the `input/` folder (create if missing).

## Usage

Run the extraction script:

```bash
python code/extract_invoices.py
```

- Output Excel files will be saved in the `output/` folder.
- Logs are written to `extract.log`.

## Notes

- Only PDFs with recognizable tables will be processed.
- If a PDF cannot be classified or parsed, it will be skipped with a warning in the log.

## Troubleshooting

- If you see warnings about "CropBox missing", they are safe to ignore.
- If you get "No tables found" warnings, the PDF may not contain extractable tables.

---
