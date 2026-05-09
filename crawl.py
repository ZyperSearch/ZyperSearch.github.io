# -------------------------------------------------------
# Crawl a set of seed URLs, follow internal links,
# collect page summaries, and store results in data.json
# -------------------------------------------------------

import asyncio
import json
import os
from urllib.parse import urljoin, urlparse
from typing import Any, Dict, List, Set, Tuple

import httpx
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

SEEDS = [
    "https://google.com", "https://bing.com", "https://yahoo.com", "https://duckduckgo.com", "https://baidu.com",
    "https://yandex.com", "https://wikipedia.org", "https://britannica.com", "https://archive.org", "https://quora.com",
    "https://medium.com", "https://substack.com", "https://wikihow.com", "https://stackexchange.com", "https://investopedia.com",
    "https://imdb.com", "https://bbc.com", "https://nytimes.com", "https://reuters.com", "https://theguardian.com",
    "https://cnn.com", "https://aljazeera.com", "https://bloomberg.com", "https://wsj.com", "https://forbes.com",
    "https://economist.com", "https://amazon.com", "https://ebay.com", "https://walmart.com", "https://target.com",
    "https://homedepot.com", "https://bestbuy.com", "https://costco.com", "https://etsy.com", "https://wayfair.com",
    "https://ikea.com", "https://alibaba.com", "https://aliexpress.com", "https://rakuten.co.jp", "https://mercadolivre.com.br",
    "https://jd.com", "https://shopify.com", "https://zillow.com", "https://realtor.com", "https://autotrader.com",
    "https://craigslist.org", "https://facebook.com", "https://instagram.com", "https://x.com", "https://linkedin.com",
    "https://reddit.com", "https://pinterest.com", "https://tumblr.com", "https://discord.com", "https://tiktok.com",
    "https://snapchat.com", "https://youtube.com", "https://vimeo.com", "https://twitch.tv", "https://netflix.com",
    "https://spotify.com", "https://soundcloud.com", "https://flickr.com", "https://behance.net", "https://dribbble.com",
    "https://deviantart.com", "https://apple.com", "https://microsoft.com", "https://cloudflare.com", "https://github.com",
    "https://gitlab.com", "https://bitbucket.org", "https://sourceforge.net", "https://npmjs.com", "https://pypi.org",
    "https://docker.com", "https://aws.amazon.com", "https://azure.microsoft.com", "https://cloud.google.com",
    "https://digitalocean.com", "https://heroku.com", "https://netlify.com", "https://vercel.com", "https://wordpress.org",
    "https://wix.com", "https://squarespace.com", "https://godaddy.com", "https://bluehost.com", "https://namecheap.com",
    "https://weather.com", "https://accuweather.com", "https://wunderground.com", "https://nationalgeographic.com",
    "https://discovery.com", "https://nasa.gov", "https://nih.gov", "https://cdc.gov", "https://who.int", "https://un.org",
    "https://whitehouse.gov", "https://europa.eu", "https://gov.uk", "https://ca.gov", "https://tokyo.jp",
    "https://booking.com", "https://expedia.com", "https://tripadvisor.com", "https://airbnb.com", "https://kayak.com",
    "https://skyscanner.net", "https://hotels.com", "https://yelp.com", "https://foursquare.com", "https://opentable.com",
    "https://uber.com", "https://lyft.com", "https://doordash.com", "https://instacart.com", "https://grubhub.com",
    "https://nike.com", "https://adidas.com", "https://zara.com", "https://h_m.com", "https://uniqlo.com",
    "https://gap.com", "https://nordstrom.com", "https://macys.com", "https://sephora.com", "https://ulta.com",
    "https://espn.com", "https://bleacherreport.com", "https://cbssports.com", "https://nfl.com", "https://nba.com",
    "https://mlb.com", "https://fifa.com", "https://olympics.com", "https://strava.com", "https://fitbit.com",
    "https://coursera.org", "https://udemy.com", "https://edx.org", "https://khanacademy.org", "https://duolingo.com",
    "https://codecademy.com", "https://skillshare.com", "https://masterclass.com", "https://ted.com", "https://grammarly.com",
    
    # --- ADDED 100 MORE (kept for context) ---
    # Finance & Banking
    "https://paypal.com", "https://stripe.com", "https://visa.com", "https://mastercard.com", "https://vanguard.com",
    "https://fidelity.com", "https://morningstar.com", "https://marketwatch.com", "https://tradingview.com",
    "https://coinbase.com", "https://binance.com", "https://robinhood.com", "https://mint.intuit.com",
    "https://nerdwallet.com", "https://creditkarma.com",
    
    # Gaming & Entertainment
    "https://steampowered.com", "https://epicgames.com", "https://ign.com", "https://gamespot.com",
    "https://roblox.com", "https://riotgames.com", "https://nintendo.com", "https://playstation.com",
    "https://xbox.com", "https://unity.com", "https://unrealengine.com", "https://twitch.tv",
    "https://rottentomatoes.com", "https://metacritic.com",
    
    # Health & Wellness
    "https://mayoclinic.org", "https://webmd.com", "https://healthline.com", "https://psychologytoday.com",
    "https://medscape.com", "https://everydayhealth.com", "https://medicalnewstoday.com",
    "https://sleepfoundation.org", "https://headspace.com", "https://calm.com", "https://myfitnesspal.com",
    "https://healthgrades.com", "https://zocdoc.com", "https://drugs.com",
    # SaaS & Productivity
    "https://salesforce.com", "https://slack.com", "https://zoom.us", "https://trello.com",
    "https://notion.so", "https://canva.com", "https://monday.com", "https://asana.com",
    "https://dropbox.com", "https://evernote.com", "https://microsoft365.com", "https://google.workspace",
    "https://calendly.com", "https://hubspot.com",
    
    # Tech News & Blogs
    "https://wired.com", "https://techcrunch.com", "https://theverge.com", "https://engadget.com",
    "https://gizmodo.com", "https://arstechnica.com", "https://cnet.com", "https://zdnet.com",
    "https://venturebeat.com", "https://mashable.com", "https://digitaltrends.com",
    "https://tomshardware.com", "https://9to5mac.com", "https://androidcentral.com",
    
    # Academic & Research
    "https://jstor.org", "https://researchgate.net", "https://academia.edu", "https://mit.edu",
    "https://stanford.edu", "https://harvard.edu", "https://ox.ac.uk", "https://cam.ac.uk",
    "https://nature.com", "https://sciencemag.org", "https://arxiv.org", "https://scholar.google.com",
    "https://springer.com", "https://wiley.com", "https://elsevier.com",
    
    # General News & Opinion
    "https://vox.com", "https://huffpost.com", "https://slate.com", "https://salon.com",
    "https://theatlantic.com", "https://newyorker.com", "https://time.com", "https://usnews.com",
    "https://politico.com", "https://axios.com", "https://dailymail.co.uk", "https://foxnews.com",
    "https://msnbc.com", "https://usatoday.com", "https://independent.co.uk",
     # International Orgs & Gov
    "https://imf.org", "https://worldbank.org", "https://wto.org", "https://nato.int",
    "https://redcross.org", "https://amnesty.org", "https://greenpeace.org", "https://icrc.org",
    "https://wmo.int", "https://unesco.org",
    
    # Lifestyle & Misc
    "https://allrecipes.com", "https://foodnetwork.com", "https://bonappetit.com",
    "https://goodhousekeeping.com", "https://realsimple.com", "https://apartmenttherapy.com",
    "https://dwell.com"
]

