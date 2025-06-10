import re, logging, pathlib, sys, pdfplumber, camelot
import pandas as pd

ROOT        = pathlib.Path(__file__).resolve().parent.parent
INPUT_DIR   = ROOT / "input"
OUTPUT_DIR  = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=ROOT / "extract.log",
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s"
)

# ---------- helper ----------------------------------------------------------
def text_from_pdf(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def find_first(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return m.group(1).strip()
    return None

# ---------- Amazon parsing --------------------------------------------------
ORDER_PATTERNS = [
    r"Order\s*(?:ID|#|No\.?)\s*[:#-]?\s*([A-Z0-9-]+)"
]
AMZ_SELLER_PAT = r"Sold\s*By\s*[:\-]?\s*(.+)"

def parse_amazon(path):
    text = text_from_pdf(path)
    order_id   = find_first(ORDER_PATTERNS, text)  or "UNKNOWN"
    seller     = find_first([AMZ_SELLER_PAT], text) or "UNKNOWN"

    # capture main table with Camelot
    tables = camelot.read_pdf(str(path), pages="all", flavor="lattice")
    if not tables or len(tables) == 0:
        logging.warning(f"No tables found in Amazon invoice: {path.name}")
        return None
    df = tables[0].df          # first table usually contains line items
    df.columns = df.iloc[0]    # promote header row
    df = df.drop(0).reset_index(drop=True)

    df.insert(0, "Order_ID", order_id)
    df.insert(1, "Seller", seller)
    return df

# ---------- Flipkart parsing ------------------------------------------------
FLIP_PAT_ORDER = r"Order\s*ID\s*[:\-]?\s*([A-Z0-9-]+)"
FLIP_PAT_SELL  = r"Seller\s*[:\-]?\s*(.+)"

def parse_flipkart(path):
    text = text_from_pdf(path)
    order_id = find_first([FLIP_PAT_ORDER], text) or "UNKNOWN"
    seller   = find_first([FLIP_PAT_SELL], text)  or "UNKNOWN"

    tables = camelot.read_pdf(str(path), pages="all", flavor="lattice")
    if not tables or len(tables) == 0:
        logging.warning(f"No tables found in Flipkart invoice: {path.name}")
        return None
    df = tables[0].df
    df.columns = df.iloc[0]
    df = df.drop(0).reset_index(drop=True)

    df.insert(0, "Order_ID", order_id)
    df.insert(1, "Seller", seller)
    return df

# ---------- main driver -----------------------------------------------------
def classify_invoice(text):
    if "amazon" in text.lower():
        return "amazon"
    if "flipkart" in text.lower():
        return "flipkart"
    return "unknown"

def main():
    amazon_frames, flipkart_frames = [], []

    pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_paths:
        logging.error("No PDF files found in input/. Exiting.")
        sys.exit("No PDFs to process.")

    for p in pdf_paths:
        text = text_from_pdf(p)
        vendor = classify_invoice(text)

        try:
            if vendor == "amazon":
                df = parse_amazon(p)
                if df is not None:
                    amazon_frames.append(df)
                    logging.info(f"Parsed Amazon invoice: {p.name}")
                else:
                    logging.warning(f"Skipped Amazon invoice (no table): {p.name}")
            elif vendor == "flipkart":
                df = parse_flipkart(p)
                if df is not None:
                    flipkart_frames.append(df)
                    logging.info(f"Parsed Flipkart invoice: {p.name}")
                else:
                    logging.warning(f"Skipped Flipkart invoice (no table): {p.name}")
            else:
                logging.warning(f"Could not classify invoice: {p.name}")
        except Exception as e:
            logging.exception(f"Error parsing {p.name}: {e}")

    # ---------- export ------------------------------------------------------
    if amazon_frames:
        pd.concat(amazon_frames, ignore_index=True).to_excel(
            OUTPUT_DIR / "amazon_invoices.xlsx", index=False
        )
    if flipkart_frames:
        pd.concat(flipkart_frames, ignore_index=True).to_excel(
            OUTPUT_DIR / "flipkart_invoices.xlsx", index=False
        )

    print("✅ Extraction run complete — check the output/ folder and extract.log")

# No changes needed in this file.
# The error is due to PowerShell syntax, not Python code.
# Run each script separately, like:

if __name__ == "__main__":
    main()
