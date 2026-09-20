"""Public-source search contract, bounded retries and in-memory TTL caching."""
import copy
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit
from xml.etree import ElementTree
import httpx

class OSINTError(Exception):
    def __init__(self, kind, message):
        self.kind, self.safe_message = kind, message
        super().__init__(message)

@dataclass(frozen=True)
class OSINTSettings:
    provider: str = "brave"
    api_key: str = field(default="", repr=False)
    endpoint: str = "https://api.search.brave.com/res/v1/web/search"
    timeout: float = 10
    retries: int = 2
    max_results: int = 5
    cache_seconds: int = 3600
    rss_fallback: bool = False
    fetch_pages: bool = True
    @classmethod
    def from_env(cls):
        return cls(provider=os.getenv("OSINT_PROVIDER", "brave"),
            api_key=os.getenv("OSINT_API_KEY", os.getenv("BRAVE_SEARCH_API_KEY", "")),
            endpoint=os.getenv("OSINT_API_URL", "https://api.search.brave.com/res/v1/web/search"),
            timeout=max(1, min(30, float(os.getenv("OSINT_TIMEOUT_SECONDS", "10")))),
            retries=max(0, min(3, int(os.getenv("OSINT_RETRIES", "2")))),
            max_results=max(1, min(10, int(os.getenv("OSINT_MAX_RESULTS", "5")))),
            cache_seconds=max(1, int(os.getenv("OSINT_CACHE_SECONDS", "3600"))),
            rss_fallback=os.getenv("OSINT_ALLOW_RSS_FALLBACK", "false").lower() == "true",
            fetch_pages=os.getenv("OSINT_FETCH_PAGES", "true").lower() == "true")

@dataclass
class SourceHit:
    url: str
    title: str
    excerpt: str
    published_at: str | None = None
    metadata: dict = field(default_factory=dict)
    document_text: str | None = None

@dataclass
class SearchResponse:
    hits: list[SourceHit]
    provider: str
    warnings: list[str] = field(default_factory=list)

class OSINTProvider(Protocol):
    name: str
    def search(self, query: str) -> SearchResponse: ...

class TTLCache:
    def __init__(self, ttl, clock=time.monotonic):
        self.ttl, self.clock, self.items = ttl, clock, OrderedDict()
    def get(self, key):
        entry = self.items.get(key)
        if entry and entry[0] > self.clock():
            return copy.deepcopy(entry[1])
        self.items.pop(key, None)
        return None
    def put(self, key, value):
        self.items[key] = (self.clock() + self.ttl, copy.deepcopy(value))
        self.items.move_to_end(key)
        while len(self.items) > 128:
            self.items.popitem(last=False)

