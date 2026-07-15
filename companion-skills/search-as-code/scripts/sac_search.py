#!/usr/bin/env python3
"""Search-as-Code harness for the Perplexity Search API.

Validates a SearchPlan, optionally injects per-query-type domain filters, batches
compatible queries, calls the Search API, dedupes/ranks results with source-tier
scoring, optionally extracts exact evidence snippets from PDFs/filings, logs
excluded results, and writes JSONL evidence/source/cost ledgers. It can also emit
a standard stock-research plan and import a run into deep-research master ledgers.

Subcommands: validate | run | summarize | costs | template | import
Stdlib-only for the core path; PDF/HTML extraction (run --extract) uses pdftotext
or pypdf when available and degrades gracefully otherwise.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


SEARCH_URL = "https://api.perplexity.ai/search"
DEFAULT_SECRET_FILE = Path.home() / ".claude" / "secrets" / "perplexity.env"
DEFAULT_WINDOWS_CURL = "/mnt/c/Windows/System32/curl.exe"
DR_SCRIPTS_DEFAULT = Path.home() / ".claude" / "skills" / "deep-research" / "scripts"
SEARCH_COST_USD = 0.005
BATCH_SIZE = 5
RUN_LEDGER_FILENAMES = [
    "queries.jsonl",
    "results.jsonl",
    "sources.jsonl",
    "evidence.jsonl",
    "extracted_evidence.jsonl",
    "verified_evidence.jsonl",
    "costs.jsonl",
    "errors.jsonl",
    "exclusion_log.jsonl",
]
REQUEST_PARAM_KEYS = [
    "country",
    "max_results",
    "snippet_mode",
    "search_domain_filter",
    "search_recency_filter",
    "search_after_date_filter",
    "search_before_date_filter",
    "last_updated_after_filter",
    "last_updated_before_filter",
    "max_tokens",
    "max_tokens_per_page",
]
VALID_MODES = {"quick", "standard", "deep", "ultradeep"}
VALID_RECENCY = {"hour", "day", "week", "month", "year"}
VALID_SNIPPET = {"low", "medium", "high"}

# --- Feature #3: source-tier taxonomy (equity / stock research) --------------
# Matching is suffix-based on the result host (so subdomains resolve to the
# registrable parent, e.g. efts.sec.gov -> sec.gov). Each domain appears in
# exactly one tier; tier 1 is most authoritative. Web-verified domains (SEDAR+,
# exchanges) confirmed 2026-06.
SOURCE_TIERS: dict[int, set[str]] = {
    1: {  # PRIMARY / ISSUER / REGULATOR — may anchor material claims
        "sec.gov", "sedarplus.ca", "federalreserve.gov", "treasury.gov",
        "esma.europa.eu", "fca.org.uk", "bankofengland.co.uk", "ema.europa.eu",
        "fda.gov", "clinicaltrials.gov", "uspto.gov", "bis.org", "imf.org",
        "worldbank.org", "oecd.org",
        # exchanges / listing venues
        "nasdaq.com", "nyse.com", "londonstockexchange.com", "lseg.com",
        "tsx.com", "tmx.com", "euronext.com", "asx.com.au", "jpx.co.jp",
        "hkex.com.hk", "nseindia.com", "bseindia.com",
    },
    2: {  # REPUTABLE STRUCTURED / WIRE — trustworthy secondary
        "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com",
        "cnbc.com", "economist.com", "barrons.com", "morningstar.com",
        "spglobal.com", "moodys.com", "fitchratings.com", "factset.com",
        "refinitiv.com", "financialmodelingprep.com",
        # issuer-originated press-release wires
        "globenewswire.com", "businesswire.com", "prnewswire.com", "newswire.ca",
    },
    3: {  # QUALITY ANALYSIS / DISCOVERY — corroborate before relying
        "marketwatch.com", "forbes.com", "businessinsider.com", "axios.com",
        "theinformation.com", "statista.com", "macrotrends.net",
        "stockanalysis.com", "koyfin.com", "tikr.com", "investopedia.com",
    },
    4: {  # HYPOTHESIS-ONLY — never anchor a material claim
        "seekingalpha.com", "fool.com", "benzinga.com", "investorplace.com",
        "zacks.com", "yahoo.com", "thestreet.com", "simplywall.st",
        "gurufocus.com", "tipranks.com", "investing.com", "wallstreetzen.com",
        "marketbeat.com", "reddit.com", "stocktwits.com", "medium.com",
        "substack.com", "youtube.com", "youtu.be", "x.com", "twitter.com",
    },
}
TIER_LABELS = {1: "primary", 2: "high_quality_secondary", 3: "secondary", 4: "low_confidence"}
TIER_SCORE = {1: 45.0, 2: 22.0, 3: 5.0, 4: -30.0}
DEFAULT_TIER = 3
IR_SUBDOMAIN_HINTS = ("ir.", "investor.", "investors.", "investorrelations.")
GOV_SUFFIXES = (".gov", ".mil", ".gov.uk", ".gov.au", ".gc.ca", ".govt.nz",
                ".gov.in", ".gov.sg", ".gov.hk", ".europa.eu")
EDU_SUFFIXES = (".edu", ".ac.uk", ".edu.au", ".ac.jp", ".edu.cn")
# Feature #6: domains dropped outright (low-quality aggregators / spam).
NOISE_DOMAINS = {"ainvest.com", "thecompanycheck.com", "stockstotrade.com"}
NAME_STOPWORDS = {
    "inc", "corp", "ltd", "plc", "llc", "the", "and", "company", "holdings",
    "group", "limited", "incorporated", "corporation", "class", "common",
    "stock", "ord", "ordinary", "shares", "co",
}

# --- Feature #4: domain filters by query type --------------------------------
# Authoritative query types allow only issuer/regulator domains and deny generic
# finance sites; discovery types deny only the noisiest. Values feed the
# Perplexity `search_domain_filter` (deny expressed with a leading "-").
_GENERIC_FINANCE_DENY = [
    "seekingalpha.com", "fool.com", "benzinga.com", "investorplace.com",
    "zacks.com", "yahoo.com", "tipranks.com", "marketbeat.com",
]
QUERY_TYPE_FILTERS: dict[str, dict[str, list[str]]] = {
    "filings": {"allow": ["sec.gov", "sedarplus.ca"], "deny": []},
    "financials": {"allow": ["sec.gov", "sedarplus.ca"], "deny": []},
    "governance": {"allow": ["sec.gov", "sedarplus.ca"], "deny": []},
    "issuer_ir": {"allow": [], "deny": []},
    "results_earnings": {
        "allow": ["sec.gov", "globenewswire.com", "businesswire.com", "prnewswire.com", "newswire.ca"],
        "deny": [],
    },
    "ma": {
        "allow": ["sec.gov", "globenewswire.com", "businesswire.com", "prnewswire.com", "reuters.com", "bloomberg.com"],
        "deny": [],
    },
    "news_catalyst": {
        "allow": ["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com", "cnbc.com"],
        "deny": [],
    },
    "valuation": {"allow": [], "deny": ["fool.com", "benzinga.com", "investorplace.com"]},
    "peers": {"allow": [], "deny": ["fool.com", "benzinga.com"]},
    "bear_case": {"allow": [], "deny": []},
}
VALID_QUERY_TYPES = set(QUERY_TYPE_FILTERS)
ALLOWED_PLAN_KEYS = {
    "topic",
    "mode",
    "output_dir",
    "plan_type",
    "entity",
    "ticker",
    "exchange",
    "sector",
    "issuer_domains",
    "queries",
}
ALLOWED_QUERY_KEYS = {
    "query",
    "purpose",
    "query_type",
    "search_domain_filter",
    "search_recency_filter",
    "search_after_date_filter",
    "search_before_date_filter",
    "last_updated_after_filter",
    "last_updated_before_filter",
    "country",
    "max_results",
    "snippet_mode",
    "max_tokens",
    "max_tokens_per_page",
    "priority",
}

# --- Feature #5: extraction tuning -------------------------------------------
MAX_EXTRACT_CHARS = 1200
MAX_FETCH_BYTES = 5_000_000
PDFTOTEXT_CANDIDATES = (
    str(Path.home() / ".local" / "bin" / "pdftotext"),
    "/usr/local/bin/pdftotext",
    "/usr/bin/pdftotext",
)
LOW_INFORMATION_EXTRACT_PATTERNS = (
    "accessibility statement",
    "skip navigation",
    "client login",
    "send a release",
    "javascript is disabled",
    "enable javascript",
    "verify that you are human",
    "verify that you're not a robot",
    "privacy policy",
    "cookie policy",
    "terms of use",
    "all rights reserved",
    "contact pr newswire",
)


class SearchRequestError(RuntimeError):
    """Search API request failure with the number of billable HTTP attempts made."""

    def __init__(self, message: str, attempts: int = 1) -> None:
        super().__init__(message)
        self.attempts = attempts
NAVIGATION_TOKENS = {
    "about",
    "accessibility",
    "careers",
    "client",
    "contact",
    "cookies",
    "login",
    "navigation",
    "privacy",
    "resources",
    "rss",
    "sitemap",
}
COUNTEREVIDENCE_TERMS = {
    "adverse",
    "bear",
    "challenge",
    "concern",
    "counter",
    "criticism",
    "dispute",
    "failure",
    "limitation",
    "risk",
    "short",
}
OFFICIAL_SOURCE_TERMS = {
    "annual",
    "filing",
    "form",
    "official",
    "primary",
    "prospectus",
    "registry",
    "regulator",
    "sec",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key(secret_file: Path | None = None) -> str:
    if not os.environ.get("PERPLEXITY_API_KEY"):
        env_file = Path(os.environ.get("PERPLEXITY_ENV_FILE") or secret_file or DEFAULT_SECRET_FILE)
        load_env_file(env_file)
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        env_file = Path(os.environ.get("PERPLEXITY_ENV_FILE") or secret_file or DEFAULT_SECRET_FILE)
        raise RuntimeError(f"PERPLEXITY_API_KEY is not set. Define it in the environment or {env_file}.")
    return api_key


def validate_query(query: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(query, dict):
        return [f"queries[{index}] must be an object"]
    unknown = sorted(set(query) - ALLOWED_QUERY_KEYS)
    if unknown:
        errors.append(f"queries[{index}] has unsupported fields: {', '.join(unknown)}")
    if not isinstance(query.get("query"), str) or not query["query"].strip():
        errors.append(f"queries[{index}].query must be a non-empty string")
    if not isinstance(query.get("purpose"), str) or not query["purpose"].strip():
        errors.append(f"queries[{index}].purpose must be a non-empty string")
    max_results = query.get("max_results")
    if max_results is not None and (not isinstance(max_results, int) or not 1 <= max_results <= 20):
        errors.append(f"queries[{index}].max_results must be an integer from 1 to 20")
    priority = query.get("priority")
    if priority is not None and (not isinstance(priority, int) or priority < 1):
        errors.append(f"queries[{index}].priority must be an integer >= 1")
    domains = query.get("search_domain_filter")
    if domains is not None:
        if not isinstance(domains, list) or len(domains) > 20 or not all(isinstance(item, str) and item for item in domains):
            errors.append(f"queries[{index}].search_domain_filter must be 1-20 strings")
        else:
            has_allow = any(not item.startswith("-") for item in domains)
            has_deny = any(item.startswith("-") for item in domains)
            if has_allow and has_deny:
                errors.append(f"queries[{index}].search_domain_filter must use allowlist or denylist mode, not both")
    recency = query.get("search_recency_filter")
    if recency is not None and recency not in VALID_RECENCY:
        errors.append(f"queries[{index}].search_recency_filter is invalid")
    snippet_mode = query.get("snippet_mode")
    if snippet_mode is not None and snippet_mode not in VALID_SNIPPET:
        errors.append(f"queries[{index}].snippet_mode is invalid")
    query_type = query.get("query_type")
    if query_type is not None and not isinstance(query_type, str):
        errors.append(f"queries[{index}].query_type must be a string")
    elif query_type is not None and query_type not in VALID_QUERY_TYPES:
        errors.append(f"queries[{index}].query_type is invalid: {query_type}")
    for key in ("max_tokens", "max_tokens_per_page"):
        value = query.get(key)
        if value is not None and (not isinstance(value, int) or value < 1):
            errors.append(f"queries[{index}].{key} must be an integer >= 1")
    return errors


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["SearchPlan must be an object"]
    unknown = sorted(set(plan) - ALLOWED_PLAN_KEYS)
    if unknown:
        errors.append(f"SearchPlan has unsupported fields: {', '.join(unknown)}")
    if not isinstance(plan.get("topic"), str) or not plan["topic"].strip():
        errors.append("topic must be a non-empty string")
    if plan.get("mode") not in VALID_MODES:
        errors.append(f"mode must be one of {sorted(VALID_MODES)}")
    issuer_domains = plan.get("issuer_domains")
    if issuer_domains is not None and (
        not isinstance(issuer_domains, list) or not all(isinstance(item, str) and item.strip() for item in issuer_domains)
    ):
        errors.append("issuer_domains must be an array of non-empty strings")
    queries = plan.get("queries")
    if not isinstance(queries, list) or not queries:
        errors.append("queries must be a non-empty array")
    else:
        for index, query in enumerate(queries):
            errors.extend(validate_query(query, index))
    return errors


def normalized_query_text(query: str) -> str:
    text = re.sub(r"\s+", " ", query.strip().lower())
    text = re.sub(r"\butm_[a-z0-9_]+:[^\s]+", "", text)
    return text


def verify_plan_quality(plan: dict[str, Any]) -> dict[str, Any]:
    """Return non-fatal plan-quality issues before spending Search API calls."""
    queries = plan.get("queries") if isinstance(plan.get("queries"), list) else []
    issues: list[dict[str, Any]] = []
    seen_queries: dict[str, int] = {}
    duplicate_indices: list[list[int]] = []
    purposes: set[str] = set()

    for index, query in enumerate(queries, start=1):
        text = normalized_query_text(str(query.get("query") or ""))
        if text in seen_queries:
            duplicate_indices.append([seen_queries[text], index])
        else:
            seen_queries[text] = index
        purpose = re.sub(r"\s+", " ", str(query.get("purpose") or "").strip().lower())
        if purpose:
            purposes.add(purpose)

    if duplicate_indices:
        issues.append(
            {
                "severity": "warning",
                "code": "duplicate_queries",
                "pairs": duplicate_indices[:10],
                "message": "SearchPlan contains duplicate normalized query strings.",
            }
        )

    if len(queries) >= 5 and len(purposes) < max(3, len(queries) // 3):
        issues.append(
            {
                "severity": "warning",
                "code": "low_purpose_diversity",
                "purpose_count": len(purposes),
                "query_count": len(queries),
                "message": "Many queries share the same purpose; coverage may be redundant.",
            }
        )

    if plan.get("mode") in {"deep", "ultradeep"}:
        joined = " ".join(
            f"{query.get('query', '')} {query.get('purpose', '')} {query.get('query_type', '')}".lower()
            for query in queries
        )
        if not any(term in joined for term in COUNTEREVIDENCE_TERMS):
            issues.append(
                {
                    "severity": "warning",
                    "code": "missing_counterevidence_lane",
                    "message": "Deep/ultradeep plans should include a bear-case, risk, limitation, or counterevidence lane.",
                }
            )

        has_official_lane = False
        for query in queries:
            query_type = query.get("query_type")
            domains = " ".join(query.get("search_domain_filter") or []).lower()
            query_text = f"{query.get('query', '')} {query.get('purpose', '')} {query_type or ''} {domains}".lower()
            if query_type in {"filings", "financials", "governance", "results_earnings"}:
                has_official_lane = True
            if any(term in query_text for term in OFFICIAL_SOURCE_TERMS) or ".gov" in domains:
                has_official_lane = True
        if not has_official_lane:
            issues.append(
                {
                    "severity": "warning",
                    "code": "missing_official_source_lane",
                    "message": "Deep/ultradeep plans should include an official or primary-source lane.",
                }
            )

    return {
        "status": "warn" if issues else "pass",
        "checked_at": utc_now(),
        "query_count": len(queries),
        "distinct_purpose_count": len(purposes),
        "issues": issues,
    }


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parts.scheme.lower() or "https", netloc, path, query, ""))


def source_id_for(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def registrable_host(url: str) -> str:
    return urlsplit(url).netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")


def tier_for_url(url: str, issuer_domains: list[str] | None = None) -> int:
    """Map a result URL to a source tier (1=primary ... 4=hypothesis-only)."""
    host = registrable_host(url)
    if not host:
        return DEFAULT_TIER
    for domain in issuer_domains or []:
        domain = domain.lower().strip().lstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return 1
    if any(host.startswith(hint) for hint in IR_SUBDOMAIN_HINTS):
        return 1
    for tier in (1, 2, 3, 4):
        for domain in SOURCE_TIERS[tier]:
            if host == domain or host.endswith("." + domain):
                return tier
    if host.endswith(GOV_SUFFIXES):
        return 1
    if host.endswith(EDU_SUFFIXES):
        return 2
    return DEFAULT_TIER


def source_type_for(url: str, tier: int) -> str:
    """Map a URL/tier to a deep-research source_type enum value (for import)."""
    host = registrable_host(url)
    if host == "sec.gov" or host.endswith(".sec.gov"):
        return "sec_filing"
    if host.endswith(GOV_SUFFIXES) or host == "sedarplus.ca" or host.endswith(".sedarplus.ca"):
        return "regulatory"
    if any(host.startswith(hint) for hint in IR_SUBDOMAIN_HINTS):
        return "company_ir"
    if host in {"globenewswire.com", "businesswire.com", "prnewswire.com", "newswire.ca",
                "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com",
                "cnbc.com", "barrons.com", "economist.com"}:
        return "news"
    if host in {"financialmodelingprep.com", "morningstar.com", "spglobal.com",
                "factset.com", "refinitiv.com", "moodys.com", "fitchratings.com"}:
        return "financial_data"
    if tier == 1:
        return "financial_data"
    return "web"


def distinctive_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9]+", str(text).lower()):
        if len(token) < 4 and not (len(token) >= 2 and any(char.isdigit() for char in token)):
            continue
        if token not in NAME_STOPWORDS and token not in seen:
            seen.append(token)
    return seen


def collision_flags(result: dict[str, Any], entity: str | None = None,
                    ticker: str | None = None, exchange: str | None = None) -> list[str]:
    """Feature #6: flag likely wrong-entity / ticker-collision results."""
    flags: list[str] = []
    haystack = f"{result.get('title', '')} {result.get('snippet', '')} {result.get('url', '')}".lower()
    if entity:
        tokens = distinctive_tokens(entity)
        if tokens and not any(token in haystack for token in tokens):
            flags.append("entity_name_absent")
    if ticker:
        ticker_l = ticker.lower().strip()
        if ticker_l and not re.search(r"\b" + re.escape(ticker_l) + r"\b", haystack):
            flags.append("ticker_absent")
    return flags


