import asyncio
import json
import os
import re
from urllib.parse import urljoin, urlparse
from typing import Any, Dict, List, Set, Tuple
from concurrent.futures import ProcessPoolExecutor

import httpx
import lxml.html

COMMON_PATHS: List[str] = []
MODEL_URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; CrawlerSummariser/2.0; +https://example.com/bot)",
    "Referer": "*/*",
    "accept-language": "en-US,en;q=0.5",
    "accept-encoding": "gzip, deflate",
    "Connection": "keep-alive",
}
RESPECT_ROBOTS = False
ROBOTS_PATH = "/robots.txt"
LIMITS = httpx.Limits(max_connections=400, max_keepalive_connections=150)
MAX_DEPTH = 100
NUM_WORKERS = 150
MAX_TARGET_URLS = 8000
OPENROUTER_CONCURRENCY_LIMIT = 20

llm_semaphore = asyncio.Semaphore(OPENROUTER_CONCURRENCY_LIMIT)

class DynamicPatternMatcher:
    def __init__(self, static_patterns: List[str], dynamic_hosts: List[str]):
        self.exact_domains: Set[str] = set()
        self.wildcard_domains: Set[str] = set()
        self.tlds: Set[str] = set()
        self.partial_matches: List[str] = []

        all_patterns = list(static_patterns) + dynamic_hosts

        for p in all_patterns:
            p = p.strip().lower()
            if not p:
                continue
            if p.startswith("*."):
                self.wildcard_domains.add(p[2:])
                self.exact_domains.add(p[2:])
            elif p.startswith("."):
                if p.count(".") == 1:
                    self.tlds.add(p)
                else:
                    self.partial_matches.append(p)
            else:
                self.exact_domains.add(p)
                self.wildcard_domains.add(p)

    def is_valid_host(self, host: str) -> bool:
        if not host:
            return False
        host = host.lower()
        if host in self.exact_domains:
            return True
        for w in self.wildcard_domains:
            if host.endswith("." + w):
                return True
        for tld in self.tlds:
            if host.endswith(tld):
                return True
        for part in self.partial_matches:
            if part in host or host.endswith(part.lstrip(".")):
                return True
        return False

def clean_html_lxml(html_content: str) -> tuple[str, str]:
    try:
        parser = lxml.html.HTMLParser(encoding='utf-8')
        doc = lxml.html.fromstring(html_content.encode('utf-8', errors='ignore'), parser=parser)
    except Exception:
        return "Untitled", ""
    
    for tag in ["script", "style", "header", "footer", "nav", "aside", "svg"]:
        for el in doc.xpath(f"//{tag}"):
            el.getparent().remove(el)
            
    title_el = doc.xpath("//title")
    title = title_el[0].text_content().strip() if title_el else "Untitled"
    body_text = " ".join(doc.text_content().split())
    return title, body_text

