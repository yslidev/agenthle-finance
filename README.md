# SEC Filing Financial Data Extraction

Automated extraction of financial metrics from SEC EDGAR XBRL filings for IBD analysts and equity researchers.

## Use Cases

- **Comp set building**: Extract 5-10 companies' financials in standardized format for M&A valuation
- **DCF model updates**: Get latest annual revenue, margins, and cash flows from fresh 10-K filings
- **Pitchbook tables**: Pull historical 3-year financials for target and comparable companies
- **Due diligence**: Validate management-provided numbers against official SEC filings

## Installation

```bash
pip install edgartools --user
```

## Usage

```bash
# Set SEC identity (required by SEC.gov)
export SEC_IDENTITY="your_name@email.com"

# Run extraction
python workflow1_sec_extraction.py --input input/company_list.json --output output/
```

## Input Format

Create `input/company_list.json`:

```json
{
  "companies": [
    {
      "ticker": "AAPL",
      "company_name": "Apple Inc",
      "fiscal_year": 2023,
      "metrics": ["Revenue", "NetIncome", "TotalAssets", "OperatingCashFlow"]
    }
  ]
}
```

### Supported Metrics

| Metric | XBRL Tag |
|--------|----------|
| Revenue | RevenueFromContractWithCustomerExcludingAssessedTax |
| NetIncome | NetIncomeLoss |
| TotalAssets | Assets |
| TotalLiabilities | Liabilities |
| StockholdersEquity | StockholdersEquity |
| GrossProfit | GrossProfit |
| OperatingIncome | OperatingIncomeLoss |
| OperatingCashFlow | NetCashProvidedByUsedInOperatingActivities |
| EPS | EarningsPerShareBasic |
| SharesOutstanding | CommonStockSharesOutstanding |

## Output

### `financial_data.json`
```json
{
  "company": "Apple Inc",
  "ticker": "AAPL",
  "cik": 320193,
  "fiscal_year": 2023,
  "metrics": {
    "Revenue": {
      "value": 383285000000,
      "unit": "USD",
      "xbrl_tag": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    }
  }
}
```

### `filing_metadata.json`
Includes accession numbers, filing dates, and SEC EDGAR URLs for verification.

### `extraction.log`
Full audit trail with timestamps and API calls.

## Verification

Each extracted metric includes:
- XBRL tag name for traceability
- Filing accession number
- Direct URL to SEC EDGAR filing

Accuracy target: 100% (exact match within $1M rounding for values in billions).

## Notes

- SEC API is free but rate-limited (10 requests/second)
- `edgartools` handles XBRL tag normalization
- User-agent identification required by SEC.gov
