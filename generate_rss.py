#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TMI総合法律事務所 - #中国 記事RSSフィード生成スクリプト
GitHub Actionsで週1回実行
"""

import os
import sys
import json
import ssl
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, quote
import urllib3

# SSL警告を無効にする（必要に応じて）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定
BASE_URL = "https://www.tmi.gr.jp"
TARGET_URL = "https://www.tmi.gr.jp/eyes/?tag=%E4%B8%AD%E5%9B%BD"  # 修正: %E4%B8%AD%E5%9B%83 → %E4%B8%AD%E5%9B%BD
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_FILE = "feed.xml"
MAX_ITEMS = 50  # RSSに含める最大記事数

# 中国時間（UTC+8）のタイムゾーン
CHINA_TZ = timezone(timedelta(hours=8))


def get_session():
    """SSL検証をスキップするセッションを作成"""
    session = requests.Session()
    
    # SSL検証を無効にする（自己署名証明書対応）
    session.verify = False
    
    # または、より安全な方法：SSLコンテキストを作成
    # ssl_context = ssl.create_default_context()
    # ssl_context.check_hostname = False
    # ssl_context.verify_mode = ssl.CERT_NONE
    # session.verify = ssl_context
    
    return session


def fetch_articles():
    """記事一覧ページを取得し、記事情報を抽出する"""
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    print(f"Fetching: {TARGET_URL}")
    
    try:
        # SSL検証を無効にしてリクエスト
        session = get_session()
        response = session.get(TARGET_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # レスポンスの内容を確認（デバッグ用）
        print(f"Response status: {response.status_code}")
        print(f"Content length: {len(response.text)} bytes")
        
    except requests.exceptions.SSLError as e:
        print(f"SSL Error: {e}")
        print("Trying with SSL verification disabled...")
        
        # SSL検証を完全に無効にして再試行
        session = requests.Session()
        session.verify = False
        response = session.get(TARGET_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
    except Exception as e:
        print(f"Request failed: {e}")
        raise
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 記事リストを取得（複数のセレクタを試す）
    articles = []
    
    # セレクタの候補を順に試す
    selectors = [
        '.blog-list .item',
        '.blog-wrap .blog-list .item',
        '.blog-wrap .item',
        '.blog-list li.item',
        '.blog-list li',
        '.item',
        'li.item',
    ]
    
    items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            print(f"Found items with selector: {selector}")
            break
    
    if not items:
        print("Warning: No articles found with standard selectors.")
        # 全てのaタグをチェック（フォールバック）
        all_links = soup.find_all('a', href=True)
        # 記事へのリンクっぽいものを抽出
        for link in all_links:
            href = link.get('href', '')
            if '/eyes/' in href and href != '/eyes/?tag=%E4%B8%AD%E5%9B%BD':
                parent = link.find_parent('li')
                if parent:
                    items.append(parent)
        print(f"Found {len(items)} items via fallback method")
    
    for item in items:
        try:
            # リンクとタイトル
            link_tag = item.find('a')
            if not link_tag:
                continue
            href = link_tag.get('href')
            if not href:
                continue
            
            # 相対URLを絶対URLに変換
            full_url = urljoin(BASE_URL, href)
            
            # タイトル
            title_tag = item.select_one('.item-title')
            if not title_tag:
                # 代替: aタグのテキストを使う
                title_tag = link_tag
            title = title_tag.get_text(strip=True) if title_tag else "タイトルなし"
            
            # 日付
            date_tag = item.select_one('.item-date')
            date_str = date_tag.get_text(strip=True) if date_tag else ""
            
            # カテゴリ
            category_tag = item.select_one('.item-category')
            category = category_tag.get_text(strip=True) if category_tag else ""
            
            # 画像
            img_tag = link_tag.find('img')
            image_url = None
            if img_tag:
                image_url = img_tag.get('src')
                # data-srcがある場合はそちらを使う（Lazy Loading対応）
                if not image_url:
                    image_url = img_tag.get('data-src')
                if image_url:
                    image_url = urljoin(BASE_URL, image_url)
            
            # 説明文（サムネイルのalt属性があれば使用）
            description = ""
            if img_tag and img_tag.get('alt'):
                description = img_tag.get('alt')
            elif title:
                description = f"{category} - {title}" if category else title
            
            articles.append({
                'url': full_url,
                'title': title,
                'date': date_str,
                'category': category,
                'image': image_url,
                'description': description,
            })
            
        except Exception as e:
            print(f"Error parsing article: {e}")
            continue
    
    # 重複を除去（URLベース）
    seen_urls = set()
    unique_articles = []
    for article in articles:
        if article['url'] not in seen_urls:
            seen_urls.add(article['url'])
            unique_articles.append(article)
    
    print(f"Found {len(unique_articles)} unique articles")
    return unique_articles


def parse_date(date_str):
    """日付文字列をパースする（YYYY.MM.DD形式）"""
    if not date_str:
        return datetime.now(CHINA_TZ)
    
    try:
        # YYYY.MM.DD 形式
        dt = datetime.strptime(date_str.strip(), '%Y.%m.%d')
        # 中国時間（UTC+8）として扱う
        dt = dt.replace(tzinfo=CHINA_TZ)
        return dt
    except ValueError:
        try:
            # YYYY/MM/DD 形式にも対応
            dt = datetime.strptime(date_str.strip(), '%Y/%m/%d')
            dt = dt.replace(tzinfo=CHINA_TZ)
            return dt
        except ValueError:
            try:
                # YYYY年MM月DD日 形式
                dt = datetime.strptime(date_str.strip(), '%Y年%m月%d日')
                dt = dt.replace(tzinfo=CHINA_TZ)
                return dt
            except ValueError:
                print(f"Warning: Could not parse date: {date_str}")
                return datetime.now(CHINA_TZ)


def generate_rss(articles):
    """RSSフィードを生成する"""
    fg = FeedGenerator()
    
    # フィードの基本情報
    fg.title("TMI総合法律事務所 - #中国 記事一覧")
    fg.description("TMI総合法律事務所の中国関連記事（ブログ、ニューズレター、執筆情報など）のRSSフィード")
    fg.link(href="https://www.tmi.gr.jp/eyes/?tag=中国", rel="alternate")
    # 以下のURLはあなたのリポジトリに合わせて変更してください
    fg.link(href="https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/feed.xml", rel="self")
    fg.language("ja")
    fg.copyright("Copyright © TMI Associates All rights reserved.")
    
    # 最終更新日時
    fg.lastBuildDate(datetime.now(CHINA_TZ))
    
    # 各記事をエントリーとして追加
    for article in articles[:MAX_ITEMS]:
        entry = fg.add_entry()
        entry.title(article['title'])
        entry.link(href=article['url'], rel="alternate")
        
        # 説明文
        description = article['description'] or article['title']
        entry.description(description)
        
        # 画像があればエンクロージャとして追加
        if article['image'] and article['image'].startswith('http'):
            entry.enclosure(article['image'], 0, 'image/jpeg')
        
        # カテゴリがあれば追加
        if article['category']:
            entry.category(term=article['category'])
        
        # 日付
        pub_date = parse_date(article['date'])
        entry.pubDate(pub_date)
        
        # GUID（URLを使用）
        entry.guid(article['url'], permalink=True)
    
    # RSSファイルを生成
    rss_str = fg.rss_str(pretty=True)
    
    # ファイルに保存（UTF-8）
    with open(OUTPUT_FILE, 'wb') as f:
        f.write(rss_str)
    
    print(f"RSS feed generated: {OUTPUT_FILE}")
    print(f"Total entries: {len(articles[:MAX_ITEMS])}")


def main():
    """メイン関数"""
    print(f"Starting RSS generation at {datetime.now(CHINA_TZ).isoformat()}")
    
    try:
        articles = fetch_articles()
        if not articles:
            print("Error: No articles found. Exiting.")
            print("Trying to save debug HTML for inspection...")
            try:
                with open('debug.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print("Saved debug.html for inspection")
            except:
                pass
            sys.exit(1)
        
        generate_rss(articles)
        print("RSS generation completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
