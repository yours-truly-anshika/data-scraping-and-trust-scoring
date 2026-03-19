from __future__ import annotations

from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from typing import Any

import requests

from .base import BaseScraper, ScrapeResult

try:
    from Bio import Entrez
except ImportError:  # pragma: no cover
    Entrez = None


class PubMedScraper(BaseScraper):
    def __init__(self, email: str, api_key: str | None = None) -> None:
        self.email = email
        self.api_key = api_key

        if Entrez is not None:
            Entrez.email = self.email
            if self.api_key:
                Entrez.api_key = self.api_key

    def scrape(self, source: str) -> ScrapeResult:
        pubmed_id = str(source)
        if Entrez is not None:
            handle = Entrez.efetch(db="pubmed", id=pubmed_id, rettype="abstract", retmode="xml")
            record = Entrez.read(handle)

            articles = record.get("PubmedArticle", [])
            if not articles:
                raise ValueError(f"No PubMed article found for id: {pubmed_id}")

            article = articles[0]["MedlineCitation"]["Article"]

            title = str(article.get("ArticleTitle", "")).strip()
            abstract = self._extract_abstract(article)
            authors = self._extract_authors(article)
            journal = self._extract_journal(article)
            pub_year = self._extract_pub_year(article)
        else:
            title, authors, journal, abstract, pub_year = self._fetch_via_eutils(pubmed_id)

        metadata = {
            "pubmed_id": pubmed_id,
            "title": title,
            "authors": authors,
            "journal": journal,
            "pub_year": pub_year,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

        chunks = []
        if abstract:
            chunks.append({"chunk_id": 0, "text": abstract})

        return ScrapeResult(
            source_type="pubmed",
            source_id=pubmed_id,
            metadata=metadata,
            content=abstract,
            content_chunks=chunks,
        )

    def _fetch_via_eutils(self, pubmed_id: str) -> tuple[str, list[str], str, str, str]:
        params = {
            "db": "pubmed",
            "id": pubmed_id,
            "retmode": "xml",
            "rettype": "abstract",
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        response = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        article = root.find(".//PubmedArticle/MedlineCitation/Article")
        if article is None:
            raise ValueError(f"No PubMed article found for id: {pubmed_id}")

        title = self._safe_text(article.find("ArticleTitle"))
        journal = self._safe_text(article.find("Journal/Title"))
        pub_year = self._safe_text(article.find("Journal/JournalIssue/PubDate/Year"))
        if not pub_year:
            pub_year = self._safe_text(article.find("Journal/JournalIssue/PubDate/MedlineDate"))

        abstract_parts = [
            (node.text or "").strip()
            for node in article.findall("Abstract/AbstractText")
            if (node.text or "").strip()
        ]
        abstract = " ".join(abstract_parts)

        authors: list[str] = []
        for author in article.findall("AuthorList/Author"):
            fore = self._safe_text(author.find("ForeName"))
            last = self._safe_text(author.find("LastName"))
            collective = self._safe_text(author.find("CollectiveName"))
            name = " ".join(part for part in [fore, last] if part).strip()
            if name:
                authors.append(name)
            elif collective:
                authors.append(collective)

        return title, authors, journal, abstract, pub_year

    @staticmethod
    def _safe_text(node: ET.Element | None) -> str:
        if node is None:
            return ""
        return (node.text or "").strip()

    @staticmethod
    def _extract_abstract(article: dict[str, Any]) -> str:
        abstract = article.get("Abstract", {})
        abstract_text = abstract.get("AbstractText", [])
        if isinstance(abstract_text, str):
            return abstract_text.strip()
        return " ".join(str(part).strip() for part in abstract_text if str(part).strip())

    @staticmethod
    def _extract_authors(article: dict[str, Any]) -> list[str]:
        author_list = article.get("AuthorList", [])
        authors: list[str] = []
        for author in author_list:
            last_name = str(author.get("LastName", "")).strip()
            fore_name = str(author.get("ForeName", "")).strip()
            collective_name = str(author.get("CollectiveName", "")).strip()

            full_name = " ".join(part for part in [fore_name, last_name] if part).strip()
            if full_name:
                authors.append(full_name)
            elif collective_name:
                authors.append(collective_name)
        return authors

    @staticmethod
    def _extract_journal(article: dict[str, Any]) -> str:
        journal = article.get("Journal", {})
        return str(journal.get("Title", "")).strip()

    @staticmethod
    def _extract_pub_year(article: dict[str, Any]) -> str:
        journal = article.get("Journal", {})
        issue = journal.get("JournalIssue", {})
        pub_date = issue.get("PubDate", {})

        year = pub_date.get("Year")
        medline_date = pub_date.get("MedlineDate")

        if year:
            return str(year)
        if medline_date:
            return str(medline_date)
        return ""