def request_params(query: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in REQUEST_PARAM_KEYS:
        value = query.get(key)
        if value is not None and value != "":
            params[key] = value
    params.setdefault("max_results", 10)
    params.setdefault("snippet_mode", "high")
    return params


def _normalized_domains(domains: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for domain in domains or []:
        item = str(domain).strip().lower().lstrip(".")
        if not item or item in normalized:
            continue
        normalized.append(item)
    return normalized


def domain_filter_for_query_type(query_type: str, issuer_domains: list[str] | None = None) -> list[str] | None:
    spec = QUERY_TYPE_FILTERS.get(query_type)
    if not spec:
        return None
    dynamic_issuer_domains = _normalized_domains(issuer_domains)
    allow = _normalized_domains(spec.get("allow") or [])
    deny = _normalized_domains(spec.get("deny") or [])
    if query_type in {"filings", "financials", "governance", "results_earnings", "issuer_ir"}:
        allow = [*dynamic_issuer_domains, *[domain for domain in allow if domain not in dynamic_issuer_domains]]
    if allow:
        return allow[:20]
    if deny:
        return [f"-{domain}" for domain in deny[:20]]
    return None


def apply_query_type_filters(
    queries: list[dict[str, Any]], issuer_domains: list[str] | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Feature #4: inject a domain filter for any query that declares a
    query_type and has no explicit search_domain_filter. Returns (queries, count)."""
    out: list[dict[str, Any]] = []
    applied = 0
    for query in queries:
        query = copy.deepcopy(query)
        query_type = query.get("query_type")
        if query_type and not query.get("search_domain_filter"):
            flt = domain_filter_for_query_type(query_type, issuer_domains=issuer_domains)
            if flt:
                query["search_domain_filter"] = flt
                query["_domain_filter_source"] = f"query_type:{query_type}"
                applied += 1
        out.append(query)
    return out, applied


def grouping_key(query: dict[str, Any]) -> str:
    params = request_params(query)
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def build_batches(queries: list[dict[str, Any]], no_batch: bool = False) -> list[dict[str, Any]]:
    """Group compatible queries into Search API requests. When no_batch is set
    (feature #1), every query becomes its own single-query request."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, query in enumerate(queries):
        item = copy.deepcopy(query)
        item["_query_id"] = f"q{index + 1:04d}"
        key = f"__solo_{index:05d}__" if no_batch else grouping_key(query)
        grouped[key].append(item)

    batches: list[dict[str, Any]] = []
    for key in sorted(grouped):
        items = grouped[key]
        for offset in range(0, len(items), BATCH_SIZE):
            chunk = items[offset : offset + BATCH_SIZE]
            params = request_params(chunk[0])
            body = dict(params)
            query_values = [item["query"] for item in chunk]
            body["query"] = query_values[0] if len(query_values) == 1 else query_values
            batches.append({"body": body, "queries": chunk})
    return batches


def cfg_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fetch_search_once(body: dict[str, Any], api_key: str, timeout: float = 60.0) -> dict[str, Any]:
    windows_curl = os.environ.get("PERPLEXITY_WINDOWS_CURL", DEFAULT_WINDOWS_CURL)
    if os.path.exists(windows_curl):
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=True)
        curl_config = (
            f'url = "{cfg_escape(SEARCH_URL)}"\n'
            'request = "POST"\n'
            'header = "Content-Type: application/json"\n'
            'header = "Accept: application/json"\n'
            f'header = "Authorization: Bearer {cfg_escape(api_key)}"\n'
            'header = "User-Agent: claude-search-as-code/1.0"\n'
            f'data-binary = "{cfg_escape(payload)}"\n'
        )
        completed = subprocess.run(
            [
                windows_curl,
                "--silent",
                "--show-error",
                "--fail-with-body",
                "--http1.1",
                "--connect-timeout",
                "15",
                "--max-time",
                str(max(20.0, timeout)),
                "--config",
                "-",
            ],
            input=curl_config,
            text=True,
            capture_output=True,
            timeout=max(25.0, timeout + 5.0),
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()[:500] or f"exit code {completed.returncode}"
            raise RuntimeError(f"Perplexity request failed: {detail}")
        return json.loads(completed.stdout)

    data = json.dumps(body).encode("utf-8")
    request = Request(
        SEARCH_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "claude-search-as-code/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def fetch_search(body: dict[str, Any], api_key: str, timeout: float = 60.0, retries: int = 2) -> dict[str, Any]:
    last_error: Exception | None = None
    attempts = 0
    for attempt in range(retries + 1):
        attempts += 1
        try:
            payload = fetch_search_once(body, api_key, timeout=timeout)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["__sac_http_attempt_count"] = attempts
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            message = str(exc).lower()
            transient = any(
                token in message
                for token in [
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "5xx",
                    "timeout",
                    "timed out",
                    "connection refused",
                    "temporarily unavailable",
                    "retry-after",
                ]
            )
            if attempt >= retries or not transient:
                break
            time.sleep(min(8, 2**attempt))
    assert last_error is not None
    raise SearchRequestError(str(last_error), attempts=attempts) from last_error


def flatten_results(payload: dict[str, Any], batch: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    query_ids = [item["_query_id"] for item in batch["queries"]]
    flattened: list[dict[str, Any]] = []
    has_nested_groups = any(isinstance(item, dict) and isinstance(item.get("results"), list) for item in results)
    if has_nested_groups:
        if len(results) != len(query_ids) or not all(isinstance(item, dict) and isinstance(item.get("results"), list) for item in results):
            raise ValueError(
                f"multi-query grouped response group count {len(results)} does not match query count {len(query_ids)}"
            )
    for index, item in enumerate(results):
        if isinstance(item, dict) and isinstance(item.get("results"), list):
            query_id = query_ids[min(index, len(query_ids) - 1)]
            for nested in item["results"]:
                if isinstance(nested, dict):
                    row = dict(nested)
                    row["_matched_query_ids"] = [query_id]
                    flattened.append(row)
        elif isinstance(item, dict):
            row = dict(item)
            if len(query_ids) == 1:
                row["_matched_query_ids"] = list(query_ids)
            else:
                row["_matched_query_ids"] = []
                row["_batch_attribution_error"] = "flat_multi_query_response"
            flattened.append(row)
    return flattened


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower())}


def score_result(result: dict[str, Any], query_map: dict[str, dict[str, Any]],
                 issuer_domains: list[str] | None = None) -> float:
    title = str(result.get("title") or "")
    snippet = str(result.get("snippet") or "")
    url = str(result.get("url") or "")
    text_tokens = tokenize(f"{title} {snippet} {url}")
    # Feature #3: source-tier weighting replaces the old flat TLD heuristic.
    tier = result.get("tier") or tier_for_url(url, issuer_domains)
    score = TIER_SCORE.get(tier, 5.0)
    if "docs." in registrable_host(url) or "developer" in registrable_host(url):
        score += 6
    if result.get("date") or result.get("last_updated"):
        score += 5
    score += min(len(snippet) / 80.0, 15)
    matched_query_ids = result.get("_matched_query_ids") or []
    for query_id in matched_query_ids:
        purpose = query_map.get(query_id, {}).get("purpose", "")
        query = query_map.get(query_id, {}).get("query", "")
        score += len(text_tokens.intersection(tokenize(f"{purpose} {query}"))) * 1.5
        priority = query_map.get(query_id, {}).get("priority")
        if isinstance(priority, int):
            score += max(0, 6 - min(priority, 6))
    return round(score, 3)


# --- Feature #5: document fetch + exact-snippet extraction --------------------
def _unsafe_ip_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_fetch_url(url: str) -> None:
    parts = urlsplit(str(url).strip())
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"unsafe fetch URL scheme: {parts.scheme or '(missing)'}")
    host = parts.hostname
    if not host:
        raise ValueError("unsafe fetch URL: missing host")
    try:
        if _unsafe_ip_address(host):
            raise ValueError(f"unsafe fetch URL host: {host}")
        return
    except ValueError as exc:
        if "does not appear to be an IPv4 or IPv6 address" not in str(exc):
            raise
    resolved: set[str] = set()
    for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(host, parts.port or None):
        if family in {socket.AF_INET, socket.AF_INET6} and sockaddr:
            resolved.add(str(sockaddr[0]))
    for address in resolved:
        if _unsafe_ip_address(address):
            raise ValueError(f"unsafe fetch URL host resolves to private address: {host} -> {address}")


class SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        validate_fetch_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def find_pdftotext() -> str | None:
    found = shutil.which("pdftotext")
    if found:
        return found
    for candidate in PDFTOTEXT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def fetch_url_bytes(url: str, timeout: float = 30.0) -> tuple[bytes, str, str, int | None]:
    validate_fetch_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; claude-search-as-code/1.0)"}
    try:
        request = Request(url, headers=headers)
        opener = build_opener(SafeRedirectHandler)
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
            final_url = response.geturl()
            validate_fetch_url(final_url)
            content_type = response.headers.get("Content-Type", "")
            return response.read(MAX_FETCH_BYTES), content_type, final_url, getattr(response, "status", None)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        windows_curl = os.environ.get("PERPLEXITY_WINDOWS_CURL", DEFAULT_WINDOWS_CURL)
        if os.path.exists(windows_curl):
            completed = subprocess.run(
                [windows_curl, "--silent", "--show-error",
                 "--connect-timeout", "15", "--max-time", str(max(20.0, timeout)),
                 "--max-filesize", str(MAX_FETCH_BYTES),
                 "--proto", "=http,https",
                 "-A", "Mozilla/5.0 (compatible; claude-search-as-code/1.0)",
                 "--output", "-", url],
                capture_output=True, timeout=max(25.0, timeout + 5.0), check=False,
            )
            if completed.returncode == 0 and completed.stdout:
                return completed.stdout, "", url, None
        raise


def pdf_bytes_to_text(payload: bytes) -> str:
    pdftotext_bin = find_pdftotext()
    if pdftotext_bin is not None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "source.pdf"
            txt_path = Path(tmp) / "source.txt"
            pdf_path.write_bytes(payload)
            completed = subprocess.run(
                [pdftotext_bin, "-layout", str(pdf_path), str(txt_path)],
                capture_output=True, text=True, check=False, timeout=45,
            )
            if completed.returncode == 0 and txt_path.exists():
                return txt_path.read_text(encoding="utf-8", errors="replace")
    try:  # fallback: pypdf (present in this env), form-feed page separators
        import io

        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(payload))
        return "\f".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"pdf extraction unavailable: {exc}") from exc


