"""Deterministic public-source extraction and conservative independence heuristics."""
import hashlib
import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit
from ..models.domain import Entity
from .chains import address_key, solana_address, solana_signature
from ..models.osint import PublicSource
from .public_source import PageParser, canonical_url
from .osint_provider import OSINTError

WALLET = re.compile(r"(?<![a-zA-Z0-9])0x[a-fA-F0-9]{40}(?![a-fA-F0-9])")
TX = re.compile(r"(?<![a-zA-Z0-9])0x[a-fA-F0-9]{64}(?![a-fA-F0-9])")
def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:24]
def plain(text):
    parser = PageParser()
    parser.feed(text)
    return " ".join(parser.text)
def exact_match(text, identifier):
    return re.search(r"(?<![\w])" + re.escape(identifier) + r"(?![\w])", text, flags=re.I if identifier.startswith("0x") else 0)
def publisher(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").removeprefix("www.")
    if host == "github.com":
        return host + "/" + parsed.path.strip("/").split("/")[0].lower()
    return host
def publisher_group(name):
    if "/" in name: return name
    parts = name.split(".")
    return ".".join(parts[-3:] if ".".join(parts[-2:]) in {"co.uk", "com.au", "gov.uk", "co.jp"} else parts[-2:])

def extract_identifiers(text, title, links):
    wallets = sorted({v.lower() for v in WALLET.findall(text)})[:30]
    hashes = sorted({v.lower() for v in TX.findall(text)})[:30]
    candidates = [dict(kind="wallet", value=v) for v in wallets] + [dict(kind="transaction_hash", value=v) for v in hashes]
    for value in set(re.findall(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,88}(?![A-Za-z0-9])", text)):
        try:
            solana_address(value)
            candidates.append(dict(kind="solana_wallet", value=value))
        except ValueError:
            try:
                solana_signature(value)
                candidates.append(dict(kind="solana_signature", value=value))
            except ValueError: pass
    patterns = {
        "name_service": r"\b[a-zA-Z0-9][a-zA-Z0-9_-]*\.(?:eth|sol)\b",
        "public_handle": r"(?<!\w)@[a-zA-Z0-9_]{2,30}\b",
        "organization_or_protocol": r"\b[A-Z][\w-]+(?: [A-Z][\w-]+){0,2} (?:Labs|Foundation|Protocol|Network|Finance|DAO)\b",
        "incident": r"\b[A-Z][\w-]+(?: [A-Z][\w-]+){0,2} (?:exploit|incident|breach|hack)\b",
    }
    for kind, pattern in patterns.items():
        candidates.extend(dict(kind=kind, value=v) for v in sorted(set(re.findall(pattern, title + " " + text)))[:10])
    for link in links[:30]:
        parsed = urlsplit(link)
        if parsed.hostname:
            candidates.append(dict(kind="domain", value=parsed.hostname))
        if parsed.hostname == "github.com" and parsed.path.strip("/"):
            candidates.append(dict(kind="github_username", value=parsed.path.strip("/").split("/")[0]))
    return wallets, hashes, list({(c["kind"], address_key(c["value"])): c for c in candidates}.values())[:60]

def candidate_entity(candidate):
    value, kind = candidate["value"], candidate["kind"]
    if kind == "wallet":
        id, type, chain = "eth-" + value.lower(), "wallet", "ethereum"
    elif kind == "solana_wallet":
        id, type, chain = "sol-" + solana_address(value), "wallet", "solana"
    else:
        id, type, chain = "public-" + digest(kind + ":" + address_key(value)), "public_identifier", None
    return Entity(id=id, entity_type=type, chain=chain, value=value, label=value[:80],
        metadata={"candidate": True, "identifier_kind": kind, "relationship": "co_mentioned_in_public_source", "identity_verified": False})

def build_source(hit, identifier, page=None):
    url = canonical_url(page["url"] if page else hit.url)
    text = page["text"] if page else (hit.document_text if hit.document_text is not None else plain(hit.excerpt))
    retrieved = page is not None or hit.document_text is not None
    title = (page.get("title") if page else None) or plain(hit.title)
    match = exact_match(text, identifier)
    excerpt = text[max(0, match.start() - 160):match.end() + 500] if match else text[:700]
    links = page.get("links", []) if page else re.findall(r"https?://[^\s<>\]\)]+", text)[:50]
    cited = []
    for link in links:
        try:
            normalized = canonical_url(link)
            if publisher_group(publisher(normalized)) != publisher_group(publisher(url)):
                cited.append(normalized)
        except (ValueError, OSINTError):
            pass
    wallets, hashes, identifiers = extract_identifiers(text, title, links)
    domain = publisher(url)
    official = (urlsplit(url).hostname or "").endswith((".gov", ".gov.uk", ".mil"))
    source_kind = "government_or_enforcement" if official else "public_repository" if urlsplit(url).hostname == "github.com" else "public_web"
    # Classification is structural; do not infer editorial authority from page claims.
    narrow = (f'The retrieved document "{title}" at {domain} explicitly mentions {identifier}.'
              if retrieved and match else f'The search excerpt for "{title}" at {domain} mentions {identifier}; the page occurrence is unverified.'
              if match else f'Search returned "{title}" at {domain}; an exact occurrence of {identifier} was not verified.')
    limitations = ["A mention or source allegation does not establish ownership, identity, guilt or participation.",
                   "Publisher independence is assessed heuristically; shared wording or citations can indicate dependence.",
                   "Candidate identifiers are co-mentions, not verified identity links."]
    if not retrieved: limitations.append("Only a search snippet was available; no original document was verified.")
    if not match: limitations.append("Exact identifier relevance is unverified; this hit is not attribution evidence.")
    source = PublicSource(publisher=domain, source_kind=source_kind, excerpt=excerpt,
        published_at=(page.get("published_at") if page else None) or hit.published_at,
        retrieved_document=retrieved, exact_match=bool(match), query_identifier=identifier,
        narrow_statement=narrow, limitations=limitations, wallet_addresses=wallets, transaction_hashes=hashes,
        identifiers=identifiers, cited_sources=sorted(set(cited))[:30], content_fingerprint=digest(text.lower()),
        reliability_reason="Official-domain publication; this rates provenance, not the truth of an allegation." if official else
                           "Public publication with unverified editorial accuracy and ownership attribution.")
    return url, title, source, ("HIGH" if official and retrieved else "MEDIUM" if retrieved else "LOW")

def assess_independence(evidence):
    sources = [e for e in evidence if e.source is not None]
    output = {}
    for record in sources:
        s = record.source
        status, derivative, reason = "UNKNOWN", False, "No independent corroboration has been established."
        for other in sources:
            if other.id == record.id: continue
            o = other.source
            if address_key(s.query_identifier) != address_key(o.query_identifier): continue
            same_publisher = publisher_group(s.publisher) == publisher_group(o.publisher)
            same_text = s.content_fingerprint == o.content_fingerprint or SequenceMatcher(None, s.excerpt.lower(), o.excerpt.lower()).ratio() > .7
            cites = (other.source_url in s.cited_sources or record.source_url in o.cited_sources or bool(set(s.cited_sources) & set(o.cited_sources)))
            if same_publisher or same_text or cites:
                status, derivative = "NO", same_text or cites
                reason = "Same publisher, substantially repeated content or a shared/cited upstream source; do not count as independent corroboration."
                break
            markers = ("our analysis", "our investigation", "we independently", "we examined")
            if s.retrieved_document and o.retrieved_document and s.exact_match and o.exact_match and any(m in s.excerpt.lower() for m in markers) and any(m in o.excerpt.lower() for m in markers):
                status = "YES"
                reason = "Heuristic candidate: distinct publishers describe their own examination without detected shared sources. Analyst verification is still required."
        output[record.id] = dict(corroboration=status, derivative=derivative, reason=reason)
    return output