def get_first_four_sentences(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned_sentences = [s.strip() for s in sentences if s.strip()]
    return " ".join(cleaned_sentences[:4]).strip()

def extract_links_and_images_lxml(html_content: str, base_url: str, visited: Set[str], matcher: DynamicPatternMatcher) -> tuple[Set[str], List[str]]:
    child_urls: Set[str] = set()
    image_strings: List[str] = []
    try:
        parser = lxml.html.HTMLParser(encoding='utf-8')
        doc = lxml.html.fromstring(html_content.encode('utf-8', errors='ignore'), parser=parser)
    except Exception:
        return child_urls, image_strings

    try:
        doc.make_links_absolute(base_url, resolve_base_href=True)
    except Exception:
        pass

    parsed_base = urlparse(base_url)
    
    for element, attribute, link, pos in doc.iterlinks():
        if element.tag == 'a' and attribute == 'href':
            parsed_link = urlparse(link)
            if not matcher.is_valid_host(parsed_link.netloc):
                continue
            canonical = parsed_link._replace(fragment="", query="").geturl().rstrip("/")
            if canonical not in visited:
                child_urls.add(canonical)
        elif element.tag == 'img' and attribute == 'src':
            alt_text = element.get("alt", "").strip() or "No Description Present"
            image_strings.append(f"{link}=({alt_text})")
            
    parent_path = parsed_base.path.rstrip("/")
    for common in COMMON_PATHS:
        candidate = f"{parent_path}/{common}".replace("//", "/")
        cand_canon = candidate.rstrip("/")
        cand_parsed = urlparse(cand_canon)
        if (
            cand_parsed.netloc == parsed_base.netloc
            and cand_canon not in visited
            and cand_canon.startswith(f"{parsed_base.scheme}://{parsed_base.netloc}/")
        ):
            child_urls.add(cand_canon)
            
    return child_urls, image_strings

async def summarise_text(client: httpx.AsyncClient, api_key: str, title: str, url: str, text: str) -> str:
    async with llm_semaphore:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        prompt = (
            f"You are evaluating a web page asset.\n"
            f"Target URL: {url}\n"
            f"Page Title: {title}\n"
            f"Raw Content Extract: {text[:4000]}\n\n"
            f"Instructions: Provide a clear summary of what this website or platform is in exactly 15 words. "
            f"If the page is a login portal, gate, or redirect, use the URL/Title context to identify the core underlying platform "
            f"(e.g., 'Google search platform and authentication services'). Return only the 15-word summary, nothing else."
        )
        payload = {
            "model": "nvidia/nemotron-3-nano-30b-a3b",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,
            "max_tokens": 40
        }
        
        for attempt in range(3):
            try:
                resp = await client.post(MODEL_URL, headers=headers, json=payload, timeout=20.0)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return f"OpenRouter Error ({resp.status_code})"
            except Exception as exc:
                if attempt == 2:
                    return f"Inference Timeout: {exc}"
                await asyncio.sleep(1.5)
        return "Generation Timed Out"

async def worker(
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    api_key: str,
    visited: Set[str],
    all_jobs: List[Dict[str, Any]],
    executor: ProcessPoolExecutor,
    matcher: DynamicPatternMatcher,
    counter_lock: asyncio.Lock
) -> None:
    loop = asyncio.get_running_loop()
    while True:
        url, depth = await queue.get()
        try:
            async with counter_lock:
                if len(all_jobs) >= MAX_TARGET_URLS:
                    queue.task_done()
                    continue

            parsed = urlparse(url)
            norm_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            if norm_url in visited or not matcher.is_valid_host(parsed.netloc):
                continue
            visited.add(norm_url)

            try:
                # Use a stream first to verify content headers before downloading whole payload
                async with client.stream("GET", url, follow_redirects=True, timeout=12.0) as resp:
                    if resp.status_code != 200:
                        continue
                    
                    content_type = resp.headers.get("content-type", "").lower()
                    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                        continue
                        
                    html_text = await resp.aread()
                    html_content = html_text.decode("utf-8", errors="ignore")
            except Exception:
                continue

            title, body_text = await loop.run_in_executor(executor, clean_html_lxml, html_content)
            snippet_text = await loop.run_in_executor(executor, get_first_four_sentences, body_text)
            child_urls, parsed_images = await loop.run_in_executor(
                executor, extract_links_and_images_lxml, html_content, str(resp.url), visited, matcher
            )
            
            ai_summary = await summarise_text(client, api_key, title, str(resp.url), body_text)

            async with counter_lock:
                if len(all_jobs) < MAX_TARGET_URLS:
                    all_jobs.append(
                        {
                            "title": title,
                            "url": str(resp.url),
                            "summary": ai_summary,
                            "snippet": snippet_text,
                            "images": parsed_images
                        }
                    )
                if len(all_jobs) >= MAX_TARGET_URLS:
                    while not queue.empty():
                        try:
                            queue.get_nowait()
                            queue.task_done()
                        except asyncio.QueueEmpty:
                            break

            if depth < MAX_DEPTH:
                for u in child_urls:
                    if u not in visited:
                        await queue.put((u, depth + 1))
        finally:
            queue.task_done()

async def periodic_saver(all_jobs: List[Dict[str, Any]], interval: float = 10.0):
    while True:
        await asyncio.sleep(interval)
        try:
            temp_file = "data.json.tmp"
            with open(temp_file, "w", encoding="utf-8") as fp:
                json.dump(all_jobs[:MAX_TARGET_URLS], fp, indent=2, ensure_ascii=False)
            os.replace(temp_file, "data.json")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Backup System] Auto-save skipped: {e}")

def parse_input_urls(file_path: str) -> tuple[List[str], List[str]]:
    seeds = []
    discovered_hosts = []
    if not os.path.exists(file_path):
        return seeds, discovered_hosts
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" not in line:
                line = "https://" + line
            parsed = urlparse(line)
            if parsed.netloc:
                seeds.append(line)
                discovered_hosts.append(parsed.netloc)
                
                base_domain = ".".join(parsed.netloc.split(".")[-2:])
                discovered_hosts.append(f"*.{base_domain}")
    return seeds, discovered_hosts

async def main() -> None:
    api_key = os.getenv("OPENROUTER")
    if not api_key:
        raise ValueError("Missing 'OPENROUTER' environmental key declaration within secret store.")

    DOMAINS = [".gov", ".google", ".github.io", "*.google.com"]
    initial_seeds, dynamic_hosts = parse_input_urls("URLs.txt")
    
    matcher = DynamicPatternMatcher(DOMAINS, dynamic_hosts)
    
    visited: Set[str] = set()
    results: List[Dict[str, Any]] = []
    counter_lock = asyncio.Lock()
    queue = asyncio.Queue()

    for p in DOMAINS:
        if p == ".google.co":
            initial_seeds.extend(["https://google.co.uk", "https://gemini.google.com"])
        elif p == ".google":
            initial_seeds.extend(["https://google.com", "https://blog.google"])

    for seed in initial_seeds:
        parsed = urlparse(seed)
        if matcher.is_valid_host(parsed.netloc):
            await queue.put((seed, 0))
            for common in COMMON_PATHS:
                await queue.put((f"{seed.rstrip('/')}/{common}", 0))

    executor = ProcessPoolExecutor()
    saver_task = asyncio.create_task(periodic_saver(results, 10.0))

    async with httpx.AsyncClient(limits=LIMITS, headers=HEADERS) as client:
        workers = [
            asyncio.create_task(worker(queue, client, api_key, visited, results, executor, matcher, counter_lock))
            for _ in range(NUM_WORKERS)
        ]
        await queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    saver_task.cancel()
    try:
        await saver_task
    except asyncio.CancelledError:
        pass

    executor.shutdown()
    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(results[:MAX_TARGET_URLS], fp, indent=2, ensure_ascii=False)
    print(f"\n[Process Met] Successfully parsed and saved {len(results[:MAX_TARGET_URLS])} documents to data.json.")

if __name__ == "__main__":
    asyncio.run(main())