_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def html_bytes_to_text(payload: bytes) -> str:
    import html as html_module

    text = payload.decode("utf-8", errors="replace")
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return html_module.unescape(text)


def extract_text_from_url(url: str, timeout: float = 30.0) -> dict[str, Any]:
    payload, content_type, final_url, status_code = fetch_url_bytes(url, timeout=timeout)
    path = urlsplit(url).path.lower()
    is_pdf = "pdf" in content_type.lower() or path.endswith(".pdf") or payload[:5] == b"%PDF-"
    if is_pdf:
        text = pdf_bytes_to_text(payload)
        pages = text.split("\f") if "\f" in text else [text]
        return {
            "text": text,
            "pages": pages,
            "method": "pdf",
            "content_type": content_type,
            "final_url": final_url,
            "status_code": status_code,
        }
    text = html_bytes_to_text(payload)
    return {
        "text": text,
        "pages": None,
        "method": "html",
        "content_type": content_type,
        "final_url": final_url,
        "status_code": status_code,
    }


def choose_extract_snippet(text: str, keywords: list[str], pages: list[str] | None = None) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return {"snippet": "", "locator": "no_text"}
    lower = compact.lower()
    best = -1
    best_keyword = ""
    for keyword in keywords:
        idx = lower.find(keyword)
        if idx >= 0 and (best < 0 or idx < best):
            best = idx
            best_keyword = keyword
    offset = max(0, best - 200) if best >= 0 else 0
    snippet = compact[offset : offset + MAX_EXTRACT_CHARS].strip()
    span_end = offset + len(snippet)
    if pages and len(pages) > 1:
        cumulative = 0
        page_num = 1
        for number, page_text in enumerate(pages, 1):
            cumulative += len(re.sub(r"\s+", " ", page_text).strip()) + 1
            page_num = number
            if cumulative >= offset:
                break
        locator = f"page:{page_num}"
    else:
        locator = f"char_span:{offset}-{span_end}"
    return {
        "snippet": snippet,
        "locator": locator,
        "span_start": offset,
        "span_end": span_end,
        "matched_keyword": best_keyword,
        "text_normalization": "whitespace_compacted",
    }


