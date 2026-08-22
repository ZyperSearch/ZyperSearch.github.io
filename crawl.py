import asyncio
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import httpx
import lxml.html


# ============================================================
# CONFIGURATION
# ============================================================

COMMON_PATHS: List[str] = []

MODEL_URL = "https://openrouter.ai/api/v1/chat/completions"

HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/webp,*/*;q=0.8"
    ),
    "User-Agent": (
        "Mozilla/5.0 (compatible; ZyperSearchBot/3.0; "
        "+https://example.com/bot)"
    ),
    "Accept-Language": "en-US,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

RESPECT_ROBOTS = False
ROBOTS_PATH = "/robots.txt"

LIMITS = httpx.Limits(
    max_connections=250,
    max_keepalive_connections=100,
)

MAX_DEPTH = 20
NUM_WORKERS = 80

MAX_TARGET_URLS = 8000000

OPENROUTER_CONCURRENCY_LIMIT = 20

REQUEST_TIMEOUT = 15.0
MAX_PAGE_BYTES = 8 * 1024 * 1024

MIN_TEXT_LENGTH = 40
MAX_SNIPPET_LENGTH = 420
MAX_KEYWORDS = 30
MAX_TAGS = 12

llm_semaphore = asyncio.Semaphore(
    OPENROUTER_CONCURRENCY_LIMIT
)


# ============================================================
# STOP WORDS
# ============================================================

STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


# ============================================================
# DOMAIN MATCHER
# ============================================================

class DynamicPatternMatcher:
    def __init__(
        self,
        static_patterns: List[str],
        dynamic_hosts: List[str],
    ):
        self.exact_domains: Set[str] = set()
        self.wildcard_domains: Set[str] = set()
        self.tlds: Set[str] = set()
        self.partial_matches: List[str] = []

        all_patterns = list(static_patterns) + list(dynamic_hosts)

        for pattern in all_patterns:
            pattern = pattern.strip().lower()

            if not pattern:
                continue

            if pattern.startswith("*."):
                domain = pattern[2:]
                self.wildcard_domains.add(domain)
                self.exact_domains.add(domain)

            elif pattern.startswith("."):
                if pattern.count(".") == 1:
                    self.tlds.add(pattern)
                else:
                    self.partial_matches.append(pattern)

            else:
                self.exact_domains.add(pattern)
                self.wildcard_domains.add(pattern)

    def is_valid_host(self, host: str) -> bool:
        if not host:
            return False

        host = host.lower().split(":")[0]

        if host in self.exact_domains:
            return True

        for domain in self.wildcard_domains:
            if host.endswith("." + domain):
                return True

        for tld in self.tlds:
            if host.endswith(tld):
                return True

        for partial in self.partial_matches:
            normalized = partial.lstrip(".")

            if normalized in host:
                return True

            if host.endswith(normalized):
                return True

        return False


# ============================================================
# URL NORMALIZATION
# ============================================================

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
}


def normalize_url(url: str) -> str:
    try:
        url = urldefrag(url)[0]

        parsed = urlparse(url)

        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()

        if not scheme or not hostname:
            return ""

        port = parsed.port

        if port and not (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            netloc = f"{hostname}:{port}"
        else:
            netloc = hostname

        path = parsed.path or "/"

        path = re.sub(r"/{2,}", "/", path)

        if path != "/":
            path = path.rstrip("/")

        # Drop known tracking/query parameters.
        query_parts = []

        if parsed.query:
            for part in parsed.query.split("&"):
                if "=" in part:
                    key, value = part.split("=", 1)

                    if key.lower() not in TRACKING_PARAMETERS:
                        query_parts.append(f"{key}={value}")
                elif part.lower() not in TRACKING_PARAMETERS:
                    query_parts.append(part)

        query = "&".join(query_parts)

        return urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                query,
                "",
            )
        )

    except Exception:
        return ""


# ============================================================
# HTML EXTRACTION
# ============================================================

def clean_html_lxml(
    html_content: str,
) -> Tuple[str, str, Dict[str, str]]:
    try:
        # Pre-strip noisy tags to prevent any raw content or CSS/JS leaking into text
        cleaned_html = re.sub(
            r"<(script|style|noscript|template|svg|iframe)\b[^>]*>[\s\S]*?<\/\1>",
            " ",
            html_content,
            flags=re.IGNORECASE,
        )

        parser = lxml.html.HTMLParser(
            encoding="utf-8"
        )

        doc = lxml.html.fromstring(
            cleaned_html.encode(
                "utf-8",
                errors="ignore",
            ),
            parser=parser,
        )

    except Exception:
        return "Untitled", "", {}

    # Remove content that is almost never useful for search.
    for tag in [
        "script",
        "style",
        "noscript",
        "template",
        "header",
        "footer",
        "nav",
        "aside",
        "svg",
        "canvas",
        "form",
        "iframe",
    ]:
        for element in doc.xpath(f"//{tag}"):
            parent = element.getparent()

            if parent is not None:
                parent.remove(element)

    title_nodes = doc.xpath("//title")

    title = (
        title_nodes[0].text_content().strip()
        if title_nodes
        else "Untitled"
    )

    title = re.sub(r"\s+", " ", title).replace("\ufffd", " ").strip()

    description = ""
    keywords = ""
    canonical = ""
    language = ""

    description_nodes = doc.xpath(
        '//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz")="description"]/@content'
    )

    if description_nodes:
        description = re.sub(
            r"\s+",
            " ",
            description_nodes[0],
        ).replace("\ufffd", " ").strip()

    keyword_nodes = doc.xpath(
        '//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz")="keywords"]/@content'
    )

    if keyword_nodes:
        keywords = re.sub(
            r"\s+",
            " ",
            keyword_nodes[0],
        ).replace("\ufffd", " ").strip()

    canonical_nodes = doc.xpath(
        '//link[contains('
        'translate(@rel, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz"), "canonical")]/@href'
    )

    if canonical_nodes:
        canonical = canonical_nodes[0].strip()

    html_nodes = doc.xpath("//html/@lang")

    if html_nodes:
        language = html_nodes[0].strip().lower()

    # Prefer main/article content when available.
    content_root = None

    main_nodes = doc.xpath("//main")

    if main_nodes:
        content_root = main_nodes[0]

    if content_root is None:
        article_nodes = doc.xpath("//article")

        if article_nodes:
            content_root = article_nodes[0]

    if content_root is None:
        content_root = doc

    raw_text = content_root.text_content()
    # Remove any leftover JSON dumps, style snippets, balancer strings, and unicode replacement characters
    raw_text = re.sub(r'<style\b[^>]*>[\s\S]*?(?:<\/style>|$)', ' ', raw_text, flags=re.I)
    raw_text = re.sub(r'\{"[a-zA-Z0-9_]+":[\s\S]*?\}', ' ', raw_text)
    raw_text = re.sub(r'\d{10,}-[a-zA-Z0-9_-]+', ' ', raw_text)
    raw_text = raw_text.replace("\ufffd", " ")

    body_text = " ".join(raw_text.split())

    return (
        title or "Untitled",
        body_text,
        {
            "description": description,
            "keywords": keywords,
            "canonical": canonical,
            "language": language,
        },
    )


# ============================================================
# SNIPPET GENERATION
# ============================================================

def get_first_four_sentences(text: str) -> str:
    if not text:
        return ""

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    cleaned = [
        re.sub(r"\s+", " ", sentence).strip()
        for sentence in sentences
        if sentence.strip()
    ]

    result = " ".join(cleaned[:4]).strip()

    if len(result) > MAX_SNIPPET_LENGTH:
        result = result[:MAX_SNIPPET_LENGTH].rsplit(
            " ",
            1,
        )[0] + "..."

    return result


# ============================================================
# KEYWORD EXTRACTION
# ============================================================

def extract_keywords(
    title: str,
    text: str,
    meta_keywords: str,
) -> List[str]:
    source = " ".join(
        [
            title,
            title,
            meta_keywords,
            text[:12000],
        ]
    ).lower()

    words = re.findall(
        r"\b[\w][\w+#.-]{1,32}\b",
        source,
        flags=re.UNICODE,
    )

    counter = Counter()

    for word in words:
        word = word.strip("._-")

        if not word:
            continue

        if len(word) < 2:
            continue

        if word in STOP_WORDS:
            continue

        if word.isnumeric():
            continue

        counter[word] += 1

    # Give title words more importance.
    for word in re.findall(
        r"\b[\w][\w+#.-]{1,32}\b",
        title.lower(),
        flags=re.UNICODE,
    ):
        word = word.strip("._-")

        if (
            len(word) >= 2
            and word not in STOP_WORDS
        ):
            counter[word] += 8

    return [
        word
        for word, _ in counter.most_common(MAX_KEYWORDS)
    ]


# ============================================================
# TAG / CATEGORY DETECTION
# ============================================================

CATEGORY_RULES = {
    "Technology": {
        "technology",
        "software",
        "computer",
        "developer",
        "programming",
        "code",
        "api",
        "linux",
        "windows",
        "hardware",
        "cloud",
    },
    "Gaming": {
        "game",
        "gaming",
        "minecraft",
        "steam",
        "xbox",
        "playstation",
        "unity",
        "unreal",
        "esports",
    },
    "News": {
        "news",
        "breaking",
        "politics",
        "report",
        "journal",
        "headline",
        "latest",
    },
    "Education": {
        "education",
        "school",
        "university",
        "course",
        "tutorial",
        "lesson",
        "learn",
        "study",
    },
    "Science": {
        "science",
        "research",
        "physics",
        "chemistry",
        "biology",
        "space",
        "scientific",
    },
    "Business": {
        "business",
        "company",
        "finance",
        "market",
        "startup",
        "enterprise",
        "investment",
    },
    "Entertainment": {
        "movie",
        "music",
        "video",
        "stream",
        "entertainment",
        "celebrity",
        "tv",
    },
}


def detect_category(
    title: str,
    text: str,
    url: str,
    keywords: List[str],
) -> str:
    combined = " ".join(
        [
            title.lower(),
            text[:12000].lower(),
            url.lower(),
            " ".join(keywords).lower(),
        ]
    )

    best_category = "General"
    best_score = 0

    for category, terms in CATEGORY_RULES.items():
        category_score = 0

        for term in terms:
            if re.search(
                rf"\b{re.escape(term)}\b",
                combined,
            ):
                category_score += 1

        if category_score > best_score:
            best_score = category_score
            best_category = category

    return best_category


def build_tags(
    keywords: List[str],
    category: str,
) -> List[str]:
    tags = []

    if category != "General":
        tags.append(category.lower())

    for keyword in keywords:
        if keyword not in tags:
            tags.append(keyword)

        if len(tags) >= MAX_TAGS:
            break

    return tags


# ============================================================
# AUTHORITY / QUALITY
# ============================================================

HIGH_AUTHORITY_DOMAINS = {
    "gov": 10,
    "edu": 9,
    "github.com": 9,
    "wikipedia.org": 9,
    "google.com": 9,
    "microsoft.com": 9,
    "apple.com": 9,
    "mozilla.org": 8,
    "python.org": 8,
    "npmjs.com": 8,
    "pypi.org": 8,
}

TRUSTED_TLDS = {
    ".gov": 10,
    ".edu": 9,
    ".org": 7,
}

def calculate_authority(url: str) -> int:
    try:
        host = (
            urlparse(url)
            .hostname
            or ""
        ).lower()

        for domain, score in HIGH_AUTHORITY_DOMAINS.items():
            if (
                host == domain
                or host.endswith("." + domain)
            ):
                return score

        for tld, score in TRUSTED_TLDS.items():
            if host.endswith(tld):
                return score

        return 4

    except Exception:
        return 1


def calculate_priority(
    url: str,
    depth: int,
    title: str,
) -> int:
    priority = 0

    if depth == 0:
        priority += 10
    elif depth == 1:
        priority += 7
    elif depth <= 3:
        priority += 4
    else:
        priority += 1

    important_title_words = {
        "home",
        "official",
        "documentation",
        "docs",
        "about",
        "download",
        "news",
    }

    for word in important_title_words:
        if re.search(
            rf"\b{re.escape(word)}\b",
            title.lower(),
        ):
            priority += 1

    return min(priority, 15)


def calculate_score(
    title: str,
    text: str,
    url: str,
    keywords: List[str],
    authority: int,
    priority: int,
) -> float:
    score = 0.0

    if title:
        score += 25

    if len(title) >= 8:
        score += 5

    if len(text) >= 200:
        score += 10

    if len(text) >= 1000:
        score += 8

    if keywords:
        score += min(
            20,
            len(keywords) * 0.8,
        )

    score += authority * 2
    score += priority * 2

    # HTTPS gets a tiny quality bonus.
    if url.lower().startswith("https://"):
        score += 3

    return round(score, 2)


# ============================================================
# DATE DETECTION
# ============================================================

DATE_META_NAMES = {
    "article:published_time",
    "article:modified_time",
    "date",
    "datepublished",
    "publishdate",
    "pubdate",
    "timestamp",
    "dc.date",
}


def extract_date(
    html_content: str,
) -> str:
    try:
        parser = lxml.html.HTMLParser(
            encoding="utf-8"
        )

        doc = lxml.html.fromstring(
            html_content.encode(
                "utf-8",
                errors="ignore",
            ),
            parser=parser,
        )

        nodes = doc.xpath(
            "//meta[@content]/@content"
        )

        for value in nodes:
            value = value.strip()

            if not value:
                continue

            if re.search(
                r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b",
                value,
            ):
                try:
                    parsed = datetime.fromisoformat(
                        value.replace("Z", "+00:00")
                    )

                    if parsed.tzinfo is None:
                        parsed = parsed.replace(
                            tzinfo=timezone.utc
                        )

                    return parsed.isoformat()
                except Exception:
                    match = re.search(
                        r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b",
                        value,
                    )

                    if match:
                        return match.group(0)

        return ""

    except Exception:
        return ""


# ============================================================
# LINKS / IMAGES
# ============================================================

def extract_links_and_images_lxml(
    html_content: str,
    base_url: str,
    visited: Set[str],
    matcher: DynamicPatternMatcher,
) -> Tuple[Set[str], List[str]]:
    child_urls: Set[str] = set()
    image_strings: List[str] = []

    try:
        parser = lxml.html.HTMLParser(
            encoding="utf-8"
        )

        doc = lxml.html.fromstring(
            html_content.encode(
                "utf-8",
                errors="ignore",
            ),
            parser=parser,
        )

    except Exception:
        return child_urls, image_strings

    try:
        doc.make_links_absolute(
            base_url,
            resolve_base_href=True,
        )
    except Exception:
        pass

    for element, attribute, link, _ in doc.iterlinks():
        try:
            if element.tag == "a" and attribute == "href":
                normalized = normalize_url(link)

                if not normalized:
                    continue

                parsed = urlparse(normalized)

                host = parsed.hostname or ""

                if not matcher.is_valid_host(host):
                    continue

                if normalized not in visited:
                    child_urls.add(normalized)

            elif (
                element.tag == "img"
                and attribute == "src"
            ):
                image_url = normalize_url(link)

                if not image_url:
                    continue

                alt_text = (
                    element.get("alt", "").strip()
                    or "No Description Present"
                )

                image_strings.append(
                    f"{image_url}=({alt_text})"
                )

        except Exception:
            continue

    parsed_base = urlparse(base_url)

    parent_path = (
        parsed_base.path.rstrip("/")
    )

    for common in COMMON_PATHS:
        candidate = (
            f"{parsed_base.scheme}://"
            f"{parsed_base.netloc}/"
            f"{common.lstrip('/')}"
        )

        normalized = normalize_url(candidate)

        if (
            normalized
            and normalized not in visited
            and matcher.is_valid_host(
                urlparse(normalized).hostname or ""
            )
        ):
            child_urls.add(normalized)

    return child_urls, image_strings


# ============================================================
# OPENROUTER SUMMARY
# ============================================================

async def summarise_text(
    client: httpx.AsyncClient,
    api_key: str,
    title: str,
    url: str,
    text: str,
) -> str:
    async with llm_semaphore:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        prompt = (
            "You are creating a search-index summary.\n"
            f"Target URL: {url}\n"
            f"Page Title: {title}\n"
            f"Content: {text[:5000]}\n\n"
            "Return one clear factual description of what the page is "
            "about in 15 words or fewer. "
            "Do not mention that you are an AI. "
            "Return only the summary."
        )

        payload = {
            "model": "nvidia/nemotron-3-nano-30b-a3b",
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.15,
            "max_tokens": 40,
        }

        for attempt in range(3):
            try:
                response = await client.post(
                    MODEL_URL,
                    headers=headers,
                    json=payload,
                    timeout=20.0,
                )

                if response.status_code == 200:
                    data = response.json()

                    content = (
                        data
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )

                    if content:
                        return content

                    return ""

                if response.status_code == 429:
                    await asyncio.sleep(
                        2 ** attempt
                    )
                    continue

                return ""

            except Exception:
                if attempt == 2:
                    return ""

                await asyncio.sleep(1.5)

        return ""


# ============================================================
# WORKER
# ============================================================

async def worker(
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    api_key: str,
    visited: Set[str],
    all_jobs: List[Dict[str, Any]],
    executor: ProcessPoolExecutor,
    matcher: DynamicPatternMatcher,
    counter_lock: asyncio.Lock,
) -> None:
    loop = asyncio.get_running_loop()

    while True:
        url, depth = await queue.get()

        try:
            # Stop creating more documents after the configured limit.
            async with counter_lock:
                if len(all_jobs) >= MAX_TARGET_URLS:
                    continue

                normalized_url = normalize_url(url)

                if not normalized_url:
                    continue

                parsed = urlparse(normalized_url)

                host = parsed.hostname or ""

                if not matcher.is_valid_host(host):
                    continue

                if normalized_url in visited:
                    continue

                visited.add(normalized_url)

            # --------------------------------------------------------
            # Fetch
            # --------------------------------------------------------

            try:
                async with client.stream(
                    "GET",
                    normalized_url,
                    follow_redirects=True,
                    timeout=REQUEST_TIMEOUT,
                ) as response:

                    if response.status_code != 200:
                        continue

                    content_type = (
                        response.headers
                        .get("content-type", "")
                        .lower()
                    )

                    if (
                        "text/html" not in content_type
                        and "application/xhtml+xml"
                        not in content_type
                    ):
                        continue

                    content_length = response.headers.get(
                        "content-length"
                    )

                    if content_length:
                        try:
                            if (
                                int(content_length)
                                > MAX_PAGE_BYTES
                            ):
                                continue
                        except ValueError:
                            pass

                    chunks = []
                    total_bytes = 0

                    async for chunk in response.aiter_bytes(
                        chunk_size=65536
                    ):
                        total_bytes += len(chunk)

                        if total_bytes > MAX_PAGE_BYTES:
                            chunks = []
                            break

                        chunks.append(chunk)

                    if not chunks:
                        continue

                    html_bytes = b"".join(chunks)

                    final_url = normalize_url(
                        str(response.url)
                    )

                    if not final_url:
                        continue

            except Exception:
                continue

            if len(html_bytes) > MAX_PAGE_BYTES:
                continue

            html_content = html_bytes.decode(
                "utf-8",
                errors="ignore",
            )

            # --------------------------------------------------------
            # Parse page
            # --------------------------------------------------------

            title, body_text, meta = (
                await loop.run_in_executor(
                    executor,
                    clean_html_lxml,
                    html_content,
                )
            )

            if len(body_text) < MIN_TEXT_LENGTH:
                continue

            snippet = (
                get_first_four_sentences(
                    body_text
                )
            )

            # If there is a meta description and it is
            # better than our extracted snippet, preserve it.
            description = meta.get(
                "description",
                "",
            ).strip()

            if (
                description
                and len(description) >= 40
            ):
                snippet = description[:MAX_SNIPPET_LENGTH].strip()

            # --------------------------------------------------------
            # Images / links
            # --------------------------------------------------------

            child_urls, parsed_images = (
                await loop.run_in_executor(
                    executor,
                    extract_links_and_images_lxml,
                    html_content,
                    final_url,
                    visited,
                    matcher,
                )
            )

            # --------------------------------------------------------
            # Deterministic index signals
            # --------------------------------------------------------

            keywords = extract_keywords(
                title,
                body_text,
                meta.get("keywords", ""),
            )

            category = detect_category(
                title,
                body_text,
                final_url,
                keywords,
            )

            tags = build_tags(
                keywords,
                category,
            )

            authority = calculate_authority(
                final_url
            )

            priority = calculate_priority(
                final_url,
                depth,
                title,
            )

            score = calculate_score(
                title,
                body_text,
                final_url,
                keywords,
                authority,
                priority,
            )

            detected_date = extract_date(
                html_content
            )

            # --------------------------------------------------------
            # Optional semantic summary
            # --------------------------------------------------------

            ai_summary = await summarise_text(
                client,
                api_key,
                title,
                final_url,
                body_text,
            )

            # --------------------------------------------------------
            # Final search document
            # --------------------------------------------------------

            document = {
                "title": title,
                "url": final_url,

                "summary": ai_summary,
                "snippet": snippet,

                "description": description,

                "keywords": keywords,
                "tags": tags,
                "category": category,

                "authority": authority,
                "priority": priority,
                "score": score,

                "popularity": 0,

                "date": detected_date,

                "language": meta.get(
                    "language",
                    "",
                ),

                "images": parsed_images[:50],

                "depth": depth,

                "indexedAt": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            async with counter_lock:
                if len(all_jobs) < MAX_TARGET_URLS:
                    all_jobs.append(document)

                    print(
                        f"[Indexed {len(all_jobs):>5}/{MAX_TARGET_URLS}] "
                        f"[depth={depth:>2}] "
                        f"[authority={authority}] "
                        f"{title[:90]}"
                    )

            # --------------------------------------------------------
            # Crawl child pages
            # --------------------------------------------------------

            if depth < MAX_DEPTH:
                async with counter_lock:
                    limit_reached = (
                        len(all_jobs)
                        >= MAX_TARGET_URLS
                    )

                if not limit_reached:
                    for child in child_urls:
                        if child == final_url:
                            continue

                        if child in visited:
                            continue

                        await queue.put(
                            (child, depth + 1)
                        )

        finally:
            queue.task_done()


# ============================================================
# PERIODIC SAVE
# ============================================================

async def periodic_saver(
    all_jobs: List[Dict[str, Any]],
    interval: float = 10.0,
):
    while True:
        try:
            await asyncio.sleep(interval)

            snapshot = list(
                all_jobs[:MAX_TARGET_URLS]
            )

            temporary_file = "data.json.tmp"

            with open(
                temporary_file,
                "w",
                encoding="utf-8",
            ) as fp:
                json.dump(
                    snapshot,
                    fp,
                    indent=2,
                    ensure_ascii=False,
                )

            os.replace(
                temporary_file,
                "data.json",
            )

            print(
                f"[Auto Save] {len(snapshot)} documents"
            )

        except asyncio.CancelledError:
            break

        except Exception as exc:
            print(
                f"[Backup System] Auto-save skipped: {exc}"
            )


# ============================================================
# INPUT URL PARSING
# ============================================================

def parse_input_urls(
    file_path: str,
) -> Tuple[List[str], List[str]]:
    seeds: List[str] = []
    discovered_hosts: List[str] = []

    if not os.path.exists(file_path):
        return seeds, discovered_hosts

    with open(
        file_path,
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "://" not in line:
                line = "https://" + line

            normalized = normalize_url(line)

            if not normalized:
                continue

            parsed = urlparse(normalized)

            hostname = parsed.hostname

            if not hostname:
                continue

            seeds.append(normalized)

            discovered_hosts.append(
                hostname
            )

            parts = hostname.split(".")

            if len(parts) >= 2:
                base_domain = ".".join(
                    parts[-2:]
                )

                discovered_hosts.append(
                    f"*.{base_domain}"
                )

    return seeds, discovered_hosts


# ============================================================
# MAIN
# ============================================================

async def main() -> None:
    api_key = os.getenv("OPENROUTER")

    if not api_key:
        raise ValueError(
            "Missing OPENROUTER environment variable."
        )

    # Domains you explicitly allow.
    DOMAINS = [
        ".gov",
        ".google",
        ".github.io",
        "*.google.com",
    ]

    initial_seeds, dynamic_hosts = (
        parse_input_urls("URLs.txt")
    )

    matcher = DynamicPatternMatcher(
        DOMAINS,
        dynamic_hosts,
    )

    visited: Set[str] = set()

    results: List[Dict[str, Any]] = []

    counter_lock = asyncio.Lock()

    queue: asyncio.Queue = asyncio.Queue()

    # ------------------------------------------------------------
    # Built-in seeds
    # ------------------------------------------------------------

    for pattern in DOMAINS:
        if pattern == ".google":
            initial_seeds.extend(
                [
                    "https://google.com",
                    "https://blog.google",
                    "https://gemini.google.com",
                ]
            )

    # ------------------------------------------------------------
    # Queue initial seeds
    # ------------------------------------------------------------

    for seed in initial_seeds:
        normalized = normalize_url(seed)

        if not normalized:
            continue

        host = (
            urlparse(normalized)
            .hostname
            or ""
        )

        if not matcher.is_valid_host(host):
            continue

        await queue.put(
            (normalized, 0)
        )

        for common in COMMON_PATHS:
            child = normalize_url(
                f"{normalized.rstrip('/')}/"
                f"{common.lstrip('/')}"
            )

            if child:
                await queue.put(
                    (child, 0)
                )

    executor = ProcessPoolExecutor()

    saver_task = asyncio.create_task(
        periodic_saver(
            results,
            10.0,
        )
    )

    try:
        async with httpx.AsyncClient(
            limits=LIMITS,
            headers=HEADERS,
        ) as client:

            workers = [
                asyncio.create_task(
                    worker(
                        queue,
                        client,
                        api_key,
                        visited,
                        results,
                        executor,
                        matcher,
                        counter_lock,
                    )
                )
                for _ in range(NUM_WORKERS)
            ]

            await queue.join()

            for worker_task in workers:
                worker_task.cancel()

            await asyncio.gather(
                *workers,
                return_exceptions=True,
            )

    finally:
        saver_task.cancel()

        try:
            await saver_task
        except asyncio.CancelledError:
            pass

        executor.shutdown(
            wait=True
        )

    # ------------------------------------------------------------
    # Final ranking/index cleanup
    # ------------------------------------------------------------

    # Remove duplicate URLs if redirects/canonicalization
    # resulted in duplicates.
    unique_documents: Dict[str, Dict[str, Any]] = {}

    for document in results:
        url = document.get("url", "")

        if not url:
            continue

        existing = unique_documents.get(url)

        if existing is None:
            unique_documents[url] = document
            continue

        if (
            float(document.get("score", 0))
            > float(existing.get("score", 0))
        ):
            unique_documents[url] = document

    final_results = list(
        unique_documents.values()
    )

    # Highest base quality first.
    final_results.sort(
        key=lambda item: (
            float(item.get("score", 0)),
            int(item.get("authority", 0)),
            int(item.get("priority", 0)),
        ),
        reverse=True,
    )

    with open(
        "data.json",
        "w",
        encoding="utf-8",
    ) as fp:
        json.dump(
            final_results[:MAX_TARGET_URLS],
            fp,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 70)
    print("ZYPERSEARCH CRAWLER COMPLETE")
    print("=" * 70)
    print(
        f"Indexed documents : {len(final_results[:MAX_TARGET_URLS])}"
    )
    print(
        f"Visited URLs      : {len(visited)}"
    )
    print(
        f"Maximum documents : {MAX_TARGET_URLS}"
    )
    print(
        f"Maximum depth     : {MAX_DEPTH}"
    )
    print(
        "Output             : data.json"
    )
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
