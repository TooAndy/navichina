from functools import cache
import logging
import re
from urllib.parse import unquote
from flask import abort, request, jsonify, redirect
import traceback
import shutil
from flask import Flask, request
from flask_caching import Cache

import requests

from search import get_album_info, get_artist_profile # type: ignore

app = Flask(__name__)
 
 # 日志
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = app.logger.handlers[0]
console_handler.setFormatter(formatter)
app.logger.setLevel(logging.INFO)

# 缓存
cache_dir = './.cache'
# try:
#     shutil.rmtree(cache_dir)
# except FileNotFoundError:
#     pass

cache = Cache(app, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': cache_dir
})

# 缓存键，解决缓存未忽略参数的情况 COPY FROM LRCAPI
def make_cache_key(*args, **kwargs) -> str:
    path:str = request.path
    args:str = str(hash(frozenset(request.args.items())))
    # auth_key:str = str(request.headers.get('Authorization', '')
                    #    or request.headers.get('Authentication', ''))
    # cookie:str = str(request.cookies.get('api_auth_token', ''))
    return path + args


@app.route('/spotify/search', methods=['GET'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_spotfiy():
    search_type = request.args.get('type')
    spotify_origin_url = f"https://api.spotify.com/v1/search?{request.query_string.decode('utf-8')}"
    
    app.logger.debug(f"GET /spotify/search?{unquote(request.query_string.decode('utf-8'))}")
    # app.logger.debug(f"spotify_origin_url={spotify_origin_url}")
    
    if search_type == "artist":
        artist_name = request.args.get('q')
        artist_name_1 = None
        
        if any(substring in artist_name for substring in [' and ', "&"]):
            sp = re.split(r" and |&", artist_name)
            artist_name_1 = sp[0].strip()
        
        try:
            artist_profile = get_artist_profile(artist_name)
            if not artist_profile and artist_name_1 is not None:
                artist_profile = get_artist_profile(artist_name_1)

            if artist_profile:
                artist = artist_profile['artist']
                app.logger.debug(f"查询到 {artist['name']}")
            else:
                return jsonify({"code":400, "message": f"无法查询到名称为[{artist_name}]的艺术家"})

            items = []
            images = []
            url = artist['img1v1Url']
            for i in range(3):
                # height 和 width 在 navidrome 中, 只用作排序. 所以大具体值无所谓
                image = {"height": 160 * (i + 1),"width": 160 * (i + 1),"url": url}
                images.append(image)
            # items.append({"name":artist['name'], "popularity": 100, "images": images})
            items.append({"name":artist_name, "popularity": 100, "images": images})
            return jsonify({"artists": {"items": items}})
        except:
            app.logger.error("Traceback: %s", traceback.format_exc())
        # 将你接口的返回内容直接返回给调用者
        abort(400, "暂时无法查询, 请稍后再试")
    else:
        # 对其他请求直接重定向到原接口
        return redirect(spotify_origin_url)


@app.route('/lastfm', methods=['GET'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_lastfm():

    app.logger.debug(f"GET /lastfm?{unquote(request.query_string.decode('utf-8'))}")

    lastfm_api_url = f"https://ws.audioscrobbler.com/2.0/?{request.query_string.decode('utf-8')}"
    # app.logger.debug(f"lastfm_api_url={lastfm_api_url}")
    lastfm_resp = requests.get(lastfm_api_url, headers=request.headers).json()
    artist_name = request.args.get('artist')
    if 'error' in lastfm_resp:
        abort(400, {"code": 400, "message": f"无法在lastfm 中查询到 {artist_name}"})

    method = request.args.get('method')
    
    if method.lower() == "artist.getinfo":
        artist_name_1 = None
        if any(substring in artist_name for substring in [' and ', "&"]):
            # 尝试拆分名字.
            sp = re.split(r" and |&", artist_name)
            artist_name_1 = sp[0]

        try:
            artist_profile = get_artist_profile(artist_name)
            if not artist_profile and artist_name_1 is not None:
                artist_profile = get_artist_profile(artist_name_1)
            if artist_profile:
                artist = artist_profile['artist']
                lastfm_resp['artist']['bio']['content'] = artist['briefDesc']
                lastfm_resp['artist']['bio']['summary'] = artist['briefDesc']
                for image in lastfm_resp['artist']['image']:
                   if image['size'] in ['mega', 'extralarge', 'large']:
                       image['#text'] = artist['picUrl']
                   image['#text'] = artist['img1v1Url']
                return jsonify(lastfm_resp)
        except:
            pass
        abort(400, {"code": 400, "message": f"无法根据 {artist_name} 查询到艺术家"})
    elif method.lower() == "album.getinfo":
        # 从请求参数中获取专辑和艺术家信息
        artist_name = request.args.get('artist')
        album_name = request.args.get('album')
        mbid = request.args.get('mbid', "")

        # 查询网易云
        if album_info := get_album_info(artist_name, album_name):
            album_result = lastfm_resp["album"]
            album_result["mbid"] = mbid
            album_result["wiki"] =  {"summary": album_info['description']}
            for image in album_result['image']:
                if image['size'] in ['mega', 'extralarge', 'large']:
                    image['#text'] = album_info['picUrl']
                image['#text'] = album_info['blurPicUrl']
            return jsonify(lastfm_resp)
        abort(400, {"code": 400, "message": f"无法根据 {artist_name} + {album_name} 查询到专辑"})
    else:
        # 对其他请求直接重定向到原接口
        return redirect(lastfm_api_url)
    