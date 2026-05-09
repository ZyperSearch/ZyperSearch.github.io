import os
import json
import httpx
import asyncio
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

SEEDS = ["https://example.com"]
MODEL_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen3-0.6B"
HEADERS = {"Authorization": "Bearer YOUR_HF_TOKEN"} # Recommended for stability

async def get_ai_summary(client, text):
    prompt = f"Summarize in 15 words and provide 1 common typo for the subject: {text[:800]}"
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 50, "return_full_text": False}}
    try:
        response = await client.post(MODEL_URL, json=payload, timeout=15.0)
        if response.status_code == 200:
            data = response.json()
            return data[0].get('generated_text', '').strip()
        return "Summary generation currently unavailable."
    except Exception:
        return "Error reaching inference server."

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup(["script", "style", "header", "footer", "nav"]):
        element.decompose()
    title = soup.title.string.strip() if soup.title else "Untitled Source"
    text = ' '.join(soup.get_text().split())
    return title, text

async def index_url(client, url):
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        
        title, body_text = clean_html(resp.text)
        ai_output = await get_ai_summary(client, body_text)
        
        return {
            "title": title,
            "url": str(resp.url),
            "content": ai_output,
            "raw": body_text[:250]
        }
    except Exception as e:
        print(f"Failed to index {url}: {e}")
        return None

async def main():
    results = []
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    
    async with httpx.AsyncClient(limits=limits, headers=HEADERS) as client:
        tasks = [index_url(client, url) for url in SEEDS]
        raw_results = await asyncio.gather(*tasks)
        results = [r for r in raw_results if r]

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Index complete. {len(results)} items written to data.json.")

if __name__ == "__main__":
    asyncio.run(main())
