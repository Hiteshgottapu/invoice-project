import re
import glob
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber
import pandas as pd

# ─── Setup ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR.parent / 'Input'
OUTPUT_DIR = BASE_DIR.parent / 'Output'
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Patterns to identify financial summary fields
AMOUNTS_PATTERNS: Dict[str, List[str]] = {
    'Subtotal':     [r"Sub\s*-?Total", r"Sub\s*Total"],
    'Discount':     [r"Coupon", r"Discount", r"Offer"],
    'Tax':          [r"Tax", r"GST", r"VAT"],
    'Shipping Fee': [r"Shipping", r"Delivery", r"Freight"],
    'Total':        [r"Grand\s*Total", r"Total"]
}

# Column keywords for line items (including Flipkart synonyms)
ITEM_COL_KEYWORDS    = ['product', 'item', 'description', 'name']
QTY_COL_KEYWORDS     = ['qty', 'quantity']
UNIT_PRICE_KEYWORDS  = ['unit price', 'gross', 'net amount', 'price', 'rate']
TOTAL_PRICE_KEYWORDS = ['total amount', 'total', 'amount', 'amt']

# Date patterns for metadata
DATE_LABELS = {
    'Order Date':   (r"Order\s*Date[:\s]+([\d./-]+)", r"([\d./-]+)\s*Order\s*Date"),
    'Invoice Date': (r"Invoice\s*Date[:\s]+([\d./-]+)", r"([\d./-]+)\s*Invoice\s*Date")
}

PAYMENT_PATTERN = r"(?:Payment\s*(?:Method|Info)|Mode\s*of\s*Payment)[:\s]+(.+)"


def clean_currency(val: Optional[str]) -> Optional[float]:
    if not val or not isinstance(val, str):
        return None
    digits = re.sub(r"[^0-9.]", "", val)
    try:
        return float(digits)
    except ValueError:
        return None


def extract_financial_table(pages: List[Any]) -> Dict[str, float]:
    summary: Dict[str, float] = {}
    for page in pages:
        for table in page.extract_tables() or []:
            for row in table:
                if not row or len(row) < 2:
                    continue
                key = str(row[0]).strip().lower()
                val = clean_currency(str(row[-1]))
                # Match 'Total' only if not 'Subtotal' or 'Grand Total'
                if any(re.search(lbl, key, re.IGNORECASE) for lbl in AMOUNTS_PATTERNS['Total']):
                    # Avoid overwriting if already set and value is None
                    if 'Total' not in summary or (val is not None and summary['Total'] is None):
                        summary['Total'] = val
                elif any(re.search(lbl, key, re.IGNORECASE) for lbl in AMOUNTS_PATTERNS['Subtotal']):
                    if 'Subtotal' not in summary or (val is not None and summary['Subtotal'] is None):
                        summary['Subtotal'] = val
                elif any(re.search(lbl, key, re.IGNORECASE) for lbl in AMOUNTS_PATTERNS['Tax']):
                    if 'Tax' not in summary or (val is not None and summary['Tax'] is None):
                        summary['Tax'] = val
                elif any(re.search(lbl, key, re.IGNORECASE) for lbl in AMOUNTS_PATTERNS['Shipping Fee']):
                    if 'Shipping Fee' not in summary or (val is not None and summary['Shipping Fee'] is None):
                        summary['Shipping Fee'] = val
                elif any(re.search(lbl, key, re.IGNORECASE) for lbl in AMOUNTS_PATTERNS['Discount']):
                    if 'Discount' not in summary or (val is not None and summary['Discount'] is None):
                        summary['Discount'] = val
    return summary


def extract_amount_text(text: str, labels: List[str]) -> Optional[float]:
    for lbl in labels:
        pattern = rf"{lbl}\s*[:\s]*[₹$€]?\s*([0-9]{{1,3}}(?:,[0-9]{{3}})*(?:\.\d{{1,2}})?)"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_currency(m.group(1))
    return None


def warn_missing(df: pd.DataFrame, column: str, sheet: str) -> None:
    missing = df[column].isna().sum()
    if missing:
        logger.warning(f"Sheet '{sheet}' missing {missing} '{column}' entries")


