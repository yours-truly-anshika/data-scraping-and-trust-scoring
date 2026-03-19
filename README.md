# Data Scraping and Trust Scoring

Production-ready modular pipeline for multi-source acquisition (blogs, YouTube, PubMed),
content processing, and transparent trust scoring.

The system uses a weighted normalized algorithm with a baseline year of 2026. YouTube metadata is extracted via HTML scraping to bypass API quota limitations, while transcripts are fetched via the youtube-transcript-api.

## Setup

### 1) Create virtual environment

```powershell
python -m venv .venv
```

If your rubric requires the folder name `venv`, use:

```powershell
python -m venv venv
```

### 2) Activate virtual environment

```powershell
.venv\Scripts\activate
```

```bash
source .venv/bin/activate
```

### 3) Install dependencies

```powershell
pip install -r requirements.txt
```

### 4) Verify installation

```powershell
python -c "import requests, bs4, lxml, youtube_transcript_api, Bio.Entrez, entrezpy, nltk, langdetect; print('OK')"
```

## Pipeline Modules

- `src/scrapers/blog_scraper.py`: Blog scraping using BeautifulSoup with `<article>` targeting and structural cleanup (`<nav>`, `<ads>`, `<footer>`).
- `src/scrapers/youtube_scraper.py`: YouTube scraping with no-key metadata fallback (`<meta>` extraction) plus transcript extraction via `youtube-transcript-api`.
- `src/scrapers/pubmed_scraper.py`: PubMed retrieval via Bio.Entrez when available, with E-utilities fallback.
- `src/utils/chunking.py`: Paragraph-first chunking with 500-1000 char constraints.
- `src/utils/tagging.py`: TF-IDF based top keyword/entity-like topic tags.
- `src/utils/validation.py`: Medical disclaimer boolean detection.
- `src/scoring/trust_score.py`: Transparent weighted trust scoring with abuse-prevention penalties.

## Project Structure

```
data-scraping-and-trust-scoring/
├── data/
│   ├── raw/               # Raw scraped artifacts (git-ignored)
│   └── processed/         # Temporary processing storage
├── output/
│   └── scraped_data.json  # FINAL production output (6 sources)
├── scripts/
│   ├── run_data_acquisition.py   # Data collection runner
│   └── validate_scraped_data.py  # Schema & Trust Score validator
├── src/
│   ├── scrapers/          # Modules for Blog, YouTube, and PubMed
│   ├── scoring/           # TrustScore algorithm & penalty logic
│   └── utils/             # NLP (Tagging, Chunking, Disclaimer detection)
├── tests/
│   └── test_scoring.py    # Unit tests for the scoring engine
├── main.py                # Main Pipeline Orchestrator (Entry Point)
├── README.md              # Setup & Documentation
├── Report.txt             # Technical logic & weighting report
└── requirements.txt       # Project dependencies
```

## Execution

Run the six-source acquisition:

```powershell
python scripts/run_data_acquisition.py
```

Artifacts:

- `data/raw/scraped_data.json`
- `data/raw/acquisition_results.json`

Run CTO-check validation:

```powershell
python scripts/validate_scraped_data.py
```

Validation checks:

- strict record-key schema (no omitted keys)
- `trust_score` numeric float-compatible
- `content_chunks` as array of strings
- transcript-disabled edge-case returns `"Transcript unavailable"`

## Trust Score Formula and Weights

Formal logic:

$$
Trust\ Score = (w_1 \cdot AC) + (w_2 \cdot CC) + (w_3 \cdot DA) + (w_4 \cdot R) + (w_5 \cdot MD)
$$

Default weights used in implementation:

- `AC` (Author Credibility): `0.25`
- `CC` (Citation Count): `0.20`
- `DA` (Domain Authority): `0.20`
- `R` (Recency): `0.20`
- `MD` (Medical Disclaimer): `0.15`

Factor definitions:

- `AC`: `1.0` known org/verified, `0.5` independent, `0.0` anonymous.
- `CC`: log-normalized by `log1p(citation_count) / log1p(max_citation_scale)`.
- `DA`: mock authority map (for example `ncbi.nlm.nih.gov = 1.0`, `blogspot.com = 0.3`).
- `R`: exponential decay from current year baseline (2026).
- `MD`: boolean disclaimer presence score.

Abuse-prevention logic:

- PubMed hard penalty: if `source_type == "pubmed"` and disclaimer is missing, apply `0.5` multiplier.
- Recency cap: if content is older than 5 years, final score is capped at `0.7`.
