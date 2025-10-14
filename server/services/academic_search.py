import requests

def search_openalex_papers(
    keywords: list[str],
    date_range: tuple[str, str] | None = None,
    concepts: list[str] | None = None,
    limit: int = 50
) -> list[dict]:
    """
    Search OpenAlex for papers by keywords (title+abstract), date range, and concepts.
    Only returns papers that have downloadable PDFs.
    """

    base_url = "https://api.openalex.org/works"
    # polite pool: both headers and mailto param
    headers = {
        "User-Agent": "ai-research-companion/1.0 (mailto:2126546982@qq.com)"
    }

    query = " ".join(keywords)

    filters = []
    if date_range:
        start, end = date_range
        filters.append(f"from_publication_date:{start}")
        filters.append(f"to_publication_date:{end}")
    if concepts:
        for cid in concepts:
            filters.append(f"concepts.id:{cid}")
    filters.append("is_oa:true")
    filter_str = ",".join(filters)

    params = {
        "search": query,
        "filter": filter_str,
        "sort": "relevance_score:desc",
        "per_page": limit,
        "mailto": "2126546982@qq.com",  # must include raw @
        "select": (
            "id,display_name,authorships,publication_date,publication_year,"
            "cited_by_count,locations,best_oa_location,abstract_inverted_index,primary_location"
        ),
    }

    # ensure mailto is not encoded
    from urllib.parse import urlencode
    encoded = urlencode(params, doseq=True).replace("%40", "@")
    url = f"{base_url}?{encoded}"

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json().get("results", [])

    papers = []
    for item in data:
        pdf_url = (item.get("best_oa_location") or {}).get("pdf_url")
        if not pdf_url:
            continue

        # reconstruct abstract if present
        summary = ""
        idx = item.get("abstract_inverted_index")
        if idx:
            words = sorted((pos, w) for w, ps in idx.items() for pos in ps)
            summary = " ".join(w for _, w in words).strip()

        authors = [
            a["author"]["display_name"].strip()
            for a in item.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]

        papers.append({
            "id": item.get("id"),
            "title": (item.get("display_name") or "").strip(),
            "authors": authors,
            "summary": summary,
            "publication_date": item.get("publication_date") or str(item.get("publication_year")),
            "source": ((item.get("primary_location") or {}).get("source") or {}).get("display_name", ""),
            "cited_by_count": item.get("cited_by_count", 0),
            "link": item.get("id"),
            "pdf_url": pdf_url
        })

    return papers

