import logging

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

COMMON_SEARCH_URL_WANGYI = 'https://music.163.com/api/search/get/web?csrf_token=hlpretag=&hlposttag=&s={}&type={}&offset={}&total=true&limit={}'
ARTIST_SEARCH_URL = 'http://music.163.com/api/v1/artist/{}'
ALBUMS_SEARCH_URL = "http://music.163.com/api/artist/albums/{}?offset=0&total=true&limit=300"
ALBUM_INFO_URL = "http://music.163.com/api/album/{}?ext=true"


def listify(obj):
    if isinstance(obj, list):
        return obj
    else:
        return [obj]


def search_artist_blur(artist_blur, limit=1):
    """ 由于没有选择交互的过程, 因此 artist_blur 如果输入的不准确, 可能会查询到错误的歌手 """
    # logging.info('开始搜索: ' + artist_blur)
    
    num = 0
    if not artist_blur:
        logging.info('Missing artist. Skipping match')
        return None

    url = COMMON_SEARCH_URL_WANGYI.format(
        urllib.parse.quote(artist_blur.lower()), 100, 0, limit)
    artists = []
    try:
        response = requests.get(url=url, headers=headers).json()
        artist_results = response['result']
        num = int(artist_results['artistCount'])
        lim = min(limit, num)
        # logging.info('搜索到的歌手数量：' + str(lim))
        for i in range(lim):
            try:
                artists = listify(artist_results['artists'])
            except:
                logging.error('Error retrieving artist search results.')
    except:
        logging.error('Error retrieving artist search results.')
    if len(artists) > 0:
        return artists[0]
    return None


def search_artist(artist_id):
    if not artist_id:
        # logging.info('Missing artist. Skipping match')
        return None
    url = ARTIST_SEARCH_URL.format(artist_id)
    try:
        resp = requests.get(url=url, headers=headers).json()
        return resp
    except:
        return None


def search_albums(artist_id):
    url = ALBUMS_SEARCH_URL.format(artist_id)
    resp = requests.get(url=url, headers=headers)
    if resp.status_code == 200 and resp.json()['code'] == 200:
        return resp.json()['hotAlbums']
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
    url = ALBUM_INFO_URL.format(album_id)
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200 and resp.json()['code'] == 200:
        return resp.json()['album']
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
    if blur_result := search_artist_blur(artist_blur=artist):
        if profile := search_artist(blur_result['id']):
            return profile
    return None