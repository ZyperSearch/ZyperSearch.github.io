# -------------------------------------------------
# Crawl a set of seed URLs, follow internal links,
# collect page summaries, and store results in data.json
# -------------------------------------------------

import asyncio
import json
import os
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Configuration ---------------------------------------------------------
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
# 2️⃣ Common directory patterns we want to *actively* explore
# ----------------------------------------------------------------------
COMMON_PATHS = [
    "about", "contact", "blog", "news", "products", "shop", "gallery",
    "forum", "community", "resources", "help", "support", "careers",
    "pricing", "login", "signup", "dashboard", "profile"
]

# ----------------------------------------------------------------------
# 3️⃣ Model endpoint ----------------------------------------------------
# ----------------------------------------------------------------------
MODEL_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen3.6-35B-A3B"

# ----------------------------------------------------------------------
# 4️⃣ HTTP Headers (feel free to customise)
# ----------------------------------------------------------------------
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; CrawlerSummariser/1.0; +https://example.com/bot)",
    "Referer": "*/*",
    "accept-language": "en-US,en;q=0.5",
    "accept-encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ----------------------------------------------------------------------
# 5️⃣ Respect robots.txt? ------------------------------------------------
# ----------------------------------------------------------------------
RESPECT_ROBOTS = True    # set False to ignore robots.txt (dangerous on big crawls)
ROBOTS_PATH = "/robots.txt"

# ----------------------------------------------------------------------
# 6️⃣ Throttling ---------------------------------------------------------
# ----------------------------------------------------------------------
LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=5)

# ----------------------------------------------------------------------
# 7️⃣ How deep can we go from the seed(s)? -------------------------------
# ----------------------------------------------------------------------
MAX_DEPTH = 2   # 0 = only seeds, 1 = seeds + direct children, 2 = children of children, …

# ----------------------------------------------------------------------
# Helper: tiny friendly robots.txt parser (does NOT implement full spec) --
# ----------------------------------------------------------------------
def fetch_robots(url: str) -> str:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}{ROBOTS_PATH}"
    try:
        r = httpx.get(robots_url, timeout=5.0)
        r.raise_for_status()
        return r.text
    except Exception:
        # Either the site has no robots.txt or we cannot fetch it – treat as empty
        return ""

def is_allowed_by_robots(url: str, robots_txt: str) -> bool:
    """
    Very naïve check – looks for lines like:
        Disallow: /path/
        Allow: /another/
    Returns True if the URL path is not explicitly disallowed.
    """
    if not robots_txt:
        return True
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") + "/"   # ensure trailing slash
    for line in robots_txt.splitlines():
        line = line.strip().lower()
        if line.startswith("disallow:"):
            # Remove the keyword and any leading spaces
            _, value = line.split(":", 1)
            if value.strip() and path.startswith(value.strip()):
                return False        # Simple allow handling (not mandatory)
        if line.startswith("allow:"):
            _, value = line.split(":", 1)
            if value.strip() and path.startswith(value.strip()):
                return True
    return True

# ----------------------------------------------------------------------
# 8️⃣ HTML cleaning -------------------------------------------------------
# ----------------------------------------------------------------------
def clean_html(html_content: str) -> tuple[str, str]:
    """Strip unwanted tags and extract a readable title + body text."""
    soup = BeautifulSoup(html_content, "html.parser")
    for el in soup(["script", "style", "header", "footer", "nav", "aside", "svg"]):
        el.decompose()
    title_tag = soup.title
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    body_text = " ".join(soup.get_text().split())
    return title, body_text

