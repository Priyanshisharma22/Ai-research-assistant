from ddgs import DDGS

def web_search(query: str, max_results: int = 3) -> list[dict]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "content": r.get("body", ""),
                "url": r.get("href", ""),
            }
            for r in results
        ]
    except Exception as e:
        return [{"title": "Search error", "content": str(e), "url": ""}]