#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048ai.vip 分类播放器
支持按类别浏览短剧/视频，并直接播放
"""

import requests
import json
import subprocess
import webbrowser
import sys
import os
from urllib.parse import quote

BASE_URL = "https://2048ai.vip"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://2048ai.vip/media/",
}

def get_json(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 200:
            print(f"接口错误: {data.get('message')}")
            return None
        return data.get("data")
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def get_categories():
    data = get_json(f"{BASE_URL}/api/v1/categories?type=video")
    if not data:
        return []
    return sorted(data, key=lambda x: x.get("sortOrder", 999))

def get_videos(category_id, page=1, size=20):
    url = f"{BASE_URL}/api/v1/videos?productId=1&categoryId={category_id}&page={page}&size={size}"
    data = get_json(url)
    return data.get("items", []) if data else []

def get_short_dramas(page=1, size=20, sort_by="heat"):
    url = f"{BASE_URL}/api/v1/short-dramas?productId=1&sortBy={sort_by}&page={page}&size={size}"
    data = get_json(url)
    return data.get("items", []) if data else []

def get_short_drama_detail(drama_id):
    data = get_json(f"{BASE_URL}/api/v1/short-dramas/{drama_id}?productId=1")
    return data

def make_play_url(video_path):
    """构造可直接播放的代理 m3u8 地址"""
    if not video_path:
        return None
    # 去掉开头的 /
    path = video_path.lstrip("/")
    return f"{BASE_URL}/api/v1/m3u8/proxy?path={quote(path)}"

def play_video(play_url, title=""):
    """优先用 VLC / mpv 播放，否则用浏览器"""
    if not play_url:
        print("没有可播放地址")
        return

    print(f"\n正在播放: {title}")
    print(f"播放地址: {play_url}\n")

    # 尝试 VLC
    for player in ["vlc", "mpv", "ffplay"]:
        try:
            if player == "vlc":
                subprocess.Popen(["vlc", "--play-and-exit", play_url],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif player == "mpv":
                subprocess.Popen(["mpv", play_url],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif player == "ffplay":
                subprocess.Popen(["ffplay", "-autoexit", "-window_title", title, play_url],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"已用 {player} 启动播放")
            return
        except FileNotFoundError:
            continue

    # 都没有则用浏览器
    print("未检测到 VLC/mpv/ffplay，使用浏览器打开...")
    webbrowser.open(play_url)

def show_menu(title, options):
    print(f"\n===== {title} =====")
    for i, opt in enumerate(options, 1):
        print(f"{i}. {opt}")
    print("0. 返回 / 退出")
    while True:
        try:
            choice = int(input("请选择: ").strip())
            if 0 <= choice <= len(options):
                return choice
        except ValueError:
            pass
        print("输入无效，请重新输入")

def browse_videos(category):
    page = 1
    while True:
        print(f"\n正在加载「{category['name']}」第 {page} 页...")
        items = get_videos(category["id"], page=page)
        if not items:
            print("没有更多内容了")
            if page == 1:
                return
            page = max(1, page - 1)
            continue

        options = []
        for item in items:
            duration = item.get("durationSec", 0)
            mins = duration // 60
            title = item.get("title", "无标题")[:50]
            options.append(f"{title}  ({mins}分钟 | 播放量:{item.get('viewCount', 0)})")

        options.append("下一页")
        if page > 1:
            options.append("上一页")

        choice = show_menu(f"{category['name']} (第{page}页)", options)
        if choice == 0:
            return
        if choice == len(items) + 1:  # 下一页
            page += 1
            continue
        if choice == len(items) + 2:  # 上一页
            page = max(1, page - 1)
            continue

        item = items[choice - 1]
        play_url = make_play_url(item.get("videoUrl"))
        play_video(play_url, item.get("title", ""))

def browse_short_dramas():
    page = 1
    while True:
        print(f"\n正在加载短剧第 {page} 页...")
        items = get_short_dramas(page=page)
        if not items:
            print("没有更多内容了")
            if page == 1:
                return
            page = max(1, page - 1)
            continue

        options = []
        for item in items:
            title = item.get("title", "无标题")[:45]
            options.append(f"{title}  (共{item.get('episodeCount', 0)}集 | 热度:{item.get('heatCount', 0)})")

        options.append("下一页")
        if page > 1:
            options.append("上一页")

        choice = show_menu(f"AI短剧 (第{page}页)", options)
        if choice == 0:
            return
        if choice == len(items) + 1:
            page += 1
            continue
        if choice == len(items) + 2:
            page = max(1, page - 1)
            continue

        drama = items[choice - 1]
        detail = get_short_drama_detail(drama["id"])
        if not detail or not detail.get("episodes"):
            print("获取剧集失败")
            continue

        episodes = detail["episodes"]
        ep_options = [f"第{ep['episodeNo']}集 - {ep.get('title') or '无标题'}" for ep in episodes]
        ep_choice = show_menu(detail.get("title", "短剧"), ep_options)
        if ep_choice == 0:
            continue

        ep = episodes[ep_choice - 1]
        play_url = make_play_url(ep.get("videoUrl"))
        play_video(play_url, f"{detail.get('title')} - 第{ep['episodeNo']}集")

def main():
    print("=" * 50)
    print("2048ai.vip 分类播放器")
    print("提示: 推荐安装 VLC 或 mpv 以获得最佳播放体验")
    print("=" * 50)

    while True:
        main_options = [
            "AI短剧（热门/最新）",
            "按视频分类浏览",
            "退出"
        ]
        choice = show_menu("主菜单", main_options)

        if choice == 0 or choice == 3:
            print("再见！")
            break
        elif choice == 1:
            browse_short_dramas()
        elif choice == 2:
            cats = get_categories()
            if not cats:
                print("获取分类失败")
                continue
            cat_options = [f"{c['name']}" for c in cats]
            cat_choice = show_menu("选择分类", cat_options)
            if cat_choice == 0:
                continue
            browse_videos(cats[cat_choice - 1])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")