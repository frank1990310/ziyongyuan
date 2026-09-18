#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JavDB Web UI / catembylegacy  Python 蜘蛛
数据源：jdforrepam.com (JavDB API) + catembylegacy 播放解析
适用于 TVBox / 影视仓 / FongMi 等支持 Python 爬虫的客户端
"""

import re
import json
import time
import hashlib
import html as html_lib
import urllib.request
import urllib.parse
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
        # jdsignature 参数（来自前端）
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
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", "mpegurl", "proxy://"))

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

    def _movie_to_vod(self, m):
        if not isinstance(m, dict):
            return None
        mid = m.get("id") or ""
        number = m.get("number") or mid
        title = m.get("title") or m.get("origin_title") or number
        pic = m.get("cover_url") or m.get("thumb_url") or ""
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

        # vod_id 用 番号|内部id，方便详情与播放
        vod_id = "%s|%s" % (number, mid)
        return {
            "vod_id": vod_id,
            "vod_name": "[%s] %s" % (number, html_lib.unescape(str(title))[:80]),
            "vod_pic": pic,
            "vod_remarks": " · ".join(remarks) if remarks else number,
            "style": {"type": "rect", "ratio": 1.5}
        }

    def _parse_movies(self, data):
        movies = []
        if isinstance(data, dict):
            if isinstance(data.get("movies"), list):
                movies = data["movies"]
            elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("movies"), list):
                movies = data["data"]["movies"]
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
        vod_list = self._parse_movies(data)
        return {"list": vod_list[:24]}

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
            # 推荐无分页，本地切片
            page_size = 20
            start = (page - 1) * page_size
            vod_list = vod_list[start:start + page_size]
        elif tid.startswith("rank_"):
            kind = tid.replace("rank_", "", 1)
            # type + period
            data = self._api("/v1/rankings", {"type": kind, "period": "1"})
            vod_list = self._parse_movies(data)
            page_size = 20
            start = (page - 1) * page_size
            vod_list = vod_list[start:start + page_size]
        else:
            data = self._api("/v1/movies/latest", {"page": str(page)})
            vod_list = self._parse_movies(data)

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def _resolve_play(self, code):
        """调用前端解析接口，返回线路列表 [{name, url_or_playlist, is_data}]"""
        url = "%s/api/v/resolve?code=%s&lang=zh" % (self.host, quote(str(code)))
        text = self._fetch(url, headers={
            "Accept": "application/json",
            "Referer": self.host + "/",
        })
        if not text:
            return []
        try:
            data = json.loads(text)
        except Exception:
            return []
        lines = []
        for v in data.get("variants") or []:
            if not isinstance(v, dict):
                continue
            name = v.get("label") or v.get("variant") or "线路"
            src = (v.get("sourceUrl") or "").strip()
            if not src:
                continue
            lines.append({
                "name": name,
                "src": src,
                "variant": v.get("variant") or "",
            })
        return lines

    def _decode_source(self, src):
        """data: m3u8 解码为文本；http 直链原样返回"""
        if not src:
            return "", False
        if src.startswith("data:"):
            try:
                # data:application/vnd.apple.mpegurl,CONTENT
                if "," in src:
                    body = src.split(",", 1)[1]
                    body = unquote(body)
                    return body, True
            except Exception:
                return "", False
        if src.startswith("http"):
            return src, False
        return "", False

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        parts = str(raw).split("|", 1)
        number = parts[0].strip()
        mid = parts[1].strip() if len(parts) > 1 else ""

        # 用搜索补全信息
        info = {"number": number, "title": number, "cover_url": "", "id": mid}
        if number:
            sr = self._api("/v2/search", {"q": number, "page": "1"})
            for m in self._parse_movies(sr) and []:
                pass
            movies = []
            if isinstance(sr, dict):
                movies = (sr.get("data") or {}).get("movies") or []
            for m in movies:
                if str(m.get("number", "")).upper() == number.upper() or str(m.get("id")) == mid:
                    info = m
                    break
            if not mid and movies:
                info = movies[0]
                number = info.get("number") or number
                mid = info.get("id") or mid

        title = info.get("title") or info.get("origin_title") or number
        pic = info.get("cover_url") or info.get("thumb_url") or ""
        remarks = info.get("release_date") or ""
        actors = ""
        # magnets 作参考信息
        magnets = []
        if mid:
            mag = self._api("/v1/movies/%s/magnets" % mid)
            if isinstance(mag, dict):
                magnets = (mag.get("data") or {}).get("magnets") or []

        content_parts = ["番号：%s" % number]
        if info.get("duration"):
            content_parts.append("时长：%s 分钟" % info.get("duration"))
        if magnets:
            content_parts.append("磁力：%d 条" % len(magnets))
        content_parts.append("播放线路来自解析服务，请自行切换。")

        # 解析播放线路
        play_from = []
        play_url = []
        lines = self._resolve_play(number)
        for idx, line in enumerate(lines):
            name = line.get("name") or ("线路%d" % (idx + 1))
            src = line.get("src") or ""
            body, is_data = self._decode_source(src)
            if is_data and body:
                # 用代理播放：proxy_m3u8|番号|线路索引
                play_id = "m3u8|%s|%d" % (number, idx)
                play_from.append(name)
                play_url.append("正片$%s" % play_id)
            elif src.startswith("http"):
                play_from.append(name)
                play_url.append("正片$%s" % src)
            elif body:
                play_id = "m3u8|%s|%d" % (number, idx)
                play_from.append(name)
                play_url.append("正片$%s" % play_id)

        if not play_from:
            play_from = ["暂无线路"]
            play_url = ["提示$https://httpbin.org/status/404"]

        return {
            "list": [{
                "vod_id": "%s|%s" % (number, mid),
                "vod_name": "[%s] %s" % (number, html_lib.unescape(str(title))[:100]),
                "vod_pic": pic,
                "vod_actor": actors or "JavDB",
                "vod_director": "JavDB",
                "vod_remarks": str(remarks),
                "vod_content": "\n".join(content_parts),
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        pid = str(id).strip()
        headers = {
            "User-Agent": self._ua,
            "Accept": "*/*",
        }

        # 代理 m3u8：m3u8|番号|index
        if pid.startswith("m3u8|"):
            parts = pid.split("|")
            code = parts[1] if len(parts) > 1 else ""
            idx = int(parts[2]) if len(parts) > 2 and str(parts[2]).isdigit() else 0
            lines = self._resolve_play(code)
            if 0 <= idx < len(lines):
                src = lines[idx].get("src") or ""
                body, is_data = self._decode_source(src)
                if is_data and body:
                    # 走 localProxy
                    proxy = self.getProxyUrl()
                    if proxy:
                        # 常见格式：把内容 key 放 query
                        key = base64.urlsafe_b64encode(("%s|%d" % (code, idx)).encode()).decode()
                        url = proxy + ("&do=m3u8&key=%s" % key if "?" in proxy else "?do=m3u8&key=%s" % key)
                        return {
                            "parse": 0,
                            "jx": 0,
                            "url": url,
                            "header": headers
                        }
                    # 无代理时尝试直接返回 data URI（部分客户端支持）
                    return {
                        "parse": 0,
                        "jx": 0,
                        "url": src,
                        "header": headers
                    }
                if src.startswith("http"):
                    return {"parse": 0, "jx": 0, "url": src, "header": headers}

        if pid.startswith("http"):
            return {
                "parse": 0,
                "jx": 0,
                "url": pid,
                "header": headers
            }

        return {
            "parse": 1,
            "jx": 0,
            "url": pid,
            "header": headers
        }

    def localProxy(self, params):
        """提供 m3u8 文本代理，供 playerContent 使用"""
        try:
            if not isinstance(params, dict):
                params = {}
            do = params.get("do") or params.get("type") or ""
            if do != "m3u8":
                return [404, "text/plain", "not found"]

            key = params.get("key") or ""
            try:
                raw = base64.urlsafe_b64decode(key.encode()).decode()
            except Exception:
                raw = unquote(key)
            parts = raw.split("|")
            code = parts[0] if parts else ""
            idx = int(parts[1]) if len(parts) > 1 and str(parts[1]).isdigit() else 0

            lines = self._resolve_play(code)
            if not (0 <= idx < len(lines)):
                return [404, "text/plain", "no line"]

            src = lines[idx].get("src") or ""
            body, is_data = self._decode_source(src)
            if is_data and body:
                return [200, "application/vnd.apple.mpegurl", body]
            if src.startswith("http"):
                # 302 到真实地址
                return [302, "text/plain", src]
            return [404, "text/plain", "empty"]
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
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "javdb catemby spider ok"}

    def liveContent(self):
        return ""

    def destroy(self):
        self.options = {}
