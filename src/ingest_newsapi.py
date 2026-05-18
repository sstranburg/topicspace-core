import os
import requests
from dotenv import load_dotenv
from src.event import Event
from src.normalize import build_event

load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")


def fetch_newsapi_query(
    query: str,
    start_date: str,
    page_size: int = 100,
    source_actors: list[str] | None = None,
    end_date: str | None = None,
) -> list[Event]:
    """Fetch news articles from Event Registry API by query.

    end_date (optional, YYYY-MM-DD): if provided, restrict results to articles
    with publication date ≤ end_date. Necessary for calendar-gap backfills
    where we only want the window, not "from start_date to today."
    """
    url = "https://eventregistry.org/api/v1/article/getArticles"

    payload: dict = {
        "action": "getArticles",
        "keyword": query,
        "articlesPage": 1,
        "articlesCount": min(page_size, 50),  # Limit to avoid rate limits
        "articlesSortBy": "date",
        "dateStart": start_date,
        "lang": "eng",
        "apiKey": NEWSAPI_KEY,
    }
    if end_date:
        payload["dateEnd"] = end_date
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        articles = data.get("articles", {}).get("results", [])
        
        events = []
        for article in articles:
            title = article.get("title", "")
            if not title:
                continue
            
            # Use body snippet if available, otherwise just title
            text = article.get("body", "")[:300] if article.get("body") else ""
            
            # Convert date to ISO format
            date_str = article.get("dateTime", article.get("date", ""))
            if date_str and "T" not in date_str:
                date_str = date_str + "T00:00:00Z"
            elif date_str and not date_str.endswith("Z"):
                date_str = date_str + "Z"
                
            event = build_event(
                timestamp=date_str or start_date + "T00:00:00Z",
                source="newsapi",
                title=title,
                text=text,
                url=article.get("url"),
                reliability=0.75,
                metadata={"source_name": article.get("source", {}).get("title", ""),
                          "source_actors": source_actors or []}
            )
            events.append(event)
        
        return events
        
    except Exception as e:
        print(f"NewsAPI error for query '{query}': {e}")
        return []