# ----------------------------------------------------------------------
# 2️⃣ Common directory patterns we want to actively explore
# ----------------------------------------------------------------------
COMMON_PATHS: List[str] = [
]

# ----------------------------------------------------------------------
# 3️⃣ Model endpoint
# ----------------------------------------------------------------------
MODEL_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen3.6-35B-A3B"

# ----------------------------------------------------------------------
# 4️⃣ HTTP Headers (feel free to customise)
# ----------------------------------------------------------------------
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (compatible; CrawlerSummariser/1.0; +https://example.com/bot)"
    ),
    "Referer": "*/*",
    "accept-language": "en-US,en;q=0.5",
    "accept-encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ----------------------------------------------------------------------
# 5️⃣ Respect robots.txt
# ----------------------------------------------------------------------
RESPECT_ROBOTS = False
ROBOTS_PATH = "/robots.txt"
LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
MAX_DEPTH = 80   # 0 = only seeds, 1 = seeds + direct children, 2 = grandchildren …


def fetch_robots(scheme: str, host: str) -> str:
    robots_url = f"{scheme}://{host}{ROBOTS_PATH}"
    try:
        r = httpx.get(robots_url, timeout=5.0)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def is_allowed_by_robots(url: str, robots_txt: str) -> bool:
    """
    Very naïve check for `Disallow:` lines that start with the URL’s path.
    Returns True if the URL is *not* blocked.
    """
    if not robots_txt:
        return True

    parsed = urlparse(url)
    path = parsed.path or "/"

    for line in robots_txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("disallow:"):
            _, dis = line.split(":", 1)
            dis = dis.strip()
            # An empty Disallow means allow everything
            if not dis:
                continue
            # Ensure dis starts with a slash for comparison
            if not dis.startswith("/"):
                dis = "/" + dis
            if path.startswith(dis):
                return False
    return True


