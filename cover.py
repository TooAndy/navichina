import logging
import os
import re
import threading

import requests

from search import get_album_info, get_artist_profile

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('')

music_dir = "/music"

ALBUM_REGEX_PATTERN = os.getenv('ALBUM_REGEX_PATTERN', "(.*)")
# ALBUM_REGEX_PATTERN = os.getenv('ALBUM_REGEX_PATTERN', "\d+--(.+)")

COVER_AUTO_DOWNLOAD = os.getenv("COVER_AUTO_DOWNLOAD", "false")
COVER_AUTO_DOWNLOAD = True if COVER_AUTO_DOWNLOAD.lower() == "true" else False

def find_album_directory(artist_dir, album_name):
    """
    在 artist_dir 目录下查找包含 album_name 的专辑目录
    """
    for dir_name in os.listdir(artist_dir):
        if album_name in dir_name:
            return os.path.join(artist_dir, dir_name)
    return None


def download_image_async(image_url, artist_name, album_name=None):
    if not COVER_AUTO_DOWNLOAD:
        return
    download_task = threading.Thread(target=download_image, args=(image_url, artist_name, album_name))
    download_task.start()



def download_image(image_url, artist_name, album_name=None):
    
    # 创建艺术家文件夹路径
    artist_dir = os.path.join(music_dir, artist_name)
    
    # 确保艺术家文件夹存在
    if not os.path.exists(artist_dir):
        logger.warning(f"不存在艺术家 {artist_name}, 无法保存封面图片")
        return
    # 如果是专辑封面，尝试找到匹配的专辑文件夹
    if album_name:
        album_dir = find_album_directory(artist_dir, album_name)
        if not album_dir:
            logger.warning(f"不存在专辑 {artist_name}/{album_name}, 无法保存封面图片")
            return
        
        image_path = os.path.join(album_dir, 'cover.jpg') 
    else:
        image_path = os.path.join(artist_dir, 'artist.jpg') 

    if os.path.exists(image_path):
        return
    
    do_download(image_url, image_path)
    



def do_download(image_url, image_path):
    try:
        response = requests.get(image_url)
        response.raise_for_status()

        # 将图片保存到指定路径
        with open(image_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"下载封面 {image_path}")
    except Exception as e:
        logger.error(f"下载封面失败: {e}")
    pass


def get_artist_pic_url(artist):
    if profile := get_artist_profile(artist):
        return profile['artist']['img1v1Url']
    return None


def get_album_pic_url(artist, album):
    if info := get_album_info(artist, album):
        return info['picUrl']
    return None


def download_covers_auto():
    if not COVER_AUTO_DOWNLOAD:
        logger.info("未开启自动下载专辑和艺术家封面")
        return
    for artist in os.listdir(music_dir):
        artist_dir = os.path.join(music_dir, artist)
        if os.path.isdir(artist_dir):
            artist_cover_path = os.path.join(artist_dir, "artist.jpg")
            # logger.info(artist_dir)
            if not os.path.exists(artist_cover_path):
                if url := get_artist_pic_url(artist):
                    do_download(url, artist_cover_path)

            for album in os.listdir(artist_dir):
                album_dir = os.path.join(artist_dir, album)
                # logger.info(album_dir)
                if os.path.isdir(album_dir):
                    cover_path = os.path.join(album_dir, "cover.jpg")
                    if not os.path.exists(cover_path):
                        real_album_name = album
                        if match := re.search(ALBUM_REGEX_PATTERN, album):
                            real_album_name = match.group(1)
                        
                        if url := get_album_pic_url(artist, real_album_name):
                            do_download(url, cover_path)
                        else:
                            logger.warning(f"找不到封面, 无法下载 {cover_path}")
    logger.info("done download_covers_auto")
                