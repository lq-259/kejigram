#!/usr/bin/env python3
"""Fetch yesterday's posts from the Telegram public preview page."""
import html
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).parent.parent / "dates"
TG_URL = "https://t.me/s/zaihuapd"


BRAND_PATTERNS = [
    r"🌸\s*在花频道\s*[·・|｜-]?\s*备用频道\s*[·・|｜-]?\s*投稿通道",
    r"🌸\s*在花频道",
    r"🍀\s*在花频道",
    r"在花频道\s*[·・|｜-]?\s*备用频道\s*[·・|｜-]?\s*投稿通道",
    r"在花频道",
    r"备用频道",
    r"投稿通道",
    r"@?zaihuapd",
    r"@?zaihuatg",
    r"@?zaihuabot",
    r"@?zaihua",
    r"[·・|｜-]?\s*英文频道",
    r"[·・|｜-]?\s*茶馆讨论",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Telegram public preview posts for one date.")
    parser.add_argument("date", nargs="?", help="Target date, defaults to yesterday: YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Overwrite existing summaries.json and refresh images")
    args = parser.parse_args()
    if args.date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("date must use YYYY-MM-DD")
    return args


def parse_target_date(date_arg=None):
    if date_arg:
        return datetime.strptime(date_arg, "%Y-%m-%d").date()
    return (datetime.now() - timedelta(days=1)).date()


def clean_text(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def clean_public_text(text):
    text = clean_text(text)
    for pattern in BRAND_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*([·・|｜-])\s*([·・|｜-]\s*)+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ·・|｜-/，,。")
    return text


def fetch_page():
    resp = requests.get(
        TG_URL,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
    )
    resp.raise_for_status()
    return resp.text


def parse_messages(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    wraps = soup.find_all("div", class_="tgme_widget_message_wrap")
    print(f"Found {len(wraps)} message blocks")

    items = []
    for wrap in wraps:
        msg = wrap.find("div", class_="tgme_widget_message")
        if not msg:
            continue

        post_id = msg.get("data-post", "").split("/")[-1]
        time_tag = msg.find("time")
        ts = time_tag.get("datetime") if time_tag else None

        text_div = msg.find("div", class_="tgme_widget_message_text js-message_text")
        title = ""
        body = ""
        if text_div:
            bold = text_div.find("b")
            if bold:
                title = clean_public_text(bold.get_text())
            body = clean_public_text(text_div.get_text())

        reply_div = msg.find("div", class_="tgme_widget_message_text js-message_reply_text")
        reply_body = clean_public_text(reply_div.get_text()) if reply_div else ""

        photos = []
        photo_wrap = msg.find("a", class_="tgme_widget_message_photo_wrap")
        if photo_wrap:
            match = re.search(r"background-image:url\('([^']+)'\)", photo_wrap.get("style", ""))
            if match:
                photos.append(match.group(1))

        srcs = []
        if text_div:
            for link in text_div.find_all("a", href=True):
                href = link["href"]
                if "t.me/zaihua" in href.lower() or "t.me/zaihuapd" in href.lower():
                    continue
                label = clean_public_text(link.get_text()) or href
                srcs.append([href, label])

        if not title and not body:
            continue

        items.append({
            "post_id": post_id,
            "ts": ts,
            "title": title or body[:60],
            "body": body,
            "reply_body": reply_body,
            "imgs": photos,
            "srcs": srcs,
        })
    return items


def filter_by_date(items, target):
    keep = []
    for item in items:
        if not item["ts"]:
            continue
        try:
            dt = datetime.fromisoformat(item["ts"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.date() == target:
            keep.append(item)
    return keep


def download_images(items, img_dir):
    img_dir.mkdir(parents=True, exist_ok=True)
    for item_index, item in enumerate(items, 1):
        local = []
        for image_index, url in enumerate(item["imgs"][:3]):
            ext = ".jpg"
            for candidate in [".png", ".webp", ".gif", ".jpeg"]:
                if candidate in url.lower():
                    ext = candidate
                    break
            out = img_dir / f"item{item_index:02d}_img{image_index}{ext}"
            try:
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200 and len(resp.content) > 1000:
                    out.write_bytes(resp.content)
                    local.append(str(out))
            except requests.RequestException:
                pass
        item["_local_imgs"] = local


def main():
    args = parse_args()
    target_date = parse_target_date(args.date)
    date_str = target_date.strftime("%Y-%m-%d")
    day_dir = ROOT / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    out = day_dir / "summaries.json"

    if out.exists() and not args.force:
        print(f"[skip] {out} already exists. Use --force to refetch and overwrite.")
        return

    print("[1] Fetching Telegram page...")
    items = parse_messages(fetch_page())

    print(f"[2] Filtering {date_str}...")
    daily_items = filter_by_date(items, target_date)
    print(f"    Matched: {len(daily_items)} items")

    print("[3] Downloading images...")
    download_images(daily_items, day_dir / "imgs")

    summaries = []
    for index, item in enumerate(daily_items, 1):
        summaries.append({
            "i": index,
            "title": item["title"],
            "body": item["body"],
            "reply_body": item["reply_body"],
            "imgs": item["imgs"],
            "srcs": item["srcs"],
            "_local_imgs": item.get("_local_imgs", []),
        })

    out.write_text(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(f"[4] Saved {len(summaries)} items to {out}")
    for summary in summaries:
        print(f"    {summary['i']}: {summary['title'][:50]} | imgs={len(summary['_local_imgs'])}")


if __name__ == "__main__":
    main()