# ----------------------------------------------------------------------
# 8️⃣ HTML cleaning
# ----------------------------------------------------------------------
def clean_html(html_content: str) -> tuple[str, str]:
    """Strip unwanted tags and return a (title, body_text) pair."""
    soup = BeautifulSoup(html_content, "html.parser")
    for element in soup(["script", "style", "header", "footer", "nav", "aside", "svg"]):
        element.decompose()
    title_tag = soup.title
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    body_text = " ".join(soup.get_text().split())
    return title, body_text


# ----------------------------------------------------------------------
# 9️⃣ Summarisation via HuggingFace
# ----------------------------------------------------------------------
async def summarise_text(client: httpx.AsyncClient, text: str) -> str:
    """
    Sends a short prompt to the HuggingFace inference API and returns a
    15‑word summary (or a fallback message on error).
    """
    prompt = (
        "You are a professional summarizer. Summarize the following text "
        "in exactly 15 words. Return only the summary, nothing else.\n\n"
        f"{text}"
    )
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 40,
            "return_full_text": False,
            "stop": ["\n"],
        },
    }

    try:
        resp = await client.post(MODEL_URL, json=payload, timeout=20.0)
        if resp.status_code == 200:
            data = resp.json()
            result = data[0].get("generated_text", "").strip()
            return result if result else "No summary generated."
        if resp.status_code == 503:
            return "Model is loading…"
        return f"API error ({resp.status_code})"
    except Exception as exc:               # pragma: no cover – defensive
        return f"Network error: {exc}"