def parse_metadata(text: str, filename: str) -> Dict[str, Any]:
    def find(pat: str) -> Optional[str]:
        m = re.search(pat, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def find_date(label: str) -> Optional[str]:
        p1, p2 = DATE_LABELS[label]
        m = re.search(p1, text, re.IGNORECASE) or re.search(p2, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    meta = {
        'Source PDF':     filename,
        'Order ID':       find(r'(?:Order\s*ID|Order\s*Number)[:\s]+(\S+)'),
        'Invoice No.':    find(r'Invoice\s*(?:Number|No\.?)[:\s]+(\S+)'),
        'Order Date':     find_date('Order Date'),
        'Invoice Date':   find_date('Invoice Date'),
        'Payment Method': find(PAYMENT_PATTERN) or ''
    }
    def extract_block(labels: List[str]) -> str:
        alt = '|'.join(labels)
        pat = rf'(?:{alt})[:\s]*\n((?:[^\n]+\n?){{1,6}})(?=\n|$)'
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            pat = rf'(?:{alt})[:\s]*\n(.*?)(?=\n(?:Order\s*Date|Invoice\s*Date|Payment|[\w ]+ Address))'
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        return '' if not m else '\n'.join(ln.strip() for ln in m.group(1).splitlines() if ln.strip())

    meta['Billing Address']  = extract_block(['Billing Address'])
    meta['Shipping Address'] = extract_block(['Shipping Address', 'Delivery Address'])
    return meta


def parse_financials(pages: List[Any], text: str, filename: str, order_id: Optional[str]) -> Dict[str, Any]:
    summary = extract_financial_table(pages)
    fin = {'Source PDF': filename, 'Order ID': order_id}
    if summary:
        for k in ['Subtotal', 'Tax', 'Shipping Fee', 'Discount', 'Total']:
            fin[k] = summary.get(k, 0.0)
    else:
        for col, pats in AMOUNTS_PATTERNS.items():
            fin[col] = extract_amount_text(text, pats)
    return fin


def map_column(header: str) -> Optional[str]:
    h = header.lower()
    if any(k in h for k in ITEM_COL_KEYWORDS):    return 'item'
    if any(k in h for k in QTY_COL_KEYWORDS):     return 'qty'
    if any(k in h for k in UNIT_PRICE_KEYWORDS):  return 'unit_price'
    if any(k in h for k in TOTAL_PRICE_KEYWORDS) and 'unit' not in h: return 'total_price'
    return None

def parse_line_items(pages: List[Any], text: str, filename: str, order_id: Optional[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for page in pages:
        tables = page.extract_tables() or []
        for table in tables:
            if not table or len(table) < 2:
                continue
            hdrs = [str(h or '').strip().lower() for h in table[0]]
            cmap = {i: map_column(h) for i, h in enumerate(hdrs) if map_column(h)}
            if 'qty' not in cmap.values():
                continue
            for row in table[1:]:
                data = {cmap[i]: row[i] for i in cmap if i < len(row) and row[i]}
                name = data.get('item', '').strip()
                if not name:
                    continue
                try:
                    qty = int(data.get('qty', '1'))
                except Exception:
                    qty = 1
                unit_price = clean_currency(data.get('unit_price'))
                total_price = clean_currency(data.get('total_price'))
                # If total_price is None or 0, but unit_price and qty are present, calculate total_price
                if (total_price is None or total_price == 0) and unit_price is not None and qty:
                    total_price = unit_price * qty
                items.append({
                    'Source PDF': filename,
                    'Order ID': order_id,
                    'Item Name': name,
                    'Description': name,
                    'Quantity': qty,
                    'Unit Price': unit_price,
                    'Total Price': total_price
                })
    # Only use fallback if no items found from tables
    if not items:
        fallback1 = re.compile(
            r"(.+?)\s+Qty[:\s]+(\d+)\s+Rate[:\s]+([0-9,]+(?:\.[0-9]{1,2})?)\s+Amount[:\s]+([0-9,]+(?:\.[0-9]{1,2})?)",
            re.IGNORECASE
        )
        fallback_count = 0
        for m in fallback1.finditer(text):
            desc = m.group(1).strip()
            qty_s = m.group(2)
            rate_s = m.group(3)
            amt_s = m.group(4)
            try:
                qty = int(qty_s)
            except Exception:
                qty = 1
            unit_price = clean_currency(rate_s)
            total_price = clean_currency(amt_s)
            if (total_price is None or total_price == 0) and unit_price is not None and qty:
                total_price = unit_price * qty
            item_name = desc if desc else "Unknown"
            items.append({
                'Source PDF': filename,
                'Order ID': order_id,
                'Item Name': item_name,
                'Description': desc,
                'Quantity': qty,
                'Unit Price': unit_price,
                'Total Price': total_price
            })
            fallback_count += 1
        if fallback_count == 0:
            logger.warning(f"No line items extracted from fallback for {filename}")
            # Improved generic fallback for Flipkart: match columns with possible headers
            lines = text.splitlines()
            header_idx = -1
            for idx, line in enumerate(lines):
                if re.search(r'description.*qty.*gross.*taxable.*igst.*total', line.replace(' ', '').lower()):
                    header_idx = idx
                    break
            if header_idx >= 0:
                for line in lines[header_idx + 1:]:
                    m = re.match(
                        r"(.+?)\s+(\d+)\s+([0-9,.]+)\s+([0-9,.]+)\s+([0-9,.]+)\s+([0-9,.]+)\s+([0-9,.]+)",
                        line.strip()
                    )
                    if m:
                        desc = m.group(1).strip()
                        qty = int(m.group(2))
                        gross = clean_currency(m.group(3))
                        total = clean_currency(m.group(7))
                        if (total is None or total == 0) and gross is not None and qty:
                            total = gross * qty
                        item_name = desc if desc else "Unknown"
                        items.append({
                            'Source PDF': filename,
                            'Order ID': order_id,
                            'Item Name': item_name,
                            'Description': desc,
                            'Quantity': qty,
                            'Unit Price': gross,
                            'Total Price': total
                        })
                if not items:
                    logger.warning(f"No line items found even with improved generic fallback for {filename}.")
                else:
                    logger.info(f"Extracted {len(items)} line items from improved generic fallback for {filename}")
            else:
                for line in lines:
                    m = re.match(r"(.+?)\s+(\d+)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})", line)
                    if m:
                        desc = m.group(1).strip()
                        qty = int(m.group(2))
                        unit_price = clean_currency(m.group(3))
                        total_price = clean_currency(m.group(4))
                        if (total_price is None or total_price == 0) and unit_price is not None and qty:
                            total_price = unit_price * qty
                        item_name = desc if desc else "Unknown"
                        items.append({
                            'Source PDF': filename,
                            'Order ID': order_id,
                            'Item Name': item_name,
                            'Description': desc,
                            'Quantity': qty,
                            'Unit Price': unit_price,
                            'Total Price': total_price
                        })
                if not items:
                    logger.warning(f"No line items found even with generic fallback for {filename}.")
                else:
                    logger.info(f"Extracted {len(items)} line items from generic fallback for {filename}")
        else:
            logger.info(f"Extracted {fallback_count} line items from fallback for {filename}")
    # Remove blank and duplicate item names per order
    unique, results = set(), []
    for it in items:
        key = (it['Order ID'], it['Item Name'], it['Quantity'], it['Unit Price'], it['Total Price'])
        if it['Item Name'] and key not in unique:
            unique.add(key)
            results.append(it)
    return results


def main() -> None:
    metas, fins, items = [], [], []
    for pdf in glob.glob(str(INPUT_DIR / '*.pdf')):
        name = Path(pdf).name
        try:
            with pdfplumber.open(pdf) as doc:
                pages = doc.pages
                txt = '\n'.join(p.extract_text() or '' for p in pages)
        except Exception as e:
            logger.error(f"Failed {name}: {e}")
            continue
        metas.append(parse_metadata(txt, name))
        fins.append(parse_financials(pages, txt, name, metas[-1].get('Order ID')))
        items.extend(parse_line_items(pages, txt, name, metas[-1].get('Order ID')))

    df_meta = pd.DataFrame(metas)
    df_fin = pd.DataFrame(fins)
    df_items = pd.DataFrame(items)

    # Remove duplicate rows from all sheets
    df_meta = df_meta.drop_duplicates()
    df_fin = df_fin.drop_duplicates()
    # Remove duplicates in line items based on all columns except 'Description'
    df_items = df_items.drop_duplicates(subset=['Source PDF', 'Order ID', 'Item Name', 'Quantity', 'Unit Price', 'Total Price'])

    # Remove rows with meaningless or repeated "Total", "Platform Fee", or numeric-only item names
    df_items = df_items[
        ~df_items['Item Name'].str.strip().str.lower().isin(['total', 'sac: 998599 platform fee'])
        & ~df_items['Item Name'].str.strip().str.match(r'^\d+(\s+0\.00)?$')
        & df_items['Item Name'].str.strip().str.len().gt(2)
    ]

    warn_missing(df_meta, 'Order ID', 'Headers & Addresses')
    warn_missing(df_fin, 'Subtotal', 'Financial Summary')
    warn_missing(df_items, 'Item Name', 'Line Items Detail')
    warn_missing(df_items, 'Total Price', 'Line Items Detail')

    out = OUTPUT_DIR / 'Invoices_Deep_Extraction.xlsx'
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df_meta.to_excel(writer, sheet_name='Headers & Addresses', index=False)
        df_fin.to_excel(writer, sheet_name='Financial Summary', index=False)
        df_items.to_excel(writer, sheet_name='Line Items Detail', index=False)

    logger.info(f"Done. Saved to {out}")

if __name__ == '__main__':
    main()
