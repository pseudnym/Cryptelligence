"""Fetch only public HTTP(S) documents. Pin DNS results to prevent private-network redirects/rebinding."""
import hashlib
import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin, parse_qsl, urlencode
from .osint_provider import OSINTError, TTLCache

def canonical_url(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise OSINTError("unsafe_url", "Only public HTTP(S) source URLs without credentials are accepted.")
    if parsed.port not in (None, 80, 443):
        raise OSINTError("unsafe_url", "Nonstandard source ports are not permitted.")
    host = parsed.hostname.lower().rstrip(".")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise OSINTError("unsafe_url", "Private-network source URLs are not permitted.")
    except ValueError:
        if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
            raise OSINTError("unsafe_url", "Private-network source URLs are not permitted.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))))
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", query, ""))

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.text, self.links, self.title = [], [], []
        self.in_title = False
        self.published = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}: self.skip += 1
        if tag == "title": self.in_title = True
        if tag == "a" and attrs.get("href"): self.links.append(attrs["href"])
        if tag == "meta" and attrs.get("property", attrs.get("name", "")).lower() in {"article:published_time", "datepublished", "date"}:
            self.published = attrs.get("content")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}: self.skip = max(0, self.skip - 1)
        if tag == "title": self.in_title = False
    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if not self.skip and data.strip(): self.text.append(data.strip())

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip
    def connect(self):
        self.sock = self._context.wrap_socket(socket.create_connection((self.ip, self.port), self.timeout), server_hostname=self.host)

class PublicPageFetcher:
    def __init__(self, settings):
        self.settings, self.cache = settings, TTLCache(settings.cache_seconds)
    def fetch(self, url):
        url = canonical_url(url)
        cached = self.cache.get(url)
        if cached is not None: return cached
        original = url
        for _ in range(4):
            parsed = urlsplit(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
                if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
                    raise OSINTError("unsafe_url", "Source resolves to a non-public network address.")
                ip = sorted(addresses)[0]
                connection = PinnedHTTPS(parsed.hostname, ip, port, self.settings.timeout) if parsed.scheme == "https" else http.client.HTTPConnection(ip, port, timeout=self.settings.timeout)
                try:
                    connection.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""),
                        headers={"Host": parsed.netloc, "User-Agent": "EvidenceEngine/0.1 public-source-research",
                                 "Accept": "text/html,text/plain", "Accept-Encoding": "identity"})
                    response = connection.getresponse()
                    if response.status in {301, 302, 303, 307, 308}:
                        url = canonical_url(urljoin(url, response.getheader("Location", "")))
                        continue
                    if response.status != 200:
                        raise OSINTError("source_unavailable", "Source page unavailable; only the search excerpt was retained.")
                    content_type = response.getheader("Content-Type", "").lower()
                    if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml")):
                        raise OSINTError("unsupported_source", "Unsupported source format; only the search excerpt was retained.")
                    raw = response.read(500001)
                    if len(raw) > 500000:
                        raise OSINTError("source_limit", "Source exceeded the fetch limit; only the search excerpt was retained.")
                finally:
                    connection.close()
            except (OSError, http.client.HTTPException, ssl.SSLError, UnicodeError):
                raise OSINTError("source_unavailable", "Source fetch failed; only the search excerpt was retained.") from None
            html = raw.decode("utf-8", errors="replace")
            parser = PageParser()
            parser.feed(html)
            text = " ".join(parser.text) if "html" in content_type else html
            links = []
            for link in parser.links[:300]:
                try: links.append(canonical_url(urljoin(url, link)))
                except (OSINTError, ValueError): pass
            page = dict(url=url, text=text[:100000], title=" ".join(parser.title)[:300],
                        published_at=parser.published, links=list(dict.fromkeys(links)),
                        content_sha256=hashlib.sha256(raw).hexdigest())
            self.cache.put(original, page)
            return page
        raise OSINTError("redirect_limit", "Source redirect limit reached; only the search excerpt was retained.")
