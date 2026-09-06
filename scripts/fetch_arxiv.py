# -*- coding: utf-8 -*-
"""从 arXiv API 抓取最近论文元数据。仅依赖标准库。"""

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from config import CATEGORIES, DAYS_BACK, MAX_RESULTS

ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
API_BASE = "https://export.arxiv.org/api/query"

USER_AGENT = "LaylaResearchWorkflow/1.0 (personal research candidate pool)"


def _clean(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _fetch(query: str) -> bytes:
    url = API_BASE + "?" + query
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_recent_papers() -> list:
    search_query = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    query = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": MAX_RESULTS,
        }
    )
    xml_bytes = _fetch(query)
    root = ET.fromstring(xml_bytes)

    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    papers = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        id_url = entry.findtext(f"{{{ATOM_NS}}}id") or ""
        arxiv_id = re.sub(r"v\d+$", "", id_url.rstrip("/").rsplit("/", 1)[-1])
        title = _clean(entry.findtext(f"{{{ATOM_NS}}}title"))
        summary = _clean(entry.findtext(f"{{{ATOM_NS}}}summary"))
        published_raw = entry.findtext(f"{{{ATOM_NS}}}published") or ""
        try:
            published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if published < cutoff:
            continue
        authors = [
            _clean(a.findtext(f"{{{ATOM_NS}}}name"))
            for a in entry.findall(f"{{{ATOM_NS}}}author")
        ]
        pdf_link = ""
        for link in entry.findall(f"{{{ATOM_NS}}}link"):
            if link.get("title") == "pdf":
                pdf_link = link.get("href", "")
                break
        cats = [c.text for c in entry.findall(f"{{{ARXIV_NS}}}category")]
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "published": published.strftime("%Y-%m-%d"),
                "authors": authors,
                "pdf_link": pdf_link,
                "categories": cats,
            }
        )
    return papers


if __name__ == "__main__":
    for p in fetch_recent_papers():
        print(p["published"], p["arxiv_id"], p["title"][:80])
