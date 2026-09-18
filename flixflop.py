#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞流视频 flixflop.com  Python 蜘蛛
适用于 TVBox / 影视仓 / FongMi 等支持 Python 爬虫的客户端
"""

import re
import json
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import quote
import http.cookiejar
import gzip
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.host = "https://www.flixflop.com"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        # 分类 id（与站点一致）
        self.categories = [
            {"type_name": "电影", "type_id": "151438147786375168"},
            {"type_name": "电视剧", "type_id": "151438147794763777"},
            {"type_name": "动漫", "type_id": "151438147807346690"},
            {"type_name": "综艺", "type_id": "151438147807346691"},
            {"type_name": "体育", "type_id": "151438147807346693"},
            {"type_name": "电影解说", "type_id": "204814944317734918"},
            {"type_name": "短剧", "type_id": "331153971999670710"},
        ]

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return "飞流视频"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, url, headers=None):
        if not url:
            return ""
        if url.startswith("/"):
            url = self.host + url
        h = {
            "User-Agent": self._ua,
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        if headers:
            h.update(headers)
        try:
            req = urllib.request.Request(url, headers=h)
            with self.opener.open(req, timeout=15) as resp:
                raw = resp.read()
                enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _parse_next_data(self, html):
        if not html:
            return {}
        m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def _queries(self, next_data):
        try:
            return next_data["props"]["pageProps"]["dehydratedState"]["queries"]
        except Exception:
            return []

    def _find_query(self, queries, key_match):
        """key_match: list 或 callable"""
        for q in queries:
            qk = q.get("queryKey")
            if not qk:
                continue
            if callable(key_match):
                if key_match(qk):
                    return q.get("state", {}).get("data")
            elif list(qk) == list(key_match):
                return q.get("state", {}).get("data")
        return None

    def _fix_pic(self, pic):
        if not pic:
            return ""
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("http"):
            return pic
        if pic.startswith("/"):
            return self.host + pic
        # 纯 hash 封面
        if re.match(r'^[a-f0-9]{40,}$', pic):
            return "https://img.dytt-tupian.com/upload/" + pic
        return pic

    def _item_to_vod(self, item):
        if not isinstance(item, dict):
            return None
        vid = str(item.get("video_id") or item.get("poster_id") or "")
        if not vid:
            return None
        title = item.get("title") or "未知"
        pic = self._fix_pic(item.get("cover_image") or "")
        remarks = item.get("remarks") or ""
        year = item.get("published_year")
        if year and not remarks:
            remarks = str(year)
        elif year and remarks:
            remarks = "%s · %s" % (year, remarks)

        # poster 类型用 url 字段
        path = item.get("url") or ("/streams/%s/detail" % vid)

        return {
            "vod_id": path if path.startswith("/") else "/streams/%s/detail" % vid,
            "vod_name": html_lib.unescape(str(title)),
            "vod_pic": pic,
            "vod_remarks": str(remarks),
            "style": {"type": "rect", "ratio": 0.7}
        }

    def homeContent(self, filter):
        return {"class": list(self.categories)}

    def homeVideoContent(self):
        html = self._fetch(self.host + "/")
        next_data = self._parse_next_data(html)
        queries = self._queries(next_data)
        vod_list = []
        seen = set()

        # 首页推荐
        data = self._find_query(queries, ["landing", "recommendations", "daily"])
        if data and isinstance(data.get("data"), list):
            for it in data["data"]:
                vod = self._item_to_vod(it)
                if vod and vod["vod_id"] not in seen:
                    seen.add(vod["vod_id"])
                    vod_list.append(vod)

        # 海报
        if len(vod_list) < 12:
            data = self._find_query(queries, ["landing", "posters"])
            if data and isinstance(data.get("data"), list):
                for it in data["data"]:
                    vod = self._item_to_vod(it)
                    if vod and vod["vod_id"] not in seen:
                        seen.add(vod["vod_id"])
                        vod_list.append(vod)

        return {"list": vod_list[:24]}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        cid = str(tid).strip()

        html = self._fetch(self.host + "/")
        next_data = self._parse_next_data(html)
        queries = self._queries(next_data)
        vod_list = []
        seen = set()

        def take(items):
            if not isinstance(items, list):
                return
            for it in items:
                vod = self._item_to_vod(it)
                if vod and vod["vod_id"] not in seen:
                    seen.add(vod["vod_id"])
                    vod_list.append(vod)

        # weekly: latest + recommendations
        data = self._find_query(
            queries,
            lambda qk: isinstance(qk, list) and len(qk) >= 4
            and qk[0] == "landing" and str(qk[1]) == cid and qk[2] == "recommendations" and qk[3] == "weekly"
        )
        if data and isinstance(data.get("data"), dict):
            take(data["data"].get("latest"))
            take(data["data"].get("recommendations"))

        # 总榜
        data = self._find_query(
            queries,
            lambda qk: isinstance(qk, list) and len(qk) >= 3
            and qk[0] == "landing" and str(qk[1]) == cid and qk[2] == "recommendations"
            and (len(qk) == 3)
        )
        if data and isinstance(data.get("data"), list):
            take(data["data"])

        # 简单分页：按页切片（首页数据量有限）
        page_size = 20
        start = (page - 1) * page_size
        end = start + page_size
        page_list = vod_list[start:end]

        return {
            "page": page,
            "pagecount": max(1, (len(vod_list) + page_size - 1) // page_size),
            "limit": len(page_list),
            "total": len(vod_list),
            "list": page_list
        }

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        path = raw.strip()
        if not path.startswith("/"):
            path = "/streams/%s/detail" % path
        if "/detail" not in path and path.startswith("/streams/"):
            path = path.rstrip("/") + "/detail"

        html = self._fetch(path)
        next_data = self._parse_next_data(html)
        queries = self._queries(next_data)

        # video_id
        vid_m = re.search(r"/streams/(\d+)", path)
        video_id = vid_m.group(1) if vid_m else ""

        meta = self._find_query(
            queries,
            lambda qk: isinstance(qk, list) and len(qk) >= 3
            and qk[0] == "videos" and str(qk[1]) == video_id and qk[2] == "metadata"
        )
        sources_wrap = self._find_query(
            queries,
            lambda qk: isinstance(qk, list) and len(qk) >= 3
            and qk[0] == "videos" and str(qk[1]) == video_id and qk[2] == "sources"
        )

        info = {}
        if meta and isinstance(meta.get("data"), dict):
            info = meta["data"]

        vod_name = info.get("title") or "精彩影片"
        vod_pic = self._fix_pic(info.get("cover_image") or "")
        actors = info.get("actors") or ""
        if isinstance(actors, list):
            actors = ", ".join(
                (a.get("name") if isinstance(a, dict) else str(a)) for a in actors
            )
        directors = info.get("directors") or ""
        if isinstance(directors, list):
            directors = ", ".join(
                (d.get("name") if isinstance(d, dict) else str(d)) for d in directors
            )
        desc = info.get("description") or ""
        remarks = info.get("remarks") or ""
        year = info.get("published_year") or ""
        area = info.get("area") or ""
        genre = info.get("genre") or info.get("category") or ""

        content_parts = []
        if year:
            content_parts.append("年份：%s" % year)
        if area:
            content_parts.append("地区：%s" % area)
        if genre:
            content_parts.append("类型：%s" % genre)
        if desc:
            content_parts.append(desc)
        vod_content = "\n".join(content_parts) if content_parts else "飞流视频"

        play_from = []
        play_url = []

        source_list = []
        if sources_wrap:
            d = sources_wrap.get("data")
            if isinstance(d, list):
                source_list = d
            elif isinstance(d, dict) and isinstance(d.get("data"), list):
                source_list = d["data"]

        for idx, src in enumerate(source_list):
            if not isinstance(src, dict):
                continue
            name = src.get("name") or ("线路%d" % (idx + 1))
            u = (src.get("url") or "").strip()
            if not u:
                continue
            # 已是 集数$url#集数$url 格式
            if "$" in u:
                play_from.append(name)
                play_url.append(u)
            else:
                play_from.append(name)
                play_url.append("正片$%s" % u)

        if not play_from:
            play_from = ["网页线路"]
            play_url = ["正片$%s%s" % (self.host, path)]

        return {
            "list": [{
                "vod_id": path,
                "vod_name": html_lib.unescape(str(vod_name)),
                "vod_pic": vod_pic,
                "vod_actor": actors or "飞流视频",
                "vod_director": directors or "飞流视频",
                "vod_remarks": str(remarks),
                "vod_content": html_lib.unescape(str(vod_content)),
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        is_page = not self.isVideoFormat(url)
        headers = {
            "User-Agent": self._ua,
            "Accept": "*/*",
        }
        if is_page:
            headers["Referer"] = self.host + "/"
        return {
            "parse": 1 if is_page else 0,
            "jx": 0,
            "url": url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        """搜索：从首页已加载数据中做本地匹配（站点搜索页不稳定时的兜底）"""
        page = int(pg) if str(pg).isdigit() else 1
        key = (key or "").strip()
        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

        html = self._fetch(self.host + "/")
        next_data = self._parse_next_data(html)
        queries = self._queries(next_data)

        vod_list = []
        seen = set()

        def take(items):
            if not isinstance(items, list):
                return
            for it in items:
                title = str(it.get("title") or "")
                if key not in title:
                    continue
                vod = self._item_to_vod(it)
                if vod and vod["vod_id"] not in seen:
                    seen.add(vod["vod_id"])
                    vod_list.append(vod)

        for q in queries:
            st = q.get("state", {}).get("data")
            if not isinstance(st, dict):
                continue
            d = st.get("data")
            if isinstance(d, list):
                take(d)
            elif isinstance(d, dict):
                take(d.get("latest"))
                take(d.get("recommendations"))
                # posters
                if d and isinstance(d, list):
                    take(d)

        return {
            "page": page,
            "pagecount": 1,
            "limit": len(vod_list),
            "total": len(vod_list),
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "flixflop spider ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Disabled"]

    def destroy(self):
        self.options = {}