class LiveSearchProvider:
    name = "brave"
    def __init__(self, settings, transport=None, sleeper=time.sleep):
        self.settings, self.transport, self.sleeper = settings, transport, sleeper
        self.cache = TTLCache(settings.cache_seconds)
    def request(self, url, params, headers=None):
        for attempt in range(self.settings.retries + 1):
            try:
                with httpx.Client(timeout=self.settings.timeout, transport=self.transport, follow_redirects=False) as client:
                    response = client.get(url, params=params, headers={"Accept": "application/json", "User-Agent": "EvidenceEngine/0.1", **(headers or {})})
                if response.status_code in (401, 403):
                    raise OSINTError("authentication", "Public search authentication failed. Check OSINT_API_KEY and provider configuration.")
                if response.status_code == 429 or response.status_code >= 500:
                    raise OSINTError("rate_limit" if response.status_code == 429 else "provider", "Public search is rate limited or temporarily unavailable. Retry later.")
                if response.status_code != 200 or len(response.content) > 1_000_000:
                    raise OSINTError("response", "Public search returned an unsuccessful or oversized response.")
                return response
            except httpx.TimeoutException:
                error = OSINTError("timeout", "Public search timed out. Retry the interrupted action.")
            except httpx.HTTPError:
                error = OSINTError("connection", "Public search connection failed.")
            except OSINTError as exc:
                if exc.kind not in {"rate_limit", "provider"}: raise
                error = exc
            if attempt == self.settings.retries:
                raise error
            self.sleeper(min(4, .5 * 2 ** attempt))

    def search(self, query):
        query = " ".join(query.split())[:500]
        key = (self.settings.provider, query)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            if self.settings.provider == "bing_rss":
                response = self.rss(query)
            elif self.settings.provider in {"ddgs", "duckduckgo"}:
                response = self.duckduckgo(query)
            elif self.settings.provider == "github":
                response = self.github(query)
            elif self.settings.provider == "brave":
                if not self.settings.api_key:
                    raise OSINTError("configuration", "Brave search needs OSINT_API_KEY in backend/.env. Restart the backend after configuration; Ethereum and fixture collection remain available.")
                parsed = urlsplit(self.settings.endpoint)
                if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
                    raise OSINTError("configuration", "OSINT_API_URL must be an HTTPS search endpoint without embedded credentials.")
                data = self.request(self.settings.endpoint, {"q": query, "count": self.settings.max_results, "text_decorations": "false"},
                                    {"X-Subscription-Token": self.settings.api_key}).json()
                rows = data.get("web", {}).get("results", [])
                if not isinstance(rows, list): raise ValueError()
                hits = []
                for row in rows[:self.settings.max_results]:
                    if not isinstance(row, dict) or not isinstance(row.get("url"), str) or not isinstance(row.get("title"), str):
                        raise ValueError()
                    hits.append(SourceHit(row["url"], row["title"][:300], str(row.get("description") or "")[:2000],
                        str(row["page_age"]) if row.get("page_age") else None, {"search_provider": "brave"}))
                response = SearchResponse(hits, "brave")
            else:
                raise OSINTError("configuration", "Unsupported OSINT_PROVIDER. Use ddgs, duckduckgo, brave, bing_rss or github.")
        except OSINTError as error:
            if not self.settings.rss_fallback or self.settings.provider != "brave":
                raise
            response = self.rss(query)
            response.warnings.append("Brave was unavailable; explicitly configured Bing RSS fallback was used. Search coverage and relevance may be poor.")
        except (ValueError, TypeError, AttributeError, KeyError):
            raise OSINTError("malformed", "Public search returned malformed results.") from None
        self.cache.put(key, response)
        return response

    def duckduckgo(self, query):
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
        for attempt in range(self.settings.retries + 1):
            try:
                rows = DDGS(timeout=self.settings.timeout).text(
                    query, backend="duckduckgo", max_results=self.settings.max_results)
                if not isinstance(rows, list):
                    raise OSINTError("malformed", "DuckDuckGo returned malformed results.")
                hits = []
                for row in rows[:self.settings.max_results]:
                    if not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in ("href", "title", "body")):
                        raise OSINTError("malformed", "DuckDuckGo returned malformed results.")
                    hits.append(SourceHit(row["href"], row["title"][:300], row["body"][:2000],
                        metadata={"search_provider": "duckduckgo", "adapter": "ddgs"}))
                return SearchResponse(hits, "duckduckgo", ["Unofficial DuckDuckGo search via DDGS; coverage may be incomplete. Search snippets are not verified page content."])
            except TimeoutException:
                error = OSINTError("timeout", "DuckDuckGo search timed out. Retry the interrupted action.")
            except RatelimitException:
                error = OSINTError("rate_limit", "DuckDuckGo search is rate limited. Retry later.")
            except DDGSException:
                # DDGS can report blocking and empty searches with the same exception.
                # Never present this ambiguous failure as proof of no public records.
                error = OSINTError("provider", "DuckDuckGo could not return results; it may be blocked or have no matches. Retry later or use another OSINT provider.")
            if attempt == self.settings.retries:
                raise error from None
            self.sleeper(min(4, .5 * 2 ** attempt))

    def rss(self, query):
        response = self.request("https://www.bing.com/search", {"q": query, "format": "rss"})
        if b"<!DOCTYPE" in response.content.upper() or b"<!ENTITY" in response.content.upper():
            raise OSINTError("malformed", "Unsafe RSS document rejected.")
        try:
            root = ElementTree.fromstring(response.content)
            if root.tag != "rss": raise ValueError()
            hits = [SourceHit(item.findtext("link") or "", item.findtext("title") or "", item.findtext("description") or "",
                              None, {"search_provider": "bing_rss"}) for item in root.findall("./channel/item")[:self.settings.max_results]]
            return SearchResponse(hits, "bing_rss", ["Public RSS results may omit exact matches. Snippets are not verified page content."])
        except (ElementTree.ParseError, ValueError):
            raise OSINTError("malformed", "Public search returned invalid RSS.") from None

    def github(self, query):
        try:
            data = self.request("https://api.github.com/search/issues", {"q": query, "per_page": self.settings.max_results}).json()
            if not isinstance(data.get("items"), list): raise ValueError()
            hits = []
            for item in data["items"][:self.settings.max_results]:
                content = str(item.get("body") or "")
                warnings = []
                # Public pull-request diffs are original code/research data; never executed.
                if "pull_request" in item:
                    parts = urlsplit(item["html_url"])
                    segments = parts.path.strip("/").split("/")
                    if parts.hostname == "github.com" and len(segments) == 4 and segments[2] == "pull":
                        api = "https://api.github.com/repos/" + "/".join(segments[:2]) + "/pulls/" + segments[3] + "/files"
                        try:
                            files = self.request(api, {"per_page": 10}).json()
                            if isinstance(files, list):
                                content += "\n".join(str(f.get("patch") or "") for f in files[:10])[:50000]
                        except OSINTError:
                            warnings.append("Pull-request file content was unavailable.")
                hits.append(SourceHit(item["html_url"], item["title"][:300], content[:2000],
                    item.get("created_at"), {"search_provider": "github_public", "content_kind": "public_issue_or_pull_request",
                    "coverage_limit": "First 10 changed files; patch may be truncated.", "warnings": warnings}, content or None))
            return SearchResponse(hits, "github_public")
        except (ValueError, TypeError, KeyError, AttributeError):
            raise OSINTError("malformed", "Public GitHub search returned malformed results.") from None

class MockOSINTProvider:
    name = "mock_osint_provider"
    def __init__(self, hits=()):
        self.hits, self.queries = list(hits), []
    def search(self, query):
        self.queries.append(query)
        return SearchResponse(copy.deepcopy(self.hits), self.name)
