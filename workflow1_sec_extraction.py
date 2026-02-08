#!/usr/bin/env python3
"""
SEC Filing Financial Data Extraction Workflow

Extracts financial metrics from SEC EDGAR XBRL filings for IBD/equity research.
Uses the edgartools library to query SEC EDGAR API.

Usage:
    pip install edgartools --user
    export SEC_IDENTITY="your_name@email.com"
    python workflow1_sec_extraction.py --input input/company_list.json --output output/

Requirements:
    - edgartools library
    - SEC_IDENTITY environment variable (required by SEC.gov)
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Metric name mappings to XBRL concept names
METRIC_TO_XBRL = {
    "Revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "TotalRevenuesAndOtherIncome",
    ],
    "NetIncome": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ],
    "TotalAssets": [
        "Assets",
    ],
    "OperatingCashFlow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "TotalLiabilities": [
        "Liabilities",
    ],
    "StockholdersEquity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "GrossProfit": [
        "GrossProfit",
    ],
    "OperatingIncome": [
        "OperatingIncomeLoss",
    ],
    "EPS": [
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
    ],
    "SharesOutstanding": [
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
}


def setup_logging(output_dir: Path) -> logging.Logger:
    """Configure logging to file and console."""
    log_file = output_dir / "extraction.log"

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Configure logger
    logger = logging.getLogger("sec_extraction")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def set_sec_identity(logger: logging.Logger) -> bool:
    """Set SEC identity from environment variable."""
    from edgar import set_identity

    identity = os.environ.get("SEC_IDENTITY")
    if not identity:
        # Use a default identity for demonstration
        identity = "SEC_Extraction_Tool contact@example.com"
        logger.warning(f"SEC_IDENTITY not set. Using default: {identity}")

    set_identity(identity)
    logger.info(f"SEC identity set: {identity}")
    return True


def get_company_cik(ticker: str, logger: logging.Logger) -> str | None:
    """Get CIK number for a ticker symbol."""
    from edgar import Company

    try:
        company = Company(ticker)
        cik = company.cik
        logger.info(f"Found CIK for {ticker}: {cik}")
        return cik
    except Exception as e:
        logger.error(f"Failed to get CIK for {ticker}: {e}")
        return None


def get_10k_filing(ticker: str, fiscal_year: int, logger: logging.Logger) -> Any | None:
    """Get the 10-K filing for a company and fiscal year."""
    from edgar import Company

    try:
        company = Company(ticker)
        filings = company.get_filings(form="10-K")

        # Find filing for the target fiscal year
        for filing in filings:
            # Check if filing date is within the fiscal year range
            filing_date = filing.filing_date
            if filing_date.year == fiscal_year or filing_date.year == fiscal_year + 1:
                # Most 10-Ks are filed in Q1 of the following year
                logger.info(f"Found 10-K for {ticker} FY{fiscal_year}: filed {filing_date}")
                return filing

        logger.warning(f"No 10-K found for {ticker} FY{fiscal_year}")
        return None

    except Exception as e:
        logger.error(f"Failed to get 10-K for {ticker}: {e}")
        return None


def extract_metric_from_facts(
    company_facts: dict,
    metric_name: str,
    fiscal_year: int,
    logger: logging.Logger
) -> dict | None:
    """Extract a specific metric from company facts."""

    xbrl_tags = METRIC_TO_XBRL.get(metric_name, [])

    for tag in xbrl_tags:
        # Look in us-gaap namespace
        us_gaap = company_facts.get("facts", {}).get("us-gaap", {})

        if tag in us_gaap:
            concept = us_gaap[tag]
            units = concept.get("units", {})

            # Try USD first, then shares
            for unit_type in ["USD", "shares", "USD/shares"]:
                if unit_type in units:
                    values = units[unit_type]

                    # Find annual value for fiscal year (10-K filing)
                    for entry in values:
                        form = entry.get("form", "")
                        fy = entry.get("fy")
                        fp = entry.get("fp", "")

                        # Match 10-K filing for the fiscal year
                        if form == "10-K" and fy == fiscal_year:
                            logger.debug(
                                f"Found {metric_name} ({tag}): "
                                f"{entry.get('val')} {unit_type} for FY{fiscal_year}"
                            )
                            return {
                                "value": entry.get("val"),
                                "unit": unit_type,
                                "xbrl_tag": f"us-gaap:{tag}",
                                "fiscal_year": fy,
                                "fiscal_period": fp,
                                "filed": entry.get("filed"),
                                "accession": entry.get("accn"),
                            }

    logger.warning(f"Could not find {metric_name} for FY{fiscal_year}")
    return None


def extract_company_financials(
    ticker: str,
    company_name: str,
    fiscal_year: int,
    metrics: list[str],
    logger: logging.Logger
) -> tuple[dict | None, dict | None]:
    """Extract financial metrics for a single company."""
    import requests
    from edgar import Company

    logger.info(f"Processing {ticker} ({company_name}) for FY{fiscal_year}")

    try:
        # Get company info
        company = Company(ticker)
        cik = company.cik
        cik_padded = str(cik).zfill(10)

        # Fetch company facts from SEC API
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
        logger.debug(f"Fetching company facts from: {facts_url}")

        headers = {
            "User-Agent": os.environ.get("SEC_IDENTITY", "SEC_Tool contact@example.com"),
            "Accept-Encoding": "gzip, deflate",
        }

        response = requests.get(facts_url, headers=headers, timeout=30)
        response.raise_for_status()
        company_facts = response.json()

        # Get filing metadata
        filings = company.get_filings(form="10-K")
        filing = None
        for f in filings:
            if f.filing_date.year == fiscal_year or f.filing_date.year == fiscal_year + 1:
                filing = f
                break

        # Extract each metric
        extracted_metrics = {}
        for metric in metrics:
            result = extract_metric_from_facts(company_facts, metric, fiscal_year, logger)
            if result:
                extracted_metrics[metric] = result

        # Build financial data output
        financial_data = {
            "company": company_name,
            "ticker": ticker,
            "cik": cik,
            "fiscal_year": fiscal_year,
            "extraction_timestamp": datetime.now().isoformat(),
            "metrics": {
                name: {
                    "value": data["value"],
                    "unit": data["unit"],
                    "xbrl_tag": data["xbrl_tag"],
                }
                for name, data in extracted_metrics.items()
            },
        }

        # Build filing metadata output
        filing_metadata = {
            "company": company_name,
            "ticker": ticker,
            "cik": cik,
            "fiscal_year": fiscal_year,
            "filing_type": "10-K",
            "company_facts_url": facts_url,
        }

        if filing:
            filing_metadata.update({
                "accession_number": filing.accession_no,
                "filing_date": str(filing.filing_date),
                "filing_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_padded}&type=10-K&dateb=&owner=include&count=40",
            })

        # Add source tags from extracted metrics
        filing_metadata["xbrl_tags_used"] = [
            data["xbrl_tag"] for data in extracted_metrics.values()
        ]

        logger.info(
            f"Successfully extracted {len(extracted_metrics)}/{len(metrics)} "
            f"metrics for {ticker}"
        )

        return financial_data, filing_metadata

    except Exception as e:
        logger.error(f"Failed to extract data for {ticker}: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Extract financial data from SEC EDGAR XBRL filings"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="input/company_list.json",
        help="Path to input JSON file with company list",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/",
        help="Output directory for results",
    )
    args = parser.parse_args()

    # Setup paths
    script_dir = Path(__file__).parent
    input_path = script_dir / args.input
    output_dir = script_dir / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup logging
    logger = setup_logging(output_dir)
    logger.info("=" * 60)
    logger.info("SEC Filing Financial Data Extraction")
    logger.info("=" * 60)
    logger.info(f"Input file: {input_path}")
    logger.info(f"Output directory: {output_dir}")

    # Check edgartools installation
    try:
        import edgar
        logger.info("edgartools loaded successfully")
    except ImportError:
        logger.error("edgartools not installed. Run: pip install edgartools --user")
        sys.exit(1)

    # Set SEC identity
    set_sec_identity(logger)

    # Load input data
    try:
        with open(input_path) as f:
            input_data = json.load(f)
        companies = input_data.get("companies", [])
        logger.info(f"Loaded {len(companies)} companies from input file")
    except FileNotFoundError:
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in input file: {e}")
        sys.exit(1)

    # Process each company
    all_financial_data = []
    all_filing_metadata = []

    for company in companies:
        ticker = company.get("ticker")
        company_name = company.get("company_name", ticker)
        fiscal_year = company.get("fiscal_year")
        metrics = company.get("metrics", ["Revenue", "NetIncome", "TotalAssets"])

        if not ticker or not fiscal_year:
            logger.warning(f"Skipping invalid entry: {company}")
            continue

        financial_data, filing_metadata = extract_company_financials(
            ticker, company_name, fiscal_year, metrics, logger
        )

        if financial_data:
            all_financial_data.append(financial_data)
        if filing_metadata:
            all_filing_metadata.append(filing_metadata)

    # Write output files
    financial_output_path = output_dir / "financial_data.json"
    with open(financial_output_path, "w") as f:
        json.dump(all_financial_data, f, indent=2)
    logger.info(f"Wrote financial data to: {financial_output_path}")

    metadata_output_path = output_dir / "filing_metadata.json"
    with open(metadata_output_path, "w") as f:
        json.dump(all_filing_metadata, f, indent=2)
    logger.info(f"Wrote filing metadata to: {metadata_output_path}")

    # Summary
    logger.info("=" * 60)
    logger.info("Extraction Complete")
    logger.info(f"Companies processed: {len(all_financial_data)}/{len(companies)}")
    logger.info(f"Output files:")
    logger.info(f"  - {financial_output_path}")
    logger.info(f"  - {metadata_output_path}")
    logger.info(f"  - {output_dir / 'extraction.log'}")
    logger.info("=" * 60)

    # Print summary to console
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    for data in all_financial_data:
        print(f"\n{data['ticker']} ({data['company']}) - FY{data['fiscal_year']}")
        for metric, info in data.get("metrics", {}).items():
            value = info["value"]
            unit = info["unit"]
            if unit == "USD" and value >= 1_000_000:
                formatted = f"${value / 1_000_000_000:.2f}B" if value >= 1_000_000_000 else f"${value / 1_000_000:.2f}M"
            else:
                formatted = f"{value:,} {unit}"
            print(f"  {metric}: {formatted} ({info['xbrl_tag']})")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