# ----------------------------------------------------------------------
# 10️⃣ Crawl a single URL (seed or discovered)
# ----------------------------------------------------------------------
async def crawl_url(
    client: httpx.AsyncClient,
    url: str,
    current_depth: int,
    visited: Set[str],
    all_jobs: List[Dict[str, Any]],
    robots_cache: Dict[str, str],
) -> None:
    """
    Fetch `url`, parse its content, summarise it, and (if depth < MAX_DEPTH)
    schedule discovered internal links for further crawling.
    """

    # -------------------------------------------------------------------------
    # Normalise URL (strip query/fragment, enforce trailing slash consistency)
    # -------------------------------------------------------------------------
    parsed = urlparse(url)
    norm_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    norm_url = norm_url.rstrip("/")

    if norm_url in visited:
        return
    visited.add(norm_url)

    # ------------------- robots.txt handling ---------------------------
    host = parsed.netloc
    if RESPECT_ROBOTS:
        robots_url = f"{parsed.scheme}://{host}{ROBOTS_PATH}"
        robots_txt = robots_cache.get(robots_url)
        if robots_txt is None:
            robots_txt = fetch_robots(parsed.scheme, host)
            robots_cache[robots_url] = robots_txt
        if not is_allowed_by_robots(norm_url, robots_txt):
            print(f"[skip] Disallowed by robots.txt → {url}")
            return

    # ------------------- HTTP request ---------------------------------
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10.0)
    except Exception as exc:  # pragma: no cover – defensive
        print(f"[error] GET failed for {url}: {exc}")
        return

    if resp.status_code != 200:
        print(f"[skip] Non‑200 ({resp.status_code}) for {url}")
        return

    # ------------------- Parse & clean ---------------------------------
    title, body_text = clean_html(resp.text)

    # Summarise – fall back if there isn’t enough text
    if len(body_text) < 10:
        ai_summary = "Insufficient text for a meaningful summary."
    else:
        ai_summary = await summarise_text(client, body_text)

    # Store result (same shape as the original script)
    all_jobs.append(
        {
            "title": title,
            "url": str(resp.url),
            "summary": ai_summary,
            "snippet": body_text[:300],
        }
    )
    print(f"[done] {url} → {title[:50]}{'...' if len(title) > 50 else ''}")

    # ------------------------------------------------------------------
    # Schedule children if we have not reached MAX_DEPTH yet
    # ------------------------------------------------------------------
    if current_depth >= MAX_DEPTH:
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    anchors = soup.find_all("a", href=True)
    child_urls: Set[str] = set()

    for a in anchors:
        href = a["href"]
        # Ensure we pass strings to urljoin – httpx.URL isn't a plain str
        link = urljoin(str(resp.url), href)
        parsed_link = urlparse(link)

        # Keep only URLs that share the same host (internal links only)
        if parsed_link.netloc != parsed.netloc:
            continue

        # Normalise (drop query string & fragment) safely
        canonical = parsed_link._replace(
            fragment=parsed_link.fragment or "",
            query=parsed_link.query or "",
        ).geturl().rstrip("/")
        if canonical not in visited:
            child_urls.add(canonical)

    # ------------------------------------------------------------------------
    # Also explicitly enqueue common directory paths that belong to this host
    # ------------------------------------------------------------------------
    parent_path = parsed.path.rstrip("/")
    for common in COMMON_PATHS:
        candidate = f"{parent_path}/{common}".replace("//", "/")
        cand_canon = candidate.rstrip("/")
        # Only keep candidates that really belong to the same host
        cand_parsed = urlparse(cand_canon)
        if (
            cand_parsed.netloc == parsed.netloc
            and cand_canon not in visited
            and cand_canon.startswith(f"{parsed.scheme}://{parsed.netloc}/")
        ):
            child_urls.add(cand_canon)

    # Schedule the newly discovered URLs recursively
    if child_urls:
        await asyncio.gather(
            *[
                crawl_url(
                    client,
                    url=u,
                    current_depth=current_depth + 1,
                    visited=visited,
                    all_jobs=all_jobs,
                    robots_cache=robots_cache,
                )
                for u in child_urls
            ]
        )


def parse_seeds_as_domains(seeds: List[str]) -> List[str]:
    """
    Turn each seed string into a plain base URL (`scheme://netloc`).
    This is the entry point for the crawler.
    """
    bases = []
    for s in seeds:
        parsed = urlparse(s)
        bases.append(f"{parsed.scheme}://{parsed.netloc}".rstrip("/",":"))
    return bases


# ----------------------------------------------------------------------
# 11️⃣ Entry point
# ----------------------------------------------------------------------
async def main() -> None:
    # ------------------------------------------------------------------
    # Data structures
    # ------------------------------------------------------------------
    visited: Set[str] = set()
    results: List[Dict[str, Any]] = []
    robots_cache: Dict[str, str] = {}

    # Normalise seeds → base domains (e.g. https://google.com)
    base_domains = parse_seeds_as_domains(SEEDS)

    # ------------------------------------------------------------------
    # Shared HTTP client
    # ------------------------------------------------------------------
    async with httpx.AsyncClient(limits=LIMITS, headers=HEADERS) as client:
        # Kick‑off crawling for each base domain and its common entry points
        crawl_tasks = []

        for base in base_domains:
            # 1️⃣ Crawl the base URL itself
            crawl_tasks.append(
                crawl_url(
                    client,
                    url=base,
                    current_depth=0,
                    visited=visited,
                    all_jobs=results,
                    robots_cache=robots_cache,
                )
            )

            # 2️⃣ Crawl every common directory under this base
            for common in COMMON_PATHS:
                candidate = f"{base.rstrip('/')}/{common}"
                crawl_tasks.append(
                    crawl_url(
                        client,
                        url=candidate,
                        current_depth=0,
                        visited=visited,
                        all_jobs=results,
                        robots_cache=robots_cache,
                    )
                )

        # Run all crawl coroutines concurrently (bounded by client limits)
        await asyncio.gather(*crawl_tasks)

    # ------------------------------------------------------------------
    # Persist the collected data
    # ------------------------------------------------------------------
    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2, ensure_ascii=False)
    print(f"\n✅ Crawl complete – {len(results)} pages summarised → data.json")


# ----------------------------------------------------------------------
# 12️⃣ Run
# ----------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
