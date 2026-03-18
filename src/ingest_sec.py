import os
import requests
from dotenv import load_dotenv
from src.event import Event
from src.normalize import build_event

load_dotenv()

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "StormDetection contact@example.com")


def fetch_sec_submissions(cik: str, ticker: str) -> list[Event]:
    """Fetch SEC submissions for a company (8-K, 10-Q, 10-K only)."""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    headers = {"User-Agent": SEC_USER_AGENT}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    events = []
    filings = data.get("filings", {}).get("recent", {})
    
    form_types = filings.get("form", [])
    filing_dates = filings.get("filingDate", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    
    for i in range(len(form_types)):
        form_type = form_types[i]
        
        if form_type not in ["8-K", "10-Q", "10-K"]:
            continue
        
        filing_date = filing_dates[i]
        accession = accession_numbers[i].replace("-", "")
        primary_doc = primary_docs[i]
        
        timestamp = filing_date + "T00:00:00Z"
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"
        
        event = build_event(
            timestamp=timestamp,
            source="sec",
            title=f"{ticker} files {form_type}",
            text=f"{ticker} submitted {form_type} filing to SEC",
            url=url,
            reliability=1.0,
            metadata={"cik": cik, "ticker": ticker, "form_type": form_type}
        )
        events.append(event)
    
    return events
