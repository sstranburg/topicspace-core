import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from src.event import Event
from src.normalize import build_event

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")


def fetch_finnhub_company_news(symbol: str, start_date: str, end_date: str) -> list[Event]:
    """Fetch company news from Finnhub API."""
    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": symbol,
        "from": start_date,
        "to": end_date,
        "token": FINNHUB_API_KEY
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    articles = response.json()
    
    events = []
    for article in articles:
        timestamp = datetime.fromtimestamp(article["datetime"]).isoformat() + "Z"
        event = build_event(
            timestamp=timestamp,
            source="finnhub",
            title=article.get("headline", ""),
            text=article.get("summary", ""),
            url=article.get("url"),
            reliability=0.85,
            metadata={"symbol": symbol, "source_actor": symbol, "category": article.get("category")}
        )
        events.append(event)
    
    return events
