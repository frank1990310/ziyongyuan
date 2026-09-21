var rule = {
    title: '2048ai短剧视频',
    host: 'https://2048ai.vip',
    url: '/api/v1/videos?productId=1&categoryId=fyclass&page=fypage&size=20',
    searchUrl: '',
    searchable: 0,
    quickSearch: 0,
    headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://2048ai.vip/media/'
    },
    // 异步分类：获取视频分类及短剧
    class_name: 'AI短剧&' + JV.ajax('https://2048ai.vip/api/v1/categories?type=video').data.map(item => item.name).join('&'),
    class_url: 'short_drama&' + JV.ajax('https://2048ai.vip/api/v1/categories?type=video').data.map(item => item.id).join('&'),
    
    // 列表解析
    lazy: `js:
        var videoPath = input.replace('https://2048ai.vip', '');
        var proxyUrl = 'https://2048ai.vip/api/v1/m3u8/proxy?path=' + encodeURIComponent(videoPath.replace(/^\\/+/, ''));
        input = {parse: 0, url: proxyUrl};
    `,
    
    // 主页推荐/分类列表数据加载
    tab_rename: {'short_drama': 'AI短剧'},
    
    // 列表数据解析
    list: `js:
        var d = [];
        if (MY_CATE === 'short_drama') {
            // 获取短剧列表
            var html = JV.ajax('https://2048ai.vip/api/v1/short-dramas?productId=1&sortBy=heat&page=' + FYPAGE + '&size=20');
            var items = html.data.items;
            items.forEach(function(item) {
                d.push({
                    title: item.title,
                    img: item.coverUrl || '',
                    desc: '共' + item.episodeCount + '集 | 热度:' + item.heatCount,
                    url: item.id
                });
            });
        } else {
            // 获取普通分类视频
            var html = JV.ajax('https://2048ai.vip/api/v1/videos?productId=1&categoryId=' + MY_CATE + '&page=' + FYPAGE + '&size=20');
            var items = html.data.items;
            items.forEach(function(item) {
                var mins = Math.floor((item.durationSec || 0) / 60);
                d.push({
                    title: item.title,
                    img: item.coverUrl || '',
                    desc: mins + '分钟 | 播放量:' + item.viewCount,
                    url: item.videoUrl
                });
            });
        }
        setResult(d);
    `,
    
    // 二级详情解析（针对短剧的选集）
    recommend: '',
    single: `js:
        var d = [];
        if (MY_URL.toString().indexOf('/') == -1 && !MY_URL.toString().startsWith('http')) {
            // 说明是短剧 ID，需要请求短剧详情获取剧集
            var detail = JV.ajax('https://2048ai.vip/api/v1/short-dramas/' + MY_URL + '?productId=1');
            var episodes = detail.data.episodes;
            var vod_items = [];
            episodes.forEach(function(ep) {
                vod_items.push('第' + ep.episodeNo + '集$' + ep.videoUrl);
            });
            let vod = {
                vod_id: MY_URL,
                vod_name: detail.data.title,
                vod_pic: detail.data.coverUrl || '',
                type_name: '短剧',
                vod_year: '',
                vod_area: '',
                vod_remarks: '共' + episodes.length + '集',
                vod_actor: '',
                vod_director: '',
                vod_content: detail.data.description || '',
                vod_play_from: '2048ai',
                vod_play_url: vod_items.join('#')
            };
            setResult(vod);
        } else {
            // 普通视频直接播放
            let vod = {
                vod_id: MY_URL,
                vod_name: '视频播放',
                vod_play_from: '2048ai',
                vod_play_url: '完整视频$' + MY_URL
            };
            setResult(vod);
        }
    `
};