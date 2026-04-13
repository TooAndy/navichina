import logging
import random

import requests
import urllib

from textcompare import association
from ttscn import t2s


# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
    'origin': 'https://music.163.com',
    'referer': 'https://music.163.com',
}

# 第三方API域名列表，每次随机选择一个
THIRD_PARTY_DOMAINS = ['apis.netstart.cn/music', 'apic.netstart.cn/music', 'ncm.zhenxin.me', 'ncmapi.btwoa.com']

def get_random_domain():
    """随机选择一个第三方API域名"""
    return random.choice(THIRD_PARTY_DOMAINS)

def build_search_url(keywords, search_type=100, limit=1):
    """构建搜索URL，使用第三方API"""
    domain = get_random_domain()
    keywords_encoded = urllib.parse.quote(keywords)
    return f'https://{domain}/search?keywords={keywords_encoded}&type={search_type}&limit={limit}'

def build_artist_detail_url(artist_id):
    """构建歌手详情URL，使用第三方API"""
    domain = get_random_domain()
    return f'https://{domain}/artist/detail?id={artist_id}'

def build_artist_albums_url(artist_id, limit=300):
    """构建歌手专辑列表URL，使用第三方API"""
    domain = get_random_domain()
    return f'https://{domain}/artist/album?id={artist_id}&limit={limit}'

def build_album_info_url(album_id):
    """构建专辑详情URL，使用第三方API"""
    domain = get_random_domain()
    return f'https://{domain}/album?id={album_id}'

def build_artist_top_songs_url(artist_id, limit=50):
    """构建歌手热门歌曲URL，使用第三方API"""
    domain = get_random_domain()
    return f'https://{domain}/artist/top/song?id={artist_id}&limit={limit}'

def build_similar_songs_url(song_id, limit=50):
    """构建相似歌曲URL，使用第三方API"""
    domain = get_random_domain()
    return f'https://{domain}/simi/song?id={song_id}&limit={limit}'


def listify(obj):
    if isinstance(obj, list):
        return obj
    else:
        return [obj]


def search_artist_blur(artist_blur, limit=1):
    """ 由于没有选择交互的过程, 因此 artist_blur 如果输入的不准确, 可能会查询到错误的歌手 """
    # logging.info('开始搜索: ' + artist_blur)
    
    if not artist_blur:
        logging.info('Missing artist. Skipping match')
        return None

    # 使用第三方API搜索歌手
    url = build_search_url(artist_blur.lower(), search_type=100, limit=limit)
    artists = []
    try:
        response = requests.get(url=url, headers=headers).json()
        if response['code'] == 200:
            artist_results = response['result']
            num = int(artist_results['artistCount'])
            lim = min(limit, num)
            # logging.info('搜索到的歌手数量：' + str(lim))
            for i in range(lim):
                try:
                    artists = listify(artist_results['artists'])
                except:
                    logging.error('Error retrieving artist search results.')
        else:
            logging.error(f'API returned error code: {response["code"]}')
    except Exception as e:
        logging.error(f'Error retrieving artist search results: {e}')
    if len(artists) > 0:
        return artists[0]
    return None


def search_artist(artist_id):
    if not artist_id:
        # logging.info('Missing artist. Skipping match')
        return None
    # 使用第三方API查询歌手详情
    url = build_artist_detail_url(artist_id)
    try:
        resp = requests.get(url=url, headers=headers).json()
        if resp['code'] == 200:
            return resp['data']  # 第三方API返回的数据在data字段中
        else:
            logging.error(f'Artist detail API returned error code: {resp["code"]}')
            return None
    except Exception as e:
        logging.error(f'Error retrieving artist detail: {e}')
        return None


def search_albums(artist_id):
    # 使用第三方API查询歌手专辑列表
    url = build_artist_albums_url(artist_id, limit=300)
    try:
        resp = requests.get(url=url, headers=headers).json()
        if resp['code'] == 200:
            return resp['hotAlbums']  # 第三方API直接返回hotAlbums字段
        else:
            logging.error(f'Artist albums API returned error code: {resp["code"]}')
            return None
    except Exception as e:
        logging.error(f'Error retrieving artist albums: {e}')
        return None


def filter_and_get_album_id(album_list, album):
    most_similar = None 
    highest_similarity = 0
    
    for candidate_album in album_list:
        if album == candidate_album['name']:
            return candidate_album['id']
        similarity = association(album, candidate_album['name'])
        if similarity > highest_similarity:
            highest_similarity = similarity
            most_similar = candidate_album
    return most_similar['id'] if most_similar is not None else None


def get_album_info_by_id(album_id):
    # 使用第三方API查询专辑详情
    url = build_album_info_url(album_id)
    try:
        resp = requests.get(url=url, headers=headers).json()
        if resp['code'] == 200:
            return resp['album']  # 第三方API直接返回album字段
        else:
            logging.error(f'Album info API returned error code: {resp["code"]}')
            return None
    except Exception as e:
        logging.error(f'Error retrieving album info: {e}')
        return None


