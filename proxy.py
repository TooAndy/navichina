import re
import os
import traceback
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable
import requests
from flask_caching import Cache
from flask import Flask, abort, request, jsonify, redirect
from cover import download_image_async
from search import get_album_info, get_artist_profile, get_artist_top_songs, get_similar_songs  # type: ignore

app = Flask(__name__)

# ========== 常量定义 ==========
SENSITIVE_PARAMS = ['api_key', 'token', 'password', 'secret', 'key']
DEFAULT_TIMEOUT = 9  # 默认超时时间（秒）
CACHE_TIMEOUT = 86400  # 缓存默认过期时间（秒）
CACHE_THRESHOLD = 1000  # 最大缓存项数

# ========== 数据结构 ==========

@dataclass
class QueryResult:
    """查询结果封装类"""
    netease_data: Optional[Dict[str, Any]] = None
    lastfm_data: Optional[Dict[str, Any]] = None
    netease_success: bool = False
    lastfm_success: bool = False
    elapsed_time: float = 0
    netease_error: Optional[str] = None
    lastfm_error: Optional[str] = None

# ========== 工具函数 ==========

def filter_sensitive_params(params_dict: Dict[str, Any], redact: bool = False) -> Dict[str, Any]:
    """过滤或隐藏敏感参数"""
    result = {}
    for key, value in params_dict.items():
        is_sensitive = any(sensitive in key.lower() for sensitive in SENSITIVE_PARAMS)
        if is_sensitive:
            if redact:
                result[key] = '[REDACTED]'
            # 不 redact 时跳过该参数
        else:
            result[key] = value
    return result

def build_image_array(small_url: str, large_url: str) -> list:
    """构建标准 Last.fm 格式的 image 数组"""
    return [
        {"#text": small_url, "size": "small"},
        {"#text": small_url, "size": "medium"},
        {"#text": large_url, "size": "large"},
        {"#text": large_url, "size": "extralarge"},
        {"#text": large_url, "size": "mega"},
        {"#text": large_url, "size": ""}
    ]

def log_query_result(method_name: str, netease_success: bool, lastfm_success: bool,
                     netease_error: Optional[str], lastfm_error: Optional[str], 
                     identifier: str, elapsed_time: float):
    """统一记录查询结果日志"""
    app.logger.debug(f"{method_name}并行查询总耗时: {elapsed_time:.2f}秒")
    
    if netease_success:
        app.logger.debug(f"成功获取网易云数据: {identifier}")
    elif netease_error:
        if netease_error == "Timeout":
            app.logger.warning(f"网易云查询超时: {identifier}")
        else:
            app.logger.error(f"网易云查询异常: {netease_error}")
    
    if lastfm_success:
        app.logger.debug(f"成功获取Last.fm数据: {identifier}")
    elif lastfm_error:
        if lastfm_error == "Timeout":
            app.logger.warning(f"Last.fm查询超时: {identifier}")
        else:
            app.logger.error(f"Last.fm查询异常: {lastfm_error}")

def parallel_query(netease_fetch_func: Callable, lastfm_api_url: str, timeout: int = DEFAULT_TIMEOUT) -> QueryResult:
    """
    通用并行查询函数，同时查询网易云和Last.fm数据
    :param netease_fetch_func: 获取网易云数据的函数
    :param lastfm_api_url: Last.fm API URL
    :param timeout: 超时时间（秒）
    :return: QueryResult 对象
    """
    result = QueryResult()
    start_time = time.time()
    
    def fetch_netease_data():
        try:
            data = netease_fetch_func()
            if data:
                return ('success', data)
            else:
                return ('no_data', None)
        except Exception as e:
            return ('error', e)
    
    def fetch_lastfm_data():
        try:
            lastfm_response = session.get(lastfm_api_url, timeout=timeout)
            if lastfm_response.status_code == 200:
                lastfm_data = lastfm_response.json()
                if 'error' not in lastfm_data:
                    return ('success', lastfm_data)
                else:
                    return ('error', f"Last.fm返回错误: {lastfm_data.get('error')}")
            else:
                return ('error', f"Last.fm HTTP错误: {lastfm_response.status_code}")
        except requests.exceptions.Timeout:
            return ('timeout', None)
        except Exception as e:
            return ('error', e)
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        netease_future = executor.submit(fetch_netease_data)
        lastfm_future = executor.submit(fetch_lastfm_data)
        
        # 等待两个任务完成，设置超时
        try:
            netease_result = netease_future.result(timeout=timeout)
        except Exception as e:
            netease_result = ('error', e)
        
        try:
            lastfm_result = lastfm_future.result(timeout=timeout)
        except Exception as e:
            lastfm_result = ('error', e)
    
    result.elapsed_time = time.time() - start_time
    
    # 处理网易云结果
    if netease_result[0] == 'success':
        result.netease_data = netease_result[1]
        result.netease_success = True
    elif netease_result[0] == 'timeout':
        result.netease_error = "Timeout"
    elif netease_result[0] == 'error':
        result.netease_error = netease_result[1]
    
    # 处理Last.fm结果
    if lastfm_result[0] == 'success':
        result.lastfm_data = lastfm_result[1]
        result.lastfm_success = True
    elif lastfm_result[0] == 'timeout':
        result.lastfm_error = "Timeout"
    elif lastfm_result[0] == 'error':
        result.lastfm_error = lastfm_result[1]
    
    return result

