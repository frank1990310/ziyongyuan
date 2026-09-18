#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JavDB Web UI / catembylegacy  Python 蜘蛛
数据源：jdforrepam.com (JavDB API)

说明：
- 在线「解析播放」返回的是图片分片伪装的 m3u8，TVBox 无法当视频播
- 本源以 浏览 / 搜索 / 磁力信息 为主；若磁力带 http 直链会尝试给出
"""

import re
import json
import time
import hashlib
import html as html_lib
import urllib.request
from urllib.parse import quote, unquote, urlencode
import http.cookiejar
import gzip
import ssl
import base64

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"
        def getProxyUrl(self): return ""


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.host = "https://catembylegacy.fastcdn.dpdns.org"
        self.api_host = "https://jdforrepam.com/api"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self._jv = "lpw6vgqzsp"
        self._iv = (
            "71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e7d"
            "5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa"
        )
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

        self.categories = [
            {"type_name": "最新发布", "type_id": "latest"},
            {"type_name": "推荐", "type_id": "recommend"},
            {"type_name": "日榜", "type_id": "rank_daily"},
            {"type_name": "周榜", "type_id": "rank_weekly"},
            {"type_name": "月榜", "type_id": "rank_monthly"},
            {"type_name": "播放榜", "type_id": "rank_playback"},
            {"type_name": "有码", "type_id": "rank_censored"},
        ]

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
        return "JavDB"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", "magnet:"))

    def manualVideoCheck(self):
        return False

    def _signature(self):
        ts = str(int(time.time()))
        digest = hashlib.md5((ts + self._iv).encode("utf-8")).hexdigest()
        return "%s.%s.%s" % (ts, self._jv, digest)

    def _fetch(self, url, headers=None, binary=False):
        if not url:
            return b"" if binary else ""
        h = {
            "User-Agent": self._ua,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
        }
        if headers:
            h.update(headers)
        try:
            req = urllib.request.Request(url, headers=h)
            with self.opener.open(req, timeout=18) as resp:
                raw = resp.read()
                enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                if binary:
                    return raw
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return b"" if binary else ""

    def _api(self, path, query=None):
        url = self.api_host + path
        if query:
            url += "?" + urlencode(query)
        text = self._fetch(url, headers={
            "Accept": "application/json",
            "jdsignature": self._signature(),
            "Referer": self.host + "/",
        })
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _pic_url(self, mid, pic=""):
        """
        官方 cover_url (tp.spfcas.com) 不是标准 JPG，TVBox 无法显示。
        改用 JavDB 公共图床：https://c0.jdbstatic.com/covers/{id前2位小写}/{id}.jpg
        """
        mid = (mid or "").strip()
        if mid and len(mid) >= 2:
            prefix = mid[:2].lower()
            return "https://c0.jdbstatic.com/covers/%s/%s.jpg" % (prefix, mid)
        if not pic:
            return ""
        if pic.startswith("//"):
            return "https:" + pic
        return pic

    def _movie_to_vod(self, m):
        if not isinstance(m, dict):
            return None
        mid = m.get("id") or ""
        number = m.get("number") or mid
        title = m.get("title") or m.get("origin_title") or number
        pic = self._pic_url(mid, m.get("cover_url") or m.get("thumb_url") or "")
        remarks = []
        if m.get("score"):
            remarks.append(str(m.get("score")))
        if m.get("duration"):
            remarks.append("%s分" % m.get("duration"))
        if m.get("has_cnsub") or m.get("play_subtitle"):
            remarks.append("中字")
        if m.get("can_play"):
            remarks.append("可播")
        if m.get("release_date"):
            remarks.append(str(m.get("release_date"))[:10])

        vod_id = "%s|%s" % (number, mid)
        return {
            "vod_id": vod_id,
            "vod_name": "[%s] %s" % (number, html_lib.unescape(str(title))[:80]),
            "vod_pic": pic,
            "vod_remarks": " · ".join(remarks) if remarks else number,
            "style": {"type": "rect", "ratio": 1.45}
        }


    def _parse_movies(self, data):
        movies = []
        if isinstance(data, dict):
            inner = data.get("data") if isinstance(data.get("data"), dict) else data
            if isinstance(inner, dict) and isinstance(inner.get("movies"), list):
                movies = inner["movies"]
            elif isinstance(data.get("movies"), list):
                movies = data["movies"]
            elif isinstance(data.get("data"), list):
                movies = data["data"]
        elif isinstance(data, list):
            movies = data
        vod_list = []
        for m in movies:
            vod = self._movie_to_vod(m)
            if vod:
                vod_list.append(vod)
        return vod_list

    def homeContent(self, filter):
        return {"class": list(self.categories)}

    def homeVideoContent(self):
        data = self._api("/v1/movies/recommend")
        return {"list": self._parse_movies(data)[:24]}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        tid = str(tid).strip()
        vod_list = []

        if tid == "latest":
            data = self._api("/v1/movies/latest", {"page": str(page)})
            vod_list = self._parse_movies(data)
        elif tid == "recommend":
            data = self._api("/v1/movies/recommend")
            vod_list = self._parse_movies(data)
            size = 20
            start = (page - 1) * size
            vod_list = vod_list[start:start + size]
        elif tid.startswith("rank_"):
            kind = tid.replace("rank_", "", 1)
            data = self._api("/v1/rankings", {"type": kind, "period": "1"})
            vod_list = self._parse_movies(data)
            size = 20
            start = (page - 1) * size
            vod_list = vod_list[start:start + size]
        else:
            data = self._api("/v1/movies/latest", {"page": str(page)})
            vod_list = self._parse_movies(data)

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 10 else page,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        parts = str(raw).split("|", 1)
        number = parts[0].strip()
        mid = parts[1].strip() if len(parts) > 1 else ""

        info = {"number": number, "title": number, "cover_url": "", "id": mid}
        if number:
            sr = self._api("/v2/search", {"q": number, "page": "1"})
            movies = []
            if isinstance(sr, dict):
                movies = (sr.get("data") or {}).get("movies") or []
            for m in movies:
                if str(m.get("number", "")).upper() == number.upper() or (mid and str(m.get("id")) == mid):
                    info = m
                    mid = mid or str(m.get("id") or "")
                    number = m.get("number") or number
                    break
            if movies and info.get("title") == number:
                info = movies[0]
                mid = mid or str(info.get("id") or "")
                number = info.get("number") or number

        title = info.get("title") or info.get("origin_title") or number
        pic = self._pic_url(mid or info.get("id") or "", info.get("cover_url") or info.get("thumb_url") or "")

        remarks = str(info.get("release_date") or "")[:10]

        magnets = []
        if mid:
            mag = self._api("/v1/movies/%s/magnets" % mid)
            if isinstance(mag, dict):
                magnets = (mag.get("data") or {}).get("magnets") or []

        content_parts = [
            "番号：%s" % number,
            "注意：本站网页播放为图片流，TVBox 无法在线播放。",
            "请使用下方磁力（需支持磁力的客户端/网盘）。",
        ]
        if info.get("duration"):
            content_parts.insert(1, "时长：%s 分钟" % info.get("duration"))

        play_from = []
        play_url = []

        # 磁力转可展示条目（部分壳可复制，不能保证直接播）
        for i, mg in enumerate(magnets[:15]):
            if not isinstance(mg, dict):
                continue
            name = mg.get("name") or ("磁力%d" % (i + 1))
            tags = []
            if mg.get("hd"):
                tags.append("HD")
            if mg.get("cnsub"):
                tags.append("中字")
            size = mg.get("size")
            if size:
                tags.append("%sMB" % size)
            label = name if not tags else "%s(%s)" % (name, ",".join(tags))
            # magnet via hash
            h = mg.get("hash") or ""
            magnet = ""
            if h:
                magnet = "magnet:?xt=urn:btih:%s" % h
            pikpak = mg.get("pikpak_url") or ""
            if magnet:
                play_from.append(label[:40])
                play_url.append("磁力$%s" % magnet)
            if pikpak and pikpak.startswith("http"):
                play_from.append((label[:30] + "-网盘")[:40])
                play_url.append("网盘$%s" % pikpak)

        if not play_from:
            play_from = ["说明"]
            play_url = ["无法在线播放-请换其他源$https://www.example.com/"]

        return {
            "list": [{
                "vod_id": "%s|%s" % (number, mid),
                "vod_name": "[%s] %s" % (number, html_lib.unescape(str(title))[:100]),
                "vod_pic": pic,
                "vod_actor": "JavDB",
                "vod_director": "JavDB",
                "vod_remarks": remarks,
                "vod_content": "\n".join(content_parts),
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        headers = {
            "User-Agent": self._ua,
            "Accept": "*/*",
        }
        # 磁力 / 外链
        if url.startswith("magnet:"):
            return {
                "parse": 0,
                "jx": 0,
                "url": url,
                "header": headers
            }
        if url.startswith("http"):
            return {
                "parse": 0,
                "jx": 0,
                "url": url,
                "header": headers
            }
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": headers
        }

    def localProxy(self, params):
        """图片代理：解决封面不显示"""
        try:
            if not isinstance(params, dict):
                params = {}
            do = str(params.get("do") or params.get("type") or "")
            if do == "pic":
                u = params.get("u") or params.get("url") or ""
                try:
                    pic = base64.urlsafe_b64decode(u.encode("utf-8")).decode("utf-8")
                except Exception:
                    pic = unquote(u)
                if not pic.startswith("http"):
                    return [404, "text/plain", "bad url"]
                raw = self._fetch(pic, headers={
                    "User-Agent": self._ua,
                    "Referer": "https://javdb.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                }, binary=True)
                if not raw:
                    return [404, "text/plain", "empty"]
                # 按魔数判断类型
                ct = "image/jpeg"
                if raw[:8] == b"\x89PNG\r\n\x1a\n":
                    ct = "image/png"
                elif raw[:2] == b"\xff\xd8":
                    ct = "image/jpeg"
                elif raw[:4] == b"GIF8":
                    ct = "image/gif"
                elif raw[:4] == b"RIFF":
                    ct = "image/webp"
                return [200, ct, raw]
            return [404, "text/plain", "not found"]
        except Exception as e:
            return [500, "text/plain", str(e)]

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        key = (key or "").strip()
        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        data = self._api("/v2/search", {"q": key, "page": str(page)})
        vod_list = self._parse_movies(data)
        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 10 else page,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "javdb spider ok"}

    def liveContent(self):
        return ""

    def destroy(self):
        self.options = {}
