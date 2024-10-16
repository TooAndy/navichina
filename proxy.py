import re
import requests
import traceback
from flask_caching import Cache
from functools import cache
from urllib.parse import unquote
from flask import Flask, abort, request, jsonify, redirect
from cover import  download_image_async
from search import get_album_info, get_artist_profile # type: ignore

app = Flask(__name__)


# 缓存
cache_dir = '/.cache'
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


@app.route('/spotify/search/', methods=['GET'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_spotfiy():
    search_type = request.args.get('type')
    spotify_origin_url = f"https://api.spotify.com/v1/search?{request.query_string.decode('utf-8')}"
    
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
                app.logger.info(f"400 GET /spotify/search/?{unquote(request.query_string.decode('utf-8'))}")
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
            app.logger.info(f"200 GET /spotify/search?{unquote(request.query_string.decode('utf-8'))}")

            # 查询成功的话, 下载封面放在 music_dir 中
            download_image_async(url, artist_name)
           
            return jsonify({"artists": {"items": items}})
        except:
            app.logger.error("Traceback: %s", traceback.format_exc())
        app.logger.warn(f"400 GET /spotify/search/?{unquote(request.query_string.decode('utf-8'))}")
        # 将你接口的返回内容直接返回给调用者
        abort(400, "暂时无法查询, 请稍后再试")
    else:
        # 对其他请求直接重定向到原接口
        app.logger.info(f"302 GET /spotify/search/?{unquote(request.query_string.decode('utf-8'))}")
        return redirect(spotify_origin_url)


@app.route('/lastfm/', methods=['GET'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def proxy_lastfm():
    lastfm_api_url = f"https://ws.audioscrobbler.com/2.0/?{request.query_string.decode('utf-8')}"

    lastfm_resp = requests.get(lastfm_api_url, headers=request.headers).json()
    artist_name = request.args.get('artist')
    if 'error' in lastfm_resp:
        app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
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
                app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
                return jsonify(lastfm_resp)
        except:
            pass
        app.logger.info(f"400 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
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
            app.logger.info(f"200 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
            download_image_async(album_info['picUrl'], artist_name, album_name)
            return jsonify(lastfm_resp)
        abort(400, {"code": 400, "message": f"无法根据 {artist_name} + {album_name} 查询到专辑"})
    else:
        # 对其他请求直接重定向到原接口
        app.logger.info(f"302 GET /lastfm/?{unquote(request.query_string.decode('utf-8'))}")
        return redirect(lastfm_api_url)
    