def parallel_query_artist_info(artist_name: str, lastfm_api_url: str, 
                               get_artist_profile_func: Callable, timeout: int = DEFAULT_TIMEOUT) -> QueryResult:
    """并行查询艺术家信息"""
    def fetch_netease_data():
        artist_name_1 = None
        if any(substring in artist_name for substring in [' and ', "&"]):
            sp = re.split(r" and |&", artist_name)
            artist_name_1 = sp[0]
        
        artist_profile = get_artist_profile_func(artist_name)
        if not artist_profile and artist_name_1 is not None:
            artist_profile = get_artist_profile_func(artist_name_1)
        
        if artist_profile:
            return artist_profile['artist']
        return None
    
    return parallel_query(fetch_netease_data, lastfm_api_url, timeout)

def parallel_query_album_info(artist_name: str, album_name: str, lastfm_api_url: str,
                              get_album_info_func: Callable, timeout: int = DEFAULT_TIMEOUT) -> QueryResult:
    """并行查询专辑信息"""
    def fetch_netease_data():
        return get_album_info_func(artist_name, album_name)
    
    return parallel_query(fetch_netease_data, lastfm_api_url, timeout)

def parallel_query_artist_toptracks(artist_name: str, limit: int, lastfm_api_url: str,
                                    get_artist_top_songs_func: Callable, timeout: int = DEFAULT_TIMEOUT) -> QueryResult:
    """并行查询艺术家热门歌曲"""
    def fetch_netease_data():
        return get_artist_top_songs_func(artist_name, limit)
    
    return parallel_query(fetch_netease_data, lastfm_api_url, timeout)


# 缓存
cache_dir = './.cache'
# try:
#     shutil.rmtree(cache_dir)
# except FileNotFoundError:
#     pass

cache = Cache(app, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': cache_dir,
    'CACHE_DEFAULT_TIMEOUT': 86400,  # 缓存默认过期时间（秒）
    'CACHE_THRESHOLD': 1000  # 最大缓存项数，超过后会自动清理
})

# 创建全局 requests.Session 对象
session = requests.Session()

# 缓存键，解决缓存未忽略参数的情况 COPY FROM LRCAPI

def make_cache_key(*args, **kwargs) -> str:
    path: str = request.path
    # 过滤掉敏感参数后再生成缓存键
    filtered_args = filter_sensitive_params(request.args.to_dict(), redact=False)
    args_hash: str = str(hash(frozenset(filtered_args.items())))
    return path + args_hash

def safe_query_string() -> str:
    """返回安全的查询字符串，隐藏敏感信息如api_key"""
    safe_dict = filter_sensitive_params(request.args.to_dict(), redact=True)
    
    # 构建查询字符串，但不进行URL编码
    # 这样日志中会显示解码后的中文，而不是URL编码
    query_parts = []
    for key, value in safe_dict.items():
        query_parts.append(f"{key}={value}")
    
    return "&".join(query_parts)