def get_album_info(artist, album):
    artist = t2s(artist)
    album = t2s(album)
    # 1. 根据 artist, 获取 artist_id
    if blur_result := search_artist_blur(artist_blur=artist):
        artist_id = blur_result['id']
        # 2. 根据 artist_id 查询所有专辑
        if album_list := search_albums(artist_id):
            # 3. 根据 album, 过滤, 并获取到 album_id
            if album_id := filter_and_get_album_id(album_list, album):
                # 4. 根据 album_id, 查询 album_info
                return get_album_info_by_id(album_id)
    return None


def get_artist_profile(artist):
    artist = t2s(artist)
    if artist is None or artist.strip() == '':
        return None
    
    # 首先搜索艺术家获取ID
    blur_result = search_artist_blur(artist_blur=artist)
    if not blur_result:
        return None
    
    # 检查搜索结果是否匹配输入的艺术家名
    # 如果搜索结果与输入名差异太大，可能不是同一个艺术家
    result_name = blur_result.get('name', '').lower()
    input_name = artist.lower()
    
    # 简单检查：如果结果名不包含输入名，且输入名也不包含结果名，可能匹配错误
    if input_name not in result_name and result_name not in input_name:
        # 尝试检查别名
        aliases = blur_result.get('alias', [])
        alias_match = any(input_name in alias.lower() or alias.lower() in input_name for alias in aliases)
        if not alias_match:
            # 可能匹配到了错误的艺术家
            return None
    
    # 获取艺术家详情
    profile = search_artist(blur_result['id'])
    if not profile:
        return None
    
    # 确保返回的数据结构包含proxy.py需要的字段
    if 'artist' in profile:
        artist_data = profile['artist']
        # 确保有picUrl和img1v1Url字段（从cover和avatar字段映射）
        if 'cover' in artist_data and 'picUrl' not in artist_data:
            artist_data['picUrl'] = artist_data['cover']
        if 'avatar' in artist_data and 'img1v1Url' not in artist_data:
            artist_data['img1v1Url'] = artist_data['avatar']
    
    return profile


def get_artist_top_songs(artist_name, limit=50):
    """获取歌手热门歌曲"""
    artist = t2s(artist_name)
    if artist is None or artist.strip() == '':
        return None
    
    # 1. 搜索歌手获取ID
    if blur_result := search_artist_blur(artist_blur=artist):
        artist_id = blur_result['id']
        
        # 2. 使用第三方API查询歌手热门歌曲
        url = build_artist_top_songs_url(artist_id, limit=limit)
        try:
            resp = requests.get(url=url, headers=headers).json()
            if resp['code'] == 200:
                return resp['songs']  # 返回歌曲列表
            else:
                logging.error(f'Artist top songs API returned error code: {resp["code"]}')
                return None
        except Exception as e:
            logging.error(f'Error retrieving artist top songs: {e}')
            return None
    return None


def get_similar_songs(song_name, artist_name=None, limit=50):
    """获取相似歌曲"""
    # 首先需要搜索歌曲获取歌曲ID
    # 由于网易云API需要歌曲ID，这里先实现一个简单的搜索
    if not song_name:
        return None
    
    # 构建搜索URL
    search_url = build_search_url(song_name, search_type=1, limit=1)  # type=1 表示搜索歌曲
    
    try:
        response = requests.get(url=search_url, headers=headers).json()
        if response['code'] == 200 and 'result' in response:
            song_results = response['result']
            if 'songCount' in song_results and song_results['songCount'] > 0:
                songs = listify(song_results.get('songs', []))
                if songs:
                    song_id = songs[0]['id']
                    
                    # 使用歌曲ID获取相似歌曲
                    url = build_similar_songs_url(song_id, limit=limit)
                    resp = requests.get(url=url, headers=headers).json()
                    if resp['code'] == 200:
                        return resp['songs']  # 返回相似歌曲列表
                    else:
                        logging.error(f'Similar songs API returned error code: {resp["code"]}')
                        return None
    except Exception as e:
        logging.error(f'Error retrieving similar songs: {e}')
    
    return None


def search_song_blur(song_name, limit=1):
    """模糊搜索歌曲"""
    if not song_name:
        return None
    
    url = build_search_url(song_name.lower(), search_type=1, limit=limit)  # type=1 表示搜索歌曲
    songs = []
    try:
        response = requests.get(url=url, headers=headers).json()
        if response['code'] == 200:
            song_results = response['result']
            num = int(song_results.get('songCount', 0))
            lim = min(limit, num)
            for i in range(lim):
                try:
                    songs = listify(song_results.get('songs', []))
                except:
                    logging.error('Error retrieving song search results.')
        else:
            logging.error(f'API returned error code: {response["code"]}')
    except Exception as e:
        logging.error(f'Error retrieving song search results: {e}')
    
    if len(songs) > 0:
        return songs[0]
    return None