def is_low_information_extract(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip().lower()
    if not compact:
        return True
    if len(compact) < 40:
        return True
    if any(pattern in compact for pattern in LOW_INFORMATION_EXTRACT_PATTERNS):
        return True
    tokens = re.findall(r"[a-z]{3,}", compact[:800])
    if len(tokens) < 12:
        return True
    nav_hits = sum(1 for token in tokens if token in NAVIGATION_TOKENS)
    return nav_hits >= 6 and nav_hits / max(len(tokens), 1) > 0.2


def extract_one_verified_evidence(
    row: dict[str, Any],
    query_map: dict[str, dict[str, Any]],
    entity: str | None,
    started_at: str,
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Fetch one source and return either an extracted evidence row or an exclusion row."""
    url = str(row.get("url") or "")
    if not url:
        return None, None
    try:
        document = extract_text_from_url(url, timeout=timeout)
        text = document.get("text") or ""
        if not text.strip():
            raise RuntimeError("no extractable text (paywall or JS-rendered page)")
        keyword_source = " ".join(
            [row.get("title") or "", entity or ""]
            + [query_map.get(q, {}).get("query", "") for q in (row.get("_matched_query_ids") or [])]
        )
        picked = choose_extract_snippet(text, distinctive_tokens(keyword_source), document.get("pages"))
        if not picked["snippet"]:
            raise RuntimeError("no snippet extracted")
        if is_low_information_extract(picked["snippet"]):
            return None, {
                "source_id": row.get("source_id"),
                "url": url,
                "title": row.get("title") or "",
                "source_tier": row.get("source_tier"),
                "hypothesis_only": row.get("hypothesis_only", False),
                "exclude_reason": "low_information_extract",
                "excluded_at": utc_now(),
            }
        evidence_row = {
            "source_id": row["source_id"],
            "source_url": url,
            "source_title": row.get("title") or "",
            "evidence_quote": picked["snippet"],
            "evidence_type": "extracted_quote",
            "locator": picked["locator"],
            "span_start": picked.get("span_start"),
            "span_end": picked.get("span_end"),
            "matched_keyword": picked.get("matched_keyword"),
            "text_normalization": picked.get("text_normalization"),
            "extraction_method": document.get("method"),
            "content_type": document.get("content_type"),
            "final_url": document.get("final_url") or url,
            "status_code": document.get("status_code"),
            "tier": row.get("tier"),
            "source_tier": row.get("source_tier"),
            "hypothesis_only": row.get("hypothesis_only", False),
            "matched_query_ids": row.get("_matched_query_ids") or [],
            "retrieved_at": started_at,
            "confidence": 0.8,
            "confidence_basis": "fetch_plus_keyword_proximity",
            "provenance_verified": True,
            "relevance_verified": False,
        }
        return evidence_row, None
    except Exception as exc:  # noqa: BLE001
        return None, {
            "source_id": row.get("source_id"),
            "url": url,
            "title": row.get("title") or "",
            "source_tier": row.get("source_tier"),
            "hypothesis_only": row.get("hypothesis_only", False),
            "exclude_reason": f"extract_failed:{str(exc)[:200]}",
            "excluded_at": utc_now(),
        }


def extract_verified_evidence(rows: list[dict[str, Any]], query_map: dict[str, dict[str, Any]],
                              entity: str | None, started_at: str, max_sources: int,
                              timeout: float, extract_concurrency: int = 4) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch top sources, extract exact snippets + locators, and return
    (evidence_rows, exclusion_rows)."""
    evidence: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    ranked = sorted(rows, key=lambda item: (item.get("tier", DEFAULT_TIER), -float(item.get("score", 0))))
    selected = ranked[: max(0, max_sources)]
    if not selected:
        return evidence, failures

    max_workers = max(1, min(int(extract_concurrency or 1), len(selected)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(extract_one_verified_evidence, row, query_map, entity, started_at, timeout)
            for row in selected
        ]
        for future in concurrent.futures.as_completed(futures):
            evidence_row, failure_row = future.result()
            if evidence_row:
                evidence.append(evidence_row)
            if failure_row:
                failures.append(failure_row)
    return evidence, failures


def source_host(row: dict[str, Any]) -> str:
    url = str(row.get("canonical_url") or row.get("url") or row.get("source_url") or "")
    return urlsplit(url).netloc.lower().removeprefix("www.")


def evidence_quote(row: dict[str, Any]) -> str:
    return str(row.get("evidence_quote") or row.get("quote") or row.get("evidence_quote_or_span") or "").strip()


def diagnose_coverage(
    plan: dict[str, Any],
    source_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    exclusion_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    tiers = Counter(str(row.get("source_tier") or "unknown") for row in source_rows)
    hosts = Counter(host for host in (source_host(row) for row in source_rows) if host)
    exclusion_reasons = Counter(str(row.get("exclude_reason") or "unknown") for row in exclusion_rows)
    low_info_evidence = [row for row in evidence_rows if is_low_information_extract(evidence_quote(row))]
    issues: list[dict[str, Any]] = []
    mode = plan.get("mode")

    if not source_rows:
        issues.append({"severity": "critical", "code": "no_retained_sources", "message": "No sources survived dedupe/classification."})
    if not evidence_rows:
        issues.append({"severity": "critical", "code": "no_evidence_rows", "message": "No evidence snippets or extracts were captured."})
    if mode in {"deep", "ultradeep"} and not any(tier in tiers for tier in ("primary", "high_quality_secondary")):
        issues.append(
            {
                "severity": "warning",
                "code": "no_primary_or_official_sources",
                "message": "Deep/ultradeep discovery retained no primary or high-quality official/issuer sources.",
            }
        )

    unknown_count = tiers.get("unknown", 0)
    if len(source_rows) >= 5 and unknown_count / len(source_rows) > 0.5:
        issues.append(
            {
                "severity": "warning",
                "code": "high_unknown_source_tier_ratio",
                "ratio": round(unknown_count / len(source_rows), 3),
                "message": "Most retained sources have unknown source_tier.",
            }
        )

    if len(source_rows) >= 5 and hosts:
        host, count = hosts.most_common(1)[0]
        if count / len(source_rows) > 0.5:
            issues.append(
                {
                    "severity": "warning",
                    "code": "domain_concentration",
                    "host": host,
                    "ratio": round(count / len(source_rows), 3),
                    "message": "Retained sources are concentrated in one domain.",
                }
            )

    low_info_extract_failures = exclusion_reasons.get("low_information_extract", 0)
    if low_info_extract_failures:
        issues.append(
            {
                "severity": "warning",
                "code": "low_information_extract_failures",
                "count": low_info_extract_failures,
                "message": "Some fetched sources yielded navigation, bot-check, or boilerplate extracts.",
            }
        )
    if low_info_evidence:
        issues.append(
            {
                "severity": "warning",
                "code": "low_information_evidence_rows",
                "count": len(low_info_evidence),
                "message": "Some retained evidence rows look low-information.",
            }
        )

    return {
        "status": "warn" if issues else "pass",
        "checked_at": utc_now(),
        "counts": {
            "retained_sources": len(source_rows),
            "evidence_rows": len(evidence_rows),
            "excluded_results": len(exclusion_rows),
            "low_information_evidence_rows": len(low_info_evidence),
        },
        "source_tiers": dict(tiers),
        "top_domains": dict(hosts.most_common(10)),
        "exclusion_reasons": dict(exclusion_reasons),
        "issues": issues,
    }


def build_delta_plan(plan: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any] | None:
    issues = diagnostics.get("issues") or []
    plan_quality_issues = diagnostics.get("plan_quality_issues") or []
    issue_codes = {issue.get("code") for issue in [*issues, *plan_quality_issues]}
    if not issue_codes:
        return None

    topic = str(plan.get("topic") or "research topic").strip()
    mode = plan.get("mode") if plan.get("mode") in VALID_MODES else "standard"
    queries: list[dict[str, Any]] = []

    if issue_codes & {"missing_official_source_lane", "no_primary_or_official_sources", "no_retained_sources"}:
        queries.append(
            {
                "query": f"{topic} official primary source filing regulator report",
                "purpose": "Delta retrieval for official or primary-source evidence missing from the first pass.",
                "query_type": "filings",
                "max_results": 10,
                "snippet_mode": "high",
                "priority": 1,
            }
        )

    if issue_codes & {"missing_counterevidence_lane"}:
        queries.append(
            {
                "query": f"{topic} risks limitations criticism bear case counterevidence",
                "purpose": "Delta retrieval for counterevidence, limitations, failure modes, and bear-case sources.",
                "query_type": "bear_case",
                "max_results": 10,
                "snippet_mode": "high",
                "priority": 2,
            }
        )

    if issue_codes & {"low_information_extract_failures", "low_information_evidence_rows", "no_evidence_rows"}:
        queries.append(
            {
                "query": f"{topic} PDF report data facts exact source",
                "purpose": "Delta retrieval for extractable source text with substantive facts rather than navigation boilerplate.",
                "max_results": 10,
                "snippet_mode": "high",
                "priority": 3,
            }
        )

    if issue_codes & {"domain_concentration", "high_unknown_source_tier_ratio", "low_purpose_diversity", "duplicate_queries"}:
        queries.append(
            {
                "query": f"{topic} independent analysis comparison evidence",
                "purpose": "Delta retrieval for independent source diversity.",
                "max_results": 10,
                "snippet_mode": "high",
                "priority": 4,
            }
        )

    if not queries:
        return None

    existing = {normalized_query_text(str(query.get("query") or "")) for query in plan.get("queries", [])}
    unique_queries = []
    for query in queries:
        normalized = normalized_query_text(query["query"])
        if normalized not in existing:
            unique_queries.append(query)
            existing.add(normalized)

    if not unique_queries:
        return None

    return {
        "topic": f"{topic} delta retrieval",
        "mode": mode,
        "queries": unique_queries,
    }


def run_batch(batch: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    started = time.time()
    payload = fetch_search(batch["body"], api_key, timeout=timeout)
    attempt_count = 1
    if isinstance(payload, dict):
        attempt_count = int(payload.pop("__sac_http_attempt_count", 1) or 1)
    return {
        "batch": batch,
        "payload": payload,
        "duration_ms": int((time.time() - started) * 1000),
        "http_attempt_count": attempt_count,
    }


def run_plan(plan: dict[str, Any], out_dir: Path, concurrency: int, timeout: float,
             no_batch: bool = True, extract: bool = False, extract_max_sources: int = 8) -> None:
    errors = validate_plan(plan)
    if errors:
        raise ValueError("Invalid SearchPlan:\n" + "\n".join(f"- {error}" for error in errors))

    api_key = get_api_key()
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in RUN_LEDGER_FILENAMES:
        path = out_dir / filename
        if not path.exists():
            path.touch()

    entity = plan.get("entity") or None
    ticker = plan.get("ticker") or None
    exchange = plan.get("exchange") or None
    issuer_domains = plan.get("issuer_domains") or []

    # Feature #4: inject per-query-type domain filters, then batch (#1).
    prepared_queries, filters_applied = apply_query_type_filters(plan["queries"], issuer_domains=issuer_domains)
    batches = build_batches(prepared_queries, no_batch=no_batch)
    query_map = {item["_query_id"]: item for batch in batches for item in batch["queries"]}
    started_at = utc_now()
    plan_quality = verify_plan_quality({**plan, "queries": prepared_queries})
    write_json(out_dir / "search_plan.json", plan)
    write_json(out_dir / "plan_quality.json", plan_quality)
    manifest = {
        "topic": plan["topic"],
        "mode": plan["mode"],
        "started_at": started_at,
        "provider": "perplexity-search-api",
        "batching": "disabled" if no_batch else "enabled",
        "no_batch": bool(no_batch),
        "batch_size": 1 if no_batch else BATCH_SIZE,
        "concurrency": concurrency,
        "extract": bool(extract),
        "query_type_filters_applied": filters_applied,
        "entity": entity,
        "ticker": ticker,
        "exchange": exchange,
        "logical_query_count": len(plan["queries"]),
        "http_request_count": len(batches),
    }
    append_jsonl(out_dir / "queries.jsonl", list(query_map.values()))

    raw_results: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = {executor.submit(run_batch, batch, api_key, timeout): batch for batch in batches}
        for future in concurrent.futures.as_completed(futures):
            batch = futures[future]
            query_ids = [item["_query_id"] for item in batch["queries"]]
            request_id = hashlib.sha256(json.dumps(batch["body"], sort_keys=True).encode("utf-8")).hexdigest()[:12]
            try:
                result = future.result()
                rows = flatten_results(result["payload"], batch)
            except Exception as exc:  # noqa: BLE001
                error_rows.append(
                    {
                        "request_id": request_id,
                        "query_ids": query_ids,
                        "logical_query_count": len(query_ids),
                        "http_request_count": 1,
                        "http_attempt_count": int(getattr(exc, "attempts", 1) or 1),
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                        "recorded_at": utc_now(),
                    }
                )
                continue
            attribution_errors = sorted(
                {
                    str(row.get("_batch_attribution_error"))
                    for row in rows
                    if row.get("_batch_attribution_error")
                }
            )
            for attribution_error in attribution_errors:
                error_rows.append(
                    {
                        "request_id": request_id,
                        "query_ids": query_ids,
                        "logical_query_count": len(query_ids),
                        "http_request_count": 0,
                        "http_attempt_count": 0,
                        "error_type": "BatchAttributionWarning",
                        "error": attribution_error,
                        "recorded_at": utc_now(),
                    }
                )
            raw_results.extend(rows)
            cost_rows.append(
                {
                    "request_id": request_id,
                    "query_ids": query_ids,
                    "logical_query_count": len(query_ids),
                    "http_request_count": 1,
                    "http_attempt_count": int(result.get("http_attempt_count", 1) or 1),
                    "estimated_cost_usd": SEARCH_COST_USD,
                    "duration_ms": result["duration_ms"],
                    "recorded_at": utc_now(),
                }
            )

    deduped: dict[str, dict[str, Any]] = {}
    for row in raw_results:
        url = str(row.get("url") or "")
        if not url:
            continue
        canon = canonical_url(url)
        existing = deduped.get(canon)
        matched = set(row.get("_matched_query_ids") or [])
        if existing:
            matched.update(existing.get("_matched_query_ids") or [])
            existing["_matched_query_ids"] = sorted(matched)
            if len(str(row.get("snippet") or "")) > len(str(existing.get("snippet") or "")):
                for key in ["title", "snippet", "date", "last_updated"]:
                    if row.get(key):
                        existing[key] = row[key]
        else:
            copied = dict(row)
            copied["canonical_url"] = canon
            copied["source_id"] = source_id_for(canon)
            copied["_matched_query_ids"] = sorted(matched)
            deduped[canon] = copied

    result_rows = list(deduped.values())
    for row in result_rows:
        row["tier"] = tier_for_url(str(row.get("url") or ""), issuer_domains)
        row["source_tier"] = TIER_LABELS.get(row["tier"], "secondary")
        row["hypothesis_only"] = row["tier"] >= 4
        row["score"] = score_result(row, query_map, issuer_domains)
    result_rows.sort(key=lambda item: item.get("score", 0), reverse=True)

    # Feature #6: partition out noise domains and ticker-collision results.
    kept_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    for row in result_rows:
        host = registrable_host(str(row.get("url") or ""))
        reason = None
        if host in NOISE_DOMAINS:
            reason = "noise_domain"
        elif entity or ticker:
            flags = collision_flags(row, entity, ticker, exchange)
            if flags:
                row["collision_flags"] = flags
            if "entity_name_absent" in flags and "ticker_absent" in flags and row.get("tier", DEFAULT_TIER) >= 3:
                reason = "ticker_collision:entity_and_ticker_absent"
        if reason:
            excluded = dict(row)
            excluded["exclude_reason"] = reason
            excluded["excluded_at"] = utc_now()
            excluded_rows.append(excluded)
        else:
            kept_rows.append(row)

    source_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(kept_rows, 1):
        source_rows.append({
            "source_id": row["source_id"],
            "rank": rank,
            "url": row.get("url"),
            "canonical_url": row.get("canonical_url"),
            "title": row.get("title") or "",
            "tier": row.get("tier"),
            "source_tier": row.get("source_tier"),
            "hypothesis_only": row.get("hypothesis_only", False),
            "date": row.get("date"),
            "last_updated": row.get("last_updated"),
            "matched_query_ids": row.get("_matched_query_ids") or [],
            "score": row.get("score"),
            "retrieved_at": started_at,
        })
        snippet = str(row.get("snippet") or "").strip()
        if snippet:
            evidence_rows.append({
                "source_id": row["source_id"],
                "source_url": row.get("url"),
                "source_title": row.get("title") or "",
                "evidence_quote": snippet,
                "evidence_type": "search_snippet",
                "locator": "Perplexity Search API snippet",
                "source_tier": row.get("source_tier"),
                "hypothesis_only": row.get("hypothesis_only", False),
                "matched_query_ids": row.get("_matched_query_ids") or [],
                "retrieved_at": started_at,
                "confidence": 0.55,
            })

    # Feature #5: fetch top sources and store exact extracted snippets.
    if extract and kept_rows:
        extracted, extract_failures = extract_verified_evidence(
            kept_rows, query_map, entity, started_at, extract_max_sources, timeout,
            extract_concurrency=max(1, min(concurrency, extract_max_sources)),
        )
        evidence_rows.extend(extracted)
        excluded_rows.extend(extract_failures)

    append_jsonl(out_dir / "results.jsonl", kept_rows)
    append_jsonl(out_dir / "sources.jsonl", source_rows)
    append_jsonl(out_dir / "evidence.jsonl", evidence_rows)
    if extract:
        extracted_rows = [row for row in evidence_rows if row.get("evidence_type") == "extracted_quote"]
        append_jsonl(out_dir / "extracted_evidence.jsonl", extracted_rows)
        append_jsonl(out_dir / "verified_evidence.jsonl", extracted_rows)
    append_jsonl(out_dir / "costs.jsonl", sorted(cost_rows, key=lambda item: item["request_id"]))
    append_jsonl(out_dir / "errors.jsonl", sorted(error_rows, key=lambda item: item["request_id"]))
    append_jsonl(out_dir / "exclusion_log.jsonl", excluded_rows)
    diagnostics = diagnose_coverage({**plan, "queries": prepared_queries}, source_rows, evidence_rows, excluded_rows)
    diagnostics["plan_quality_issues"] = plan_quality.get("issues") or []
    diagnostics["batch_errors"] = error_rows
    if diagnostics["plan_quality_issues"] and diagnostics["status"] == "pass":
        diagnostics["status"] = "warn"
    if error_rows and diagnostics["status"] == "pass":
        diagnostics["status"] = "warn"
    write_json(out_dir / "coverage_diagnostics.json", diagnostics)
    delta_plan = build_delta_plan({**plan, "queries": prepared_queries}, diagnostics)
    if delta_plan:
        write_json(out_dir / "delta_search_plan.json", delta_plan)
    manifest["successful_http_request_count"] = len(cost_rows)
    manifest["failed_http_request_count"] = len(error_rows)
    manifest["http_attempt_count"] = sum(int(row.get("http_attempt_count", 1)) for row in [*cost_rows, *error_rows])
    manifest["estimated_cost_usd"] = round(sum(float(row["estimated_cost_usd"]) for row in cost_rows), 6)
    manifest["worst_case_logical_query_cost_usd"] = round(len(plan["queries"]) * SEARCH_COST_USD, 6)
    write_json(out_dir / "run_manifest.json", manifest)
    write_coverage_summary(out_dir, plan, kept_rows, cost_rows, len(excluded_rows))


def write_coverage_summary(out_dir: Path, plan: dict[str, Any], results: list[dict[str, Any]],
                           costs: list[dict[str, Any]], excluded_count: int = 0) -> None:
    hosts = Counter(urlsplit(str(row.get("canonical_url") or row.get("url") or "")).netloc for row in results)
    tiers = Counter(row.get("source_tier", "secondary") for row in results)
    total_cost = sum(float(row["estimated_cost_usd"]) for row in costs)
    lines = [
        f"# Coverage Summary: {plan['topic']}",
        "",
        f"- Mode: {plan['mode']}",
        f"- Logical queries: {len(plan['queries'])}",
        f"- HTTP requests: {len(costs)}",
        f"- Unique sources kept: {len(results)}",
        f"- Excluded results: {excluded_count}",
        f"- Estimated Search API cost: ${total_cost:.4f}",
        "",
        "## Source Tiers",
    ]
    for label in ("primary", "high_quality_secondary", "secondary", "low_confidence"):
        if tiers.get(label):
            lines.append(f"- {label}: {tiers[label]}")
    lines.extend(["", "## Top Sources"])
    for row in results[:20]:
        marker = " [hypothesis-only]" if row.get("hypothesis_only") else ""
        lines.append(f"- [{row.get('score')}] ({row.get('source_tier')}){marker} {row.get('title') or '(untitled)'} - {row.get('url')}")
    lines.extend(["", "## Top Domains"])
    for host, count in hosts.most_common(15):
        if host:
            lines.append(f"- {host}: {count}")
    lines.append("")
    (out_dir / "coverage_summary.md").write_text("\n".join(lines), encoding="utf-8")


def summarize_run(run_dir: Path) -> None:
    summary = run_dir / "coverage_summary.md"
    if not summary.exists():
        raise RuntimeError(f"coverage_summary.md not found in {run_dir}")
    sys.stdout.write(summary.read_text(encoding="utf-8"))


def print_costs(run_dir: Path) -> None:
    path = run_dir / "costs.jsonl"
    if not path.exists():
        raise RuntimeError(f"costs.jsonl not found in {run_dir}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {
        "http_request_count": sum(int(row.get("http_request_count", 0)) for row in rows),
        "logical_query_count": sum(int(row.get("logical_query_count", 0)) for row in rows),
        "estimated_cost_usd": round(sum(float(row.get("estimated_cost_usd", 0)) for row in rows), 6),
    }
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# --- Feature #2: import a run into deep-research master ledgers ---------------
def _run_dr(script: Path, args_list: list[str]) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args_list], capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"{script.name} failed: {detail}")
    return completed.stdout.strip()


def _batch_count(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    return 0


def merge_into_project(run_dir: Path, dst_dir: Path, dr_scripts: Path = DR_SCRIPTS_DEFAULT) -> dict[str, Any]:
    """Merge a Search-as-Code run's sources/evidence into a deep-research project
    by re-registering through citation_manager.py / evidence_store.py, which gives
    stable deduped source IDs and remaps evidence to those IDs."""
    citation_manager = Path(dr_scripts) / "citation_manager.py"
    evidence_store = Path(dr_scripts) / "evidence_store.py"
    if not citation_manager.exists() or not evidence_store.exists():
        raise RuntimeError(f"deep-research scripts not found in {dr_scripts}")
    run_dir = Path(run_dir)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not (dst_dir / "run_manifest.json").exists() or not (dst_dir / "sources.jsonl").exists():
        topic = "search-as-code import"
        mode = "standard"
        manifest = run_dir / "run_manifest.json"
        if manifest.exists():
            data = read_json(manifest)
            topic = data.get("topic", topic)
            mode = data.get("mode", "standard")
        _run_dr(citation_manager, ["init-run", "--out-dir", str(dst_dir),
                                   "--query", topic, "--mode", mode if mode in VALID_MODES else "standard"])
    if not (dst_dir / "evidence.jsonl").exists():
        _run_dr(evidence_store, ["init", "--dir", str(dst_dir)])

    source_rows = read_jsonl(run_dir / "sources.jsonl")
    source_payloads: list[dict[str, Any]] = []
    source_original_ids: list[str | None] = []
    for row in source_rows:
        url = row.get("url") or row.get("raw_url")
        if not url:
            continue
        tier = row.get("tier") or tier_for_url(url)
        source_original_ids.append(row.get("source_id"))
        source_payloads.append({
            "raw_url": url,
            "title": row.get("title") or "",
            "source_type": source_type_for(url, tier),
            "metadata_status": "unverified",
        })
        if row.get("date"):
            source_payloads[-1]["document_date"] = row["date"]
        if row.get("retrieved_at"):
            source_payloads[-1]["retrieved_at"] = row["retrieved_at"]
        label = TIER_LABELS.get(tier)
        if label:
            source_payloads[-1]["source_tier"] = label

    id_map: dict[str, str] = {}
    sources_added = sources_duplicate = 0
    source_errors: list[dict[str, Any]] = []
    if source_payloads:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as handle:
            source_jsonl = Path(handle.name)
            for payload in source_payloads:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        try:
            response = json.loads(_run_dr(citation_manager, ["register-sources", "--jsonl", str(source_jsonl), "--dir", str(dst_dir)]))
        finally:
            source_jsonl.unlink(missing_ok=True)
        returned_ids = response.get("source_ids") if isinstance(response.get("source_ids"), list) else []
        for original_id, dr_source_id in zip(source_original_ids, returned_ids):
            if original_id and dr_source_id:
                id_map[original_id] = dr_source_id
        sources_added = int(response.get("registered", 0) or 0)
        sources_duplicate = _batch_count(response.get("duplicates"))
        source_errors = response.get("errors") if isinstance(response.get("errors"), list) else []

    if len(id_map) < len([source_id for source_id in source_original_ids if source_id]):
        dst_sources = read_jsonl(dst_dir / "sources.jsonl")
        by_raw_url = {row.get("raw_url"): row.get("source_id") for row in dst_sources if row.get("raw_url") and row.get("source_id")}
        for original_id, payload in zip(source_original_ids, source_payloads):
            if original_id and original_id not in id_map and by_raw_url.get(payload.get("raw_url")):
                id_map[original_id] = by_raw_url[payload.get("raw_url")]

    evidence_added = evidence_duplicate = evidence_skipped = 0
    evidence_payloads: list[dict[str, Any]] = []
    for row in read_jsonl(run_dir / "evidence.jsonl"):
        dr_source_id = id_map.get(row.get("source_id"))
        if not dr_source_id:
            evidence_skipped += 1
            continue
        quote = row.get("evidence_quote") or row.get("quote") or ""
        if not quote:
            evidence_skipped += 1
            continue
        evidence_type = {
            "extracted_quote": "direct_quote",
            "search_snippet": "paraphrase",
            "direct_quote": "direct_quote",
            "paraphrase": "paraphrase",
            "data_point": "data_point",
            "figure_reference": "figure_reference",
            "methodology": "methodology",
        }.get(row.get("evidence_type"), "direct_quote")
        payload = {"source_id": dr_source_id, "quote": quote, "evidence_type": evidence_type}
        if row.get("locator"):
            payload["locator"] = row["locator"]
        evidence_payloads.append(payload)

    evidence_errors: list[dict[str, Any]] = []
    if evidence_payloads:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as handle:
            evidence_jsonl = Path(handle.name)
            for payload in evidence_payloads:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        try:
            response = json.loads(_run_dr(evidence_store, ["add-batch", "--jsonl", str(evidence_jsonl), "--dir", str(dst_dir)]))
        finally:
            evidence_jsonl.unlink(missing_ok=True)
        evidence_added = int(response.get("added", 0) or 0)
        evidence_duplicate = _batch_count(response.get("duplicates"))
        evidence_errors = response.get("errors") if isinstance(response.get("errors"), list) else []

    display_number_status = "ok"
    display_number_error = None
    try:
        _run_dr(citation_manager, ["assign-display-numbers", "--dir", str(dst_dir)])
    except Exception as exc:  # noqa: BLE001
        display_number_status = "failed"
        display_number_error = str(exc)[:300]

    return {
        "into": str(dst_dir),
        "sources_added": sources_added,
        "sources_duplicate": sources_duplicate,
        "source_errors": source_errors,
        "evidence_added": evidence_added,
        "evidence_duplicate": evidence_duplicate,
        "evidence_skipped": evidence_skipped,
        "evidence_errors": evidence_errors,
        "display_number_status": display_number_status,
        "display_number_error": display_number_error,
    }


# --- Feature #7: standard stock deep-research plan ----------------------------
def _q(query: str, purpose: str, query_type: str, priority: int = 2,
       recency: str | None = None, max_results: int = 10) -> dict[str, Any]:
    item: dict[str, Any] = {
        "query": query,
        "purpose": purpose,
        "query_type": query_type,
        "priority": priority,
        "max_results": max_results,
        "snippet_mode": "high",
    }
    if recency:
        item["search_recency_filter"] = recency
    return item


def build_stock_plan(company: str, ticker: str, exchange: str | None = None,
                     sector: str | None = None, fy: str | None = None,
                     peers: list[str] | None = None, mode: str = "deep",
                     issuer_domains: list[str] | None = None) -> dict[str, Any]:
    """Standard institutional equity deep-dive: filings, results, governance,
    M&A, financial quality, valuation, peers, bear case. query_type tags let the
    run-time domain filter (feature #4) route each query to the right sources."""
    fy = fy or ""
    sector = sector or ""
    exch = exchange or ""
    peer_str = " ".join(peers or [])
    queries = [
        # 1. Filings & disclosures
        _q(f"{company} {ticker} 10-K annual report SEC EDGAR {fy}".strip(),
           "Most recent 10-K: full financial statements and MD&A.", "filings", 1, "year"),
        _q(f"{company} {ticker} 10-Q quarterly report SEC EDGAR {fy}".strip(),
           "Most recent 10-Q interim financials.", "filings", 1, "year"),
        _q(f"{company} {ticker} 8-K material event current report",
           "Recent 8-K material events.", "filings", 2, "year"),
        _q(f"{company} {ticker} {exch} investor relations annual report presentation".strip(),
           "Company IR disclosures and presentations.", "issuer_ir", 3),
        # 2. Latest results
        _q(f"{company} {ticker} latest quarterly earnings revenue EPS beat miss {fy}".strip(),
           "Most recent earnings: headline financials.", "results_earnings", 1, "month"),
        _q(f"{company} {ticker} earnings call transcript guidance outlook {fy}".strip(),
           "Earnings call commentary, guidance, Q&A tone.", "results_earnings", 1, "month"),
        _q(f"{company} {ticker} full year guidance revenue EBITDA free cash flow raised lowered {fy}".strip(),
           "Full-year guidance and revisions.", "results_earnings", 2, "year"),
        # 3. Governance
        _q(f"{company} {ticker} DEF 14A proxy statement executive compensation board",
           "Proxy: executive pay, board composition.", "governance", 2, "year"),
        _q(f"{company} {ticker} insider ownership Form 4 director executive transactions {fy}".strip(),
           "Insider ownership and recent Form 4 transactions.", "governance", 3, "year"),
        _q(f"{company} {ticker} institutional ownership 13F top shareholders",
           "Institutional ownership concentration.", "governance", 3, "year"),
        # 4. M&A history
        _q(f"{company} {ticker} acquisitions merger history deal value announced closed",
           "M&A chronology with deal values and rationale.", "ma", 2),
        _q(f"{company} {ticker} divestitures spin-off asset sale discontinued operations",
           "Divestitures and portfolio pruning.", "ma", 4),
        # 5. Financial quality
        _q(f"{company} {ticker} organic revenue growth segment mix gross margin trend {fy}".strip(),
           "Revenue decomposition and margin progression.", "financials", 1),
        _q(f"{company} {ticker} free cash flow conversion capex working capital {fy}".strip(),
           "Cash generation quality and FCF conversion.", "financials", 1),
        _q(f"{company} {ticker} net debt leverage EBITDA covenant liquidity credit facility",
           "Capital structure, leverage, debt maturities.", "financials", 2),
        _q(f"{company} {ticker} accounting quality goodwill impairment revenue recognition restatement",
           "Accounting-quality red flags.", "financials", 2),
        # 6. Valuation
        _q(f"{company} {ticker} EV/EBITDA P/E price to sales consensus analyst price target",
           "Current trading multiples and price targets.", "valuation", 2, "month"),
        _q(f"{company} {ticker} analyst upgrade downgrade rating initiation {fy}".strip(),
           "Analyst rating changes as sentiment signal.", "valuation", 3, "year"),
        _q(f"{company} {ticker} historical valuation multiple range premium discount to sector",
           "Historical multiple range vs. sector.", "valuation", 3),
        # 7. Peers
        _q(f"{company} competitors peers comparable companies {sector} market share".strip(),
           "Peer set and market positioning.", "peers", 3),
        _q(f"{company} {ticker} vs {peer_str} revenue growth margin comparison {fy}".strip()
           if peer_str else f"{company} {ticker} peer benchmarking revenue growth margin comparison {fy}".strip(),
           "Benchmark key metrics vs. peers.", "peers", 3),
        # 8. Bear case
        _q(f"{company} {ticker} short thesis bear case risks concerns criticism {fy}".strip(),
           "Published bear arguments and short reports.", "bear_case", 4, "year"),
        _q(f"{company} {ticker} regulatory risk antitrust litigation SEC investigation",
           "Regulatory, legal, and enforcement tail risk.", "bear_case", 4, "year"),
        _q(f"{company} {ticker} customer concentration churn management departure CFO CEO turnover {fy}".strip(),
           "Concentration risk and management-stability signals.", "bear_case", 4, "year"),
    ]
    label = f"{company} ({ticker}) institutional equity deep-dive".strip()
    return {
        "topic": label,
        "mode": mode if mode in VALID_MODES else "deep",
        "plan_type": "stock",
        "entity": company,
        "ticker": ticker,
        "exchange": exchange,
        "sector": sector or None,
        "issuer_domains": _normalized_domains(issuer_domains),
        "queries": queries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Search-as-Code Perplexity Search API plan.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--plan", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--plan", required=True)
    run_parser.add_argument("--out-dir", required=True)
    run_parser.add_argument("--concurrency", type=int, default=10)
    run_parser.add_argument("--timeout", type=float, default=60.0)
    run_parser.set_defaults(no_batch=True)
    run_parser.add_argument("--batch", dest="no_batch", action="store_false",
                            help="Opt in to batching compatible queries into up to five-query Search API requests.")
    run_parser.add_argument("--no-batch", "--one-query-per-run", dest="no_batch", action="store_true",
                            help="Send one query per request (no batching); reflected in the manifest.")
    run_parser.add_argument("--extract", action="store_true",
                            help="Fetch top sources and store exact extracted snippets (PDF/HTML).")
    run_parser.add_argument("--extract-max-sources", type=int, default=8)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--run-dir", required=True)

    costs_parser = subparsers.add_parser("costs")
    costs_parser.add_argument("--run-dir", required=True)

    template_parser = subparsers.add_parser("template", help="Emit a standard stock deep-research SearchPlan.")
    template_parser.add_argument("--ticker", required=True)
    template_parser.add_argument("--company", required=True)
    template_parser.add_argument("--exchange", default=None)
    template_parser.add_argument("--sector", default=None)
    template_parser.add_argument("--issuer-domain", action="append", default=[],
                                 help="Issuer or investor-relations domain to allow in issuer/filings/results lanes. Repeat or comma-separate.")
    template_parser.add_argument("--fy", default=None)
    template_parser.add_argument("--peers", default=None, help="Comma-separated peer names/tickers.")
    template_parser.add_argument("--mode", default="deep", choices=sorted(VALID_MODES))
    template_parser.add_argument("--out", default=None, help="Write plan to this path instead of stdout.")

    import_parser = subparsers.add_parser("import", help="Merge a run into deep-research master ledgers.")
    import_parser.add_argument("--run-dir", required=True)
    import_parser.add_argument("--into", required=True, help="Deep-research project dir with sources/evidence ledgers.")
    import_parser.add_argument("--dr-scripts", default=str(DR_SCRIPTS_DEFAULT))

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            plan = read_json(Path(args.plan))
            errors = validate_plan(plan)
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            print("SearchPlan valid")
            return 0
        if args.command == "run":
            run_plan(read_json(Path(args.plan)), Path(args.out_dir), args.concurrency, args.timeout,
                     no_batch=args.no_batch, extract=args.extract, extract_max_sources=args.extract_max_sources)
            print(f"Wrote Search-as-Code run to {args.out_dir}")
            return 0
        if args.command == "summarize":
            summarize_run(Path(args.run_dir))
            return 0
        if args.command == "costs":
            print_costs(Path(args.run_dir))
            return 0
        if args.command == "template":
            peers = [p.strip() for p in args.peers.split(",") if p.strip()] if args.peers else None
            issuer_domains = [
                domain.strip()
                for value in (args.issuer_domain or [])
                for domain in value.split(",")
                if domain.strip()
            ]
            plan = build_stock_plan(args.company, args.ticker, exchange=args.exchange,
                                    sector=args.sector, fy=args.fy, peers=peers, mode=args.mode,
                                    issuer_domains=issuer_domains)
            text = json.dumps(plan, indent=2, ensure_ascii=False)
            if args.out:
                Path(args.out).write_text(text + "\n", encoding="utf-8")
                print(f"Wrote stock SearchPlan to {args.out}")
            else:
                print(text)
            return 0
        if args.command == "import":
            stats = merge_into_project(Path(args.run_dir), Path(args.into), Path(args.dr_scripts))
            print(json.dumps(stats, indent=2, sort_keys=True))
            return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
