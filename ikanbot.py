#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爱看机器人 ikanbot.com  Python 蜘蛛
适用于 TVBox / 影视仓 / FongMi 等支持 Python 爬虫的客户端
"""

import re
import json
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
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
        self.host = "https://www1.ikanbot.com"
        self._ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
        self.options = {}

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
        return "爱看机器人"

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
            with self.opener.open(req, timeout=12) as resp:
                raw = resp.read()
                enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _fetch_json(self, url, headers=None):
        text = self._fetch(url, headers)
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _extract_token(self, html):
        """根据页面 current_id 和 e_token 计算播放 token"""
        id_m = re.search(r'id=["\']current_id["\'][^>]*value=["\']([^"\']+)["\']', html)
        if not id_m:
            id_m = re.search(r'value=["\']([^"\']+)["\'][^>]*id=["\']current_id["\']', html)
        token_m = re.search(r'id=["\']e_token["\'][^>]*value=["\']([^"\']+)["\']', html)
        if not token_m:
            token_m = re.search(r'value=["\']([^"\']+)["\'][^>]*id=["\']e_token["\']', html)

        if not id_m or not token_m:
            return ""

        current_id = id_m.group(1)
        e_token = token_m.group(1)
        if not current_id or not e_token:
            return ""

        sub_id = current_id[-4:] if len(current_id) >= 4 else current_id
        keys = []
        for ch in sub_id:
            try:
                cur_int = int(ch)
            except Exception:
                cur_int = 0
            split_pos = cur_int % 3 + 1
            keys.append(e_token[split_pos:split_pos + 8])
            e_token = e_token[split_pos + 8:]
        return "".join(keys)

    def _parse_list_items(self, html):
        """解析列表页卡片"""
        vod_list = []
        seen = set()

        # 匹配 /play/数字
        pattern = r'<a[^>]+href=["\'](/play/(\d+))["\'][^>]*>[\s\S]*?</a>'
        blocks = re.findall(r'(<div[^>]*class=["\'][^"\']*item[^"\']*["\'][^>]*>[\s\S]*?</div>\s*</div>)', html)
        if not blocks:
            blocks = re.findall(r'(<a[^>]+href=["\']/play/\d+["\'][^>]*>[\s\S]*?</a>)', html)

        for block in blocks:
            href_m = re.search(r'href=["\'](/play/(\d+))["\']', block)
            if not href_m:
                continue
            path, vid = href_m.groups()
            if vid in seen:
                continue
            seen.add(vid)

            # 标题
            title = ""
            title_m = re.search(r'<[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</', block)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            if not title:
                alt_m = re.search(r'alt=["\']([^"\']+)["\']', block)
                if alt_m:
                    title = alt_m.group(1).strip()
            if not title:
                title = "影片" + vid

            title = html_lib.unescape(title)

            # 图片
            pic = ""
            pic_m = re.search(r'(?:data-src|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', block, re.I)
            if pic_m:
                pic = pic_m.group(1).strip()
                if pic.startswith("//"):
                    pic = "https:" + pic
                elif pic.startswith("/"):
                    pic = self.host + pic

            vod_list.append({
                "vod_id": path,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "爱看机器人",
                "style": {"type": "rect", "ratio": 0.7}
            })

        return vod_list

    def homeContent(self, filter):
        classes = [
            {"type_name": "热门电影", "type_id": "/hot/index-movie-热门.html"},
            {"type_name": "热门剧集", "type_id": "/hot/index-tv-热门.html"},
            {"type_name": "全部影片", "type_id": "/kanlist/全部-p-1.html"},
            {"type_name": "电影", "type_id": "/category/电影"},
            {"type_name": "电视剧", "type_id": "/category/电视剧"},
            {"type_name": "综艺", "type_id": "/category/综艺"},
            {"type_name": "动漫", "type_id": "/category/动漫"},
        ]
        return {"class": classes}

    def homeVideoContent(self):
        html = self._fetch(self.host + "/hot/index-movie-热门.html")
        vod_list = self._parse_list_items(html)
        return {"list": vod_list[:20]}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        path = str(tid).strip()

        if path.startswith("/hot/") or path.startswith("/kanlist/"):
            if page > 1 and "-p-" not in path:
                # 简单处理分页
                if path.endswith(".html"):
                    path = path.replace(".html", "-p-%d.html" % page)
            target = self.host + path
        elif path.startswith("/category/"):
            target = self.host + path
            if page > 1:
                target += "?page=%d" % page
        else:
            target = self.host + path

        html = self._fetch(target)
        vod_list = self._parse_list_items(html)

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        path = raw if raw.startswith("/") else "/play/" + raw
        if not path.startswith("/play/"):
            path = "/play/" + path.lstrip("/")

        html = self._fetch(self.host + path)
        if not html:
            return {"list": []}

        # 标题
        title_m = re.search(r'<h1[^>]*id=["\']video_title["\'][^>]*>([\s\S]*?)</h1>', html)
        vod_name = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "精彩影片"
        vod_name = html_lib.unescape(vod_name)

        # 封面
        pic = ""
        pic_m = re.search(r'(?:data-src|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', html, re.I)
        if pic_m:
            pic = pic_m.group(1)
            if pic.startswith("//"):
                pic = "https:" + pic

        # videoId
        vid_m = re.search(r'/play/(\d+)', path)
        video_id = vid_m.group(1) if vid_m else ""

        # mtype
        mtype = "2"
        mtype_m = re.search(r'id=["\']mtype["\'][^>]*value=["\']([^"\']+)["\']', html)
        if mtype_m:
            mtype = mtype_m.group(1)

        # 计算 token
        token = self._extract_token(html)

        play_from = []
        play_url = []

        if video_id and token:
            api = "%s/api/getResN?videoId=%s&mtype=%s&token=%s" % (
                self.host, video_id, mtype, quote(token)
            )
            data = self._fetch_json(api, headers={
                "User-Agent": self._ua,
                "Referer": self.host + path,
                "X-Requested-With": "XMLHttpRequest"
            })

            if data.get("state") == 1:
                data_list = data.get("data", {}).get("list", [])
                for idx, item in enumerate(data_list):
                    line_name = "线路%d" % (idx + 1)
                    res_raw = item.get("resData", "")
                    try:
                        # 有些返回是字符串形式的数组
                        if isinstance(res_raw, str):
                            res = eval(res_raw) if res_raw.strip().startswith("[") else []
                        else:
                            res = res_raw or []
                    except Exception:
                        res = []

                    ep_parts = []
                    for j, r in enumerate(res):
                        if not isinstance(r, dict):
                            continue
                        u = r.get("url", "")
                        name = r.get("newName") or r.get("name") or ("正片" if j == 0 else "第%d集" % (j + 1))
                        if u:
                            # 有些是多集用 # 分隔
                            if "#" in u and "$" not in u:
                                for part in u.split("#"):
                                    if part.strip():
                                        ep_parts.append("%s$%s" % (name, part.strip()))
                            else:
                                ep_parts.append("%s$%s" % (name, u))

                    if ep_parts:
                        play_from.append(line_name)
                        play_url.append("#".join(ep_parts))

        if not play_from:
            # 兜底：返回页面本身让客户端嗅探
            play_from = ["网页线路"]
            play_url = ["正片$%s%s" % (self.host, path)]

        return {
            "list": [{
                "vod_id": path,
                "vod_name": vod_name,
                "vod_pic": pic,
                "vod_actor": "爱看机器人",
                "vod_director": "爱看机器人",
                "vod_remarks": "多线路",
                "vod_content": "资源来自全网聚合，线路质量参差不齐，请自行切换。",
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        # 如果是页面链接则开启嗅探，否则直接播放
        is_page = not self.isVideoFormat(url)
        return {
            "parse": 1 if is_page else 0,
            "jx": 0,
            "url": url,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.host + "/"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        encoded = quote(key)
        # 搜索地址（常见写法）
        search_url = "%s/search?q=%s" % (self.host, encoded)
        if page > 1:
            search_url += "&page=%d" % page

        html = self._fetch(search_url)
        if not html:
            # 备用搜索路径
            search_url2 = "%s/search/%s" % (self.host, encoded)
            html = self._fetch(search_url2)

        vod_list = self._parse_list_items(html)

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 9999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ikanbot spider ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Disabled"]

    def destroy(self):
        self.options = {}