@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    """清空缓存目录"""
    try:
        shutil.rmtree(cache_dir)
        # 重新创建缓存目录
        import os
        os.makedirs(cache_dir, exist_ok=True)
        app.logger.info("缓存已清空")
        return jsonify({"status": "success", "message": "缓存已清空"}), 200
    except Exception as e:
        app.logger.error(f"清空缓存时出错: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/lastfm/', methods=['GET', 'POST'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_lastfm():
    lastfm_api_url = f"https://ws.audioscrobbler.com/2.0/?{request.query_string.decode('utf-8')}"

    if request.method == "POST":
        resp = session.post(lastfm_api_url, json=None, headers=request.headers)
        app.logger.info(f"{resp.status_code} POST /lastfm/?{safe_query_string()}")
        return jsonify(resp.json()), resp.status_code

    method = request.args.get('method')
    if not method:
        abort(400, {"code": 400, "message": "缺少 method 参数"})
    
    method = method.lower()
    
    if method == "artist.getinfo":
        artist_name = request.args.get('artist')
        if not artist_name:
            abort(400, {"code": 400, "message": "缺少 artist 参数"})
        
        # 并行查询网易云和Last.fm数据
        query_result = parallel_query_artist_info(
            artist_name=artist_name,
            lastfm_api_url=lastfm_api_url,
            get_artist_profile_func=get_artist_profile,
            timeout=DEFAULT_TIMEOUT
        )
        
        # 使用通用日志记录函数
        log_query_result("artist.getinfo", query_result.netease_success, query_result.lastfm_success,
                        query_result.netease_error, query_result.lastfm_error, artist_name, query_result.elapsed_time)
        
        # 根据获取的数据情况决定返回什么
        if query_result.lastfm_success:
            # 有Last.fm数据，以其为模板
            result = query_result.lastfm_data
            
            # 如果有网易云数据，用网易云数据补充（网易云数据优先）
            if query_result.netease_success:
                # 替换image标签为网易云数据
                artist_result = result['artist']
                
                # 获取网易云图片URL
                netease_img1v1 = query_result.netease_data.get('img1v1Url', '')
                netease_pic = query_result.netease_data.get('picUrl', '')
                
                # 更新image数组
                if 'image' in artist_result:
                    for img in artist_result['image']:
                        size = img.get('size', '')
                        if size in ['small', 'medium']:
                            img['#text'] = netease_img1v1
                        elif size in ['large', 'extralarge', 'mega', '']:
                            img['#text'] = netease_pic
                
                # 更新bio summary
                if 'bio' in artist_result:
                    netease_brief = query_result.netease_data.get('briefDesc', '')
                    if netease_brief:
                        artist_result['bio']['summary'] = netease_brief
                        artist_result['bio']['content'] = netease_brief
                
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云+Last.fm合并)")
            else:
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅Last.fm)")
            
            return jsonify(result)
        
        elif query_result.netease_success:
            # 只有网易云数据，构建Last.fm格式的响应
            netease_img1v1 = query_result.netease_data.get('img1v1Url', '')
            netease_pic = query_result.netease_data.get('picUrl', '')
            netease_brief = query_result.netease_data.get('briefDesc', '')
            
            # 构建标准Last.fm结构
            lastfm_resp = {
                "artist": {
                    "name": artist_name,
                    "mbid": "",  # 网易云没有mbid
                    "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}",
                    "image": build_image_array(netease_img1v1, netease_pic),
                    "streamable": "0",
                    "ontour": "0",
                    "stats": {
                        "listeners": "0",
                        "playcount": "0"
                    },
                    "similar": {
                        "artist": []
                    },
                    "tags": {
                        "tag": []
                    },
                    "bio": {
                        "links": {
                            "link": {
                                "#text": "",
                                "rel": "original",
                                "href": f"https://last.fm/music/{artist_name.replace(' ', '+')}/+wiki"
                            }
                        },
                        "published": "01 Jan 1970, 00:00",
                        "summary": netease_brief,
                        "content": netease_brief
                    }
                }
            }
            
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅网易云)")
            return jsonify(lastfm_resp)
        
        else:
            # 两者都没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{safe_query_string()}")
            abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name}"})
    elif method == "album.getinfo":
        # 从请求参数中获取专辑和艺术家信息
        artist_name = request.args.get('artist')
        album_name = request.args.get('album')
        mbid = request.args.get('mbid', "")
        
        if not artist_name or not album_name:
            abort(400, {"code": 400, "message": "缺少 artist 或 album 参数"})
        
        # 并行查询网易云和Last.fm数据
        query_result = parallel_query_album_info(
            artist_name=artist_name,
            album_name=album_name,
            lastfm_api_url=lastfm_api_url,
            get_album_info_func=get_album_info,
            timeout=DEFAULT_TIMEOUT
        )
        
        # 使用通用日志记录函数
        identifier = f"{artist_name} - {album_name}"
        log_query_result("album.getinfo", query_result.netease_success, query_result.lastfm_success,
                        query_result.netease_error, query_result.lastfm_error, identifier, query_result.elapsed_time)
        
        # 根据获取的数据情况决定返回什么
        if query_result.lastfm_success:
            # 有Last.fm数据，以其为模板
            result = query_result.lastfm_data
            
            # 如果有网易云数据，用网易云数据补充（网易云数据优先）
            if query_result.netease_success:
                # 替换image标签为网易云数据
                album_result = result['album']
                
                # 获取网易云图片URL
                netease_blur_pic = query_result.netease_data.get('blurPicUrl', '')
                netease_pic = query_result.netease_data.get('picUrl', '')
                
                # 更新image数组
                if 'image' in album_result:
                    for img in album_result['image']:
                        size = img.get('size', '')
                        if size in ['small', 'medium']:
                            img['#text'] = netease_blur_pic
                        elif size in ['large', 'extralarge', 'mega', '']:
                            img['#text'] = netease_pic
                
                # 更新wiki summary
                if 'wiki' in album_result:
                    netease_desc = query_result.netease_data.get('description', '')
                    if netease_desc:
                        album_result['wiki']['summary'] = netease_desc
                        album_result['wiki']['content'] = netease_desc
                
                # 下载封面
                download_image_async(netease_pic, artist_name, album_name)
                
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云+Last.fm合并)")
            else:
                app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅Last.fm)")
            
            return jsonify(result)
        
        elif query_result.netease_success:
            # 只有网易云数据，构建Last.fm格式的响应
            netease_blur_pic = query_result.netease_data.get('blurPicUrl', '')
            netease_pic = query_result.netease_data.get('picUrl', '')
            netease_desc = query_result.netease_data.get('description', '')
            
            # 构建标准Last.fm结构
            lastfm_resp = {
                "album": {
                    "name": album_name,
                    "artist": artist_name,
                    "mbid": mbid,
                    "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}/{album_name.replace(' ', '+')}",
                    "image": build_image_array(netease_blur_pic, netease_pic),
                    "listeners": "0",
                    "playcount": "0",
                    "tracks": {
                        "track": []
                    },
                    "tags": {
                        "tag": []
                    },
                    "wiki": {
                        "published": "01 Jan 1970, 00:00",
                        "summary": netease_desc,
                        "content": netease_desc
                    }
                }
            }
            
            # 下载封面
            download_image_async(netease_pic, artist_name, album_name)
            
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (仅网易云)")
            return jsonify(lastfm_resp)
        
        else:
            # 两者都没有数据，返回400错误
            app.logger.info(f"400 GET /lastfm/?{safe_query_string()}")
            abort(400, {"code": 400, "message": f"无法查询到专辑 {album_name} (艺术家: {artist_name})"})
    elif method == "artist.gettoptracks":
        # 获取艺术家热门歌曲
        artist_name = request.args.get('artist')
        limit = int(request.args.get('limit', 50))
        
        if not artist_name:
            abort(400, {"code": 400, "message": "缺少 artist 参数"})
        
        # 并行查询网易云和Last.fm数据
        query_result = parallel_query_artist_toptracks(
            artist_name=artist_name,
            limit=limit,
            lastfm_api_url=lastfm_api_url,
            get_artist_top_songs_func=get_artist_top_songs,
            timeout=DEFAULT_TIMEOUT
        )
        
        # 使用通用日志记录函数
        log_query_result("artist.gettoptracks", query_result.netease_success, query_result.lastfm_success,
                        query_result.netease_error, query_result.lastfm_error, artist_name, query_result.elapsed_time)
        
        # 根据获取的数据情况决定返回什么
        # 1. 如果有网易云数据，以网易云数据填充Last.fm格式，抛弃Last.fm数据
        if query_result.netease_success:
            tracks = []
            for i, song in enumerate(query_result.netease_data[:limit]):
                track = {
                    "name": song.get('name', ''),
                    "duration": str(song.get('duration', 0)),
                    "playcount": str(song.get('playCount', 0)),
                    "listeners": str(song.get('listeners', 0)),
                    "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}/_/{song.get('name', '').replace(' ', '+')}",
                    "artist": {
                        "name": artist_name,
                        "mbid": "",
                        "url": f"https://www.last.fm/music/{artist_name.replace(' ', '+')}"
                    },
                    "image": build_image_array(
                        song.get('album', {}).get('picUrl', ''),
                        song.get('album', {}).get('picUrl', '')
                    ),
                    "@attr": {
                        "rank": str(i + 1)
                    }
                }
                tracks.append(track)
            
            lastfm_resp = {
                "toptracks": {
                    "track": tracks,
                    "@attr": {
                        "artist": artist_name,
                        "page": "1",
                        "perPage": str(len(tracks)),
                        "totalPages": "1",
                        "total": str(len(tracks))
                    }
                }
            }
            
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云数据填充)")
            return jsonify(lastfm_resp)
        
        # 2. 如果网易云超时/无数据，但Last.fm有数据，使用Last.fm数据
        elif query_result.lastfm_success:
            app.logger.info(f"200 GET /lastfm/?{safe_query_string()} (网易云无数据，使用Last.fm)")
            return jsonify(query_result.lastfm_data)
        
        # 3. 两者都没有数据，返回400错误
        else:
            app.logger.info(f"400 GET /lastfm/?{safe_query_string()} (无数据)")
            abort(400, {"code": 400, "message": f"无法查询到艺术家 {artist_name} 的热门歌曲"})
    elif method.lower() in ["track.getsimilar", "artist.getsimilar"]:
        # 对于相似歌曲和相似艺术家，直接重定向到Last.fm原生接口
        app.logger.info(f"302 GET /lastfm/?{safe_query_string()} (重定向到Last.fm)")
        return redirect(lastfm_api_url)
    else:
        # 对其他请求直接重定向到原接口
        app.logger.info(f"302 GET /lastfm/?{safe_query_string()}")
        return redirect(lastfm_api_url)
