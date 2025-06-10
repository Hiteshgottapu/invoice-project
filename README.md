# Invoice Extraction Project

This project extracts structured data from invoice PDFs, including metadata, financial summaries, and line items, and exports the results to an Excel file.

## Features

- Extracts order and invoice metadata (Order ID, Invoice No., Dates, Addresses, Payment Method)
- Extracts financial summary (Subtotal, Tax, Shipping Fee, Discount, Total)
- Extracts detailed line items (Item Name, Quantity, Unit Price, Total Price)
- Handles various invoice formats, including Flipkart and similar e-commerce invoices
- Outputs results to an Excel file with separate sheets for metadata, financials, and line items

## Requirements

- Python 3.8+
- See `requirements.txt` for dependencies:
  - pdfplumber
  - camelot-py
  - pandas
  - openpyxl

Install dependencies with:
```bash
pip install -r requirements.txt
```

## Usage

1. Place your invoice PDF files in the `Input` directory (create it if it doesn't exist).
2. Run the extraction script:
   ```bash
   python extract_invoices.py
   ```
3. The results will be saved as `Invoices_Deep_Extraction.xlsx` in the `Output` directory.

## Notes

- The script is designed to handle a variety of invoice layouts, but results may vary depending on PDF quality and structure.
- For debugging, logs are printed to the console.

## Project Structure

```
invoice-project/
├── code/
│   ├── extract_invoices.py
│   └── requirements.txt
├── Input/
│   └── (your PDF files here)
├── Output/
│   └── Invoices_Deep_Extraction.xlsx
└── README.md
```

## License

This project is provided for educational and personal use.
