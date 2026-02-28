import os
import asyncio
import csv
import time
from datetime import datetime, timezone
from feedgen.feed import FeedGenerator
from TikTokApi import TikTokApi
import config
from playwright.async_api import async_playwright, Playwright
from pathlib import Path
from urllib.parse import urlparse

# Edit config.py to change your URLs
ghRawURL = config.ghRawURL

# --- NEW AUTO-TOKEN FUNCTION ---
async def get_ms_token():
    """Automatically fetches a fresh ms_token from TikTok"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # Visit TikTok to trigger cookie generation
        await page.goto("https://www.tiktok.com", wait_until="networkidle")
        cookies = await context.cookies()
        ms_token = next((c['value'] for c in cookies if c['name'] == 'msToken'), None)
        await browser.close()
        return ms_token

async def runscreenshot(playwright: Playwright, url, screenshotpath):
    chromium = playwright.chromium
    browser = await chromium.launch()
    page = await browser.new_page()
    await page.goto(url)
    await page.screenshot(path=screenshotpath, quality=20, type='jpeg')
    await browser.close()

async def user_videos():
    # 1. Get a fresh token automatically
    print("Fetching fresh ms_token...")
    generated_ms_token = await get_ms_token()
    
    # Use generated token, or fallback to Secret if generation fails
    active_token = generated_ms_token or os.environ.get("MS_TOKEN")
    print(f"Using token: {active_token[:10]}...")

    with open('subscriptions.csv') as f:
        cf = csv.DictReader(f, fieldnames=['username'])
        for row in cf:
            user = row['username']
            print(f'Running for user \'{user}\'')

            fg = FeedGenerator()
            fg.id('https://www.tiktok.com/@' + user)
            fg.title(user + ' TikTok')
            fg.author({'name': 'Conor ONeill', 'email': 'conor@conoroneill.com'})
            fg.link(href='http://tiktok.com', rel='alternate')
            fg.logo(ghRawURL + 'tiktok-rss.png')
            fg.subtitle('Latest TikToks from ' + user)
            fg.link(href=ghRawURL + 'rss/' + user + '.xml', rel='self')
            fg.language('en')

            updated = None
            
            async with TikTokApi() as api:
                # 2. Inject the fresh token here
                await api.create_sessions(ms_tokens=[active_token], num_sessions=1, sleep_after=3, headless=True)
                ttuser = api.user(user)
                try:
                    async for video in ttuser.videos(count=10):
                        fe = fg.add_entry()
                        link = "https://tiktok.com/@" + user + "/video/" + video.id
                        fe.id(link)
                        ts = datetime.fromtimestamp(video.as_dict['createTime'], timezone.utc)
                        fe.published(ts)
                        fe.updated(ts)
                        updated = max(ts, updated) if updated else ts
                        
                        title = video.as_dict.get('desc', 'No Title')[:255]
                        fe.title(title if title else "No Title")
                        fe.link(href=link)

                        content = title if title else "No Description"
                        
                        if video.as_dict['video'].get('cover'):
                            videourl = video.as_dict['video']['cover']
                            parsed_url = urlparse(videourl)
                            path_segments = parsed_url.path.split('/')
                            last_segment = [seg for seg in path_segments if seg][-1]

                            screenshotsubpath = "thumbnails/" + user + "/screenshot_" + last_segment + ".jpg"
                            screenshotpath = os.path.join(os.path.dirname(os.path.realpath(__file__)), screenshotsubpath)
                            
                            # Ensure directory exists
                            os.makedirs(os.path.dirname(screenshotpath), exist_ok=True)
                            
                            if not os.path.isfile(screenshotpath):
                                async with async_playwright() as playwright:
                                    await runscreenshot(playwright, videourl, screenshotpath)
                            
                            screenshoturl = ghRawURL + screenshotsubpath
                            content = f'<img src="{screenshoturl}" /> {content}'

                        fe.content(content)
                    
                    if updated:
                        fg.updated(updated)
                        fg.rss_file('rss/' + user + '.xml', pretty=True)
                except Exception as e:
                    print(f"Error for user {user}: {e}")

if __name__ == "__main__":
    asyncio.run(user_videos())
