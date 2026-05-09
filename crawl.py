import os
import json
import httpx
import asyncio
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

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
    "https://docker.com", "https://aws.amazon.com", "https://azure.microsoft.com", "https://cloud.google.com", "https://digitalocean.com",
    "https://heroku.com", "https://netlify.com", "https://vercel.com", "https://wordpress.org", "https://wix.com",
    "https://squarespace.com", "https://godaddy.com", "https://bluehost.com", "https://namecheap.com", "https://cloudflare.com",
    "https://weather.com", "https://accuweather.com", "https://wunderground.com", "https://nationalgeographic.com", "https://discovery.com",
    "https://nasa.gov", "https://nih.gov", "https://cdc.gov", "https://who.int", "https://un.org",
    "https://whitehouse.gov", "https://europa.eu", "https://gov.uk", "https://ca.gov", "https://tokyo.jp",
    "https://booking.com", "https://expedia.com", "https://tripadvisor.com", "https://airbnb.com", "https://kayak.com",
    "https://skyscanner.net", "https://hotels.com", "https://yelp.com", "https://foursquare.com", "https://opentable.com",
    "https://uber.com", "https://lyft.com", "https://doordash.com", "https://instacart.com", "https://grubhub.com",
    "https://nike.com", "https://adidas.com", "https://zara.com", "https://h_m.com", "https://uniqlo.com",
    "https://gap.com", "https://nordstrom.com", "https://macys.com", "https://sephora.com", "https://ulta.com",
    "https://espn.com", "https://bleacherreport.com", "https://cbssports.com", "https://nfl.com", "https://nba.com",
    "https://mlb.com", "https://fifa.com", "https://olympics.com", "https://strava.com", "https://fitbit.com",
    "https://coursera.org", "https://udemy.com", "https://edx.org", "https://khanacademy.org", "https://duolingo.com",
    "https://codecademy.com", "https://skillshare.com", "https://masterclass.com", "https://ted.com", "https://grammarly.com"
]
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
    limits = httpx.Limits(max_connections=80, max_keepalive_connections=10)
    
    async with httpx.AsyncClient(limits=limits, headers=HEADERS) as client:
        tasks = [index_url(client, url) for url in SEEDS]
        raw_results = await asyncio.gather(*tasks)
        results = [r for r in raw_results if r]

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Index complete. {len(results)} items written to data.json.")

if __name__ == "__main__":
    asyncio.run(main())