# ----------------------------------------------------------------------
# 9️⃣ Summarisation via HuggingFace ---------------------------------------
# ----------------------------------------------------------------------
async def summarise_text(client: httpx.AsyncClient, text: str) -> str:
    """
    Sends a short prompt to the HuggingFace inference API and returns the    generated summary (up to 40 tokens, forced to ~15 words by the prompt).
    """
    prompt = (
        "You are a professional summarizer. Summarize the following text "
        "in *exactly* 15 words. Return only the summary, nothing else.\n\n"
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
        elif resp.status_code == 503:
            return "Model is loading…"
        else:
            return f"API error ({resp.status_code})"
    except Exception as e:
        return f"Network error: {e}"

# ----------------------------------------------------------------------
# 10️⃣ Crawl a single URL (seed or discovered) ---------------------------
# ----------------------------------------------------------------------
async def crawl_url(
    client: httpx.AsyncClient,
    url: str,
    current_depth: int,
    visited: set,
    all_jobs: list,
    robots_cache: dict,
) -> None:
    """
    Recursively fetches a URL, extracts links, and schedules further crawling
    up to `MAX_DEPTH`.  Summaries are appended to `all_jobs`.
    """
    # Normalise the URL (resolve relative scheme/host if needed)
    parsed = urlparse(url)
    norm_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    norm_url = norm_url.rstrip("/")

    if norm_url in visited:
        return
    visited.add(norm_url)

    # ------------------- Robots.txt handling ---------------------------
    if RESPECT_ROBOTS:
        robots_url = f"{parsed.scheme}://{parsed.netloc}{ROBOTS_PATH}"
        robots_txt = robots_cache.get(robots_url)
        if robots_txt is None:
            robots_txt = fetch_robots(parsed.scheme, parsed.netloc)
            robots_cache[robots_url] = robots_txt
        if not is_allowed_by_robots(norm_url, robots_txt):
            print(f"[skip] Disallowed by robots.txt → {url}")
            return
        # Quick check for any `Disallow:` that directly matches the URL        if any(line.lower().startswith("disallow:") for line in robots_txt.splitlines()):
            # Scan lines again to see if the specific path is blocked
            for line in robots_txt.splitlines():
                if line.lower().startswith("disallow:"):
                    _, target = line.split(":", 1)
                    if norm_url.startswith(target.strip()):
                        print(f"[skip] Disallowed by robots.txt → {url}")
                        return

    # ------------------- HTTP request ---------------------------------
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10.0)
    except Exception as e:
        print(f"[error] GET failed for {url}: {e}")
        return

    if resp.status_code != 200:
        print(f"[skip] Non‑200 ({resp.status_code}) for {url}")
        return

    # ------------------- Parse & clean ---------------------------------
    title, body_text = clean_html(resp.text)

    # If there isn’t enough content to summarise, fall back to a short note
    if len(body_text) < 10:
        ai_summary = "Insufficient text for a meaningful summary."
    else:
        ai_summary = await summarise_text(client, body_text)

    # Append result (same shape as original script)
    all_jobs.append(
        {
            "title": title,
            "url": str(resp.url),
            "summary": ai_summary,
            "snippet": body_text[:300],
        }
    )
    print(f"[done] {url} → {title[:50]}{'...' if len(title)>50 else ''}")

    # ------------------- Discover & schedule child links ---------------
    if current_depth < MAX_DEPTH:
        # Grab all <a href> links that look internal (same host) but *not* mailto:, #
        # We also add URLs derived from COMMON_PATHS if the parent URL ends with '/'.
        soup = BeautifulSoup(resp.text, "html.parser")
        anchors = soup.find_all("a", href=True)
        child_urls = set()

        for a in anchors:
            href = a["href"]
            # Resolve relative urls
            link = urljoin(resp.url, href)

            # Strip fragment & query for a canonical form
            parsed_link = urlparse(link)
            canonical = parsed_link._replace(fragment="", query="").geturl()

            # Keep only URLs that share the *same* netloc as the seed (internal links)
            if parsed_link.netloc != parsed.netloc:
                continue

            # Normalise again (strip trailing slash for comparison)
            canonical = canonical.rstrip("/")

            # Avoid duplicates & avoid endless loops
            if canonical not in visited:
                child_urls.add(canonical)

        # Add explicitly known common directories if they appear as sub‑paths
        # (e.g., https://example.com/blog/… => we treat 'blog' as a known dir)
        parsed_parent = urlparse(resp.url)
        parent_path = parsed_parent.path.rstrip("/")
        for common in COMMON_PATHS:
            candidate = f"{parent_path}/{common}".replace("//", "/")
            cand_canon = candidate.rstrip("/")
            if cand_canon not in visited and cand_canon.startswith(parsed_parent.scheme + "://" + parsed_parent.netloc):
                child_urls.add(cand_canon)

        # Schedule crawling of discovered URLs (recursively)
        tasks = [
            crawl_url(client, u, current_depth + 1, visited, all_jobs, robots_cache)
            for u in child_urls
        ]
        if tasks:
            await asyncio.gather(*tasks)


def parse_seeds_as_domains(seeds: list) -> list:
    """
    Convert raw strings into a list of base URLs (scheme+netloc) that we can
    later expand with COMMON_PATHS.
    """
    out = []
    for s in seeds:
        parsed = urlparse(s)
        base = f"{parsed.scheme}://{parsed.netloc}"
        out.append(base.rstrip("/"))
    return out


# ----------------------------------------------------------------------
# 11️⃣ Entry point ---------------------------------------------------------
# ----------------------------------------------------------------------
async def main():
    # ------------------------------------------------------------------
    # Prepare data structures
    # ------------------------------------------------------------------
    visited: set = set()
    results: list = []
    robots_cache: dict = {}

    # Normalise seeds to base domains (so we can later append /about, /blog, …)
    base_domains = parse_seeds_as_domains(SEEDS)

    # Create a single httpx client that will be shared across all requests    async with httpx.AsyncClient(limits=LIMITS, headers=HEADERS) as client:
        # Kick off crawling for each seed domain
        crawl_tasks = []
        for base in base_domains:
            # Start with the plain base URL (e.g., https://google.com)
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
            # Also start crawling the common entry points that belong to that base
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

        # Run them all concurrently (bounded by client limits)
        await asyncio.gather(*crawl_tasks)

    # ------------------------------------------------------------------
    # Store results    # ------------------------------------------------------------------
    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
    print(f"\n✅ Crawl complete – {len(results)} pages summarised → data.json")


# ----------------------------------------------------------------------
# 12️⃣ Run -----------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
