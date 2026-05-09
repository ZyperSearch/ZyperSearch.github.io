import os
import json
import subprocess
import requests
import concurrent.futures
from bs4 import BeautifulSoup

SEEDS = ["https://example.com"] # Add your target URLs here
MODEL_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen3-0.6B"

def run_wget():
    subprocess.run([
        "wget", "--recursive", "--level=1", "--page-requisites", 
        "--adjust-extension", "--span-hosts", "--convert-links", 
        "--restrict-file-names=windows", "--directory-prefix=crawl_temp",
        *SEEDS
    ], check=False)

def get_ai_data(text):
    prompt = f"Summarize this in 15 words and provide 1 common typo for the main subject: {text[:1000]}"
    try:
        resp = requests.post(MODEL_URL, json={"inputs": prompt}, timeout=10)
        return resp.json()[0]['generated_text'].replace(prompt, "").strip()
    except:
        return "Summary generation currently unavailable."

def process_page(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            for s in soup(["script", "style"]): s.decompose()
            title = soup.title.string if soup.title else "Untitled Page"
            body_text = ' '.join(soup.get_text().split())
            ai_output = get_ai_data(body_text)
            
            return {
                "title": title,
                "url": filepath.replace("crawl_temp/", ""), 
                "content": ai_output,
                "raw": body_text[:200]
            }
    except:
        return None

def main():
    if not os.path.exists('crawl_temp'): run_wget()
    
    html_files = []
    for root, _, files in os.walk('crawl_temp'):
        for f in files:
            if f.endswith(".html"):
                html_files.append(os.path.join(root, f))

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_page, f) for f in html_files]
        results = [f.result() for f in concurrent.futures.as_completed(futures) if f.result()]

    with open('data.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
