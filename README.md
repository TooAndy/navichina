[![Docker Pulls](https://img.shields.io/docker/pulls/tooandy/navichina?logo=docker&label=pulls&style=flat-square)](https://hub.docker.com/r/tooandy/navichina)

## 背景
由于 navidrome 只能使用 Spotify 获取歌曲封面, 通过 Last.fm 获取艺术家信息和专辑信息, 对于中文歌曲来说, 不太友好, 例如: 
- 对于华语歌手来说, Last.fm 中缺失大多数艺术家描述
- 从 Last.fm 中获取的艺术家描述基本上都是英文的
- 从 Spotify 获取的封面信息缺失.
- 由于神秘原因, 访问 Spotify 不稳定.

因此考虑使用使用网易云音乐的接口代替 Last.fm 和 Spotify. 

由于 navidrome 使用 golang 开发, 而我不懂 golang, 因此没有能力直接在 navidrome 上贡献源码. 只能通过这种撇脚的方式, 来解决这个问题.

## 解决思路
1. 修改 navidrome 访问 Spotify 和 Last.fm 的默认地址(具体在 `core/agents/Last.fm/client.go` 和 `core/agents/Spotify/client.go`), 替换为访问本地 `22520` 端口的代理
2. 在 `22520` 端口上, 启动本代理插件, 拦截 navidrome 原本应该向 Spotify 和 Last.fm 发起的请求.
3. 根据拦截的请求信息, 访问网易云的接口, 获取必要的信息, 主要包括艺术家/专辑封面, 描述等 

## 实现效果
1. 不再访问 Spotify, 但仍会访问 Last.fm.
2. 通过网易云音乐对艺术家和专辑的描述, 丰富了 Last.fm 的查询结果.

## 使用方法
### **1. 直接使用已有docker镜像运行(推荐)**
直接使用已经编译完成的 docker 镜像, 并使用如下 docker-compose.yaml, 可直接运行 [navidrome](https://github.com/TooAndy/navidrome) + navichina.
```shell
docker compose -f docker-compose.yaml up -d 
```

docker-compose.yaml 内容如下, 如果需要修改配置, 请参考注释

```yaml
services:
  navidrome:
    container_name: navidrome
    image: tooandy/navidrome:latest
    user: 0:0  # 需要对卷有写入权限
    network_mode: host
    restart: unless-stopped
    environment:
      - ND_CONFIGFILE=/data/navidrome.toml
    volumes:
      - /var/lib/navidrome:/data  # 配置文件放在 /var/lib/navidrome 中, 生成的数据库文件也会放在这里
      - /path/to/your/music:/music 
    depends_on:
      - navichina

  navichina:
    container_name: navichina
    image: tooandy/navichina:latest
    user: 0:0   # 需要对卷有写入权限.
    restart: unless-stopped
    volumes:
      - /path/to/your/music:/music # 如果需要 navidrome 将艺术家和专辑封面下载到音乐路径中, 需要和 navidrome 的卷设置相同.
    ports:
      - 22522:22522   # 外部端口需要设置为 22522, 因为 tooandy/navidrome 容器默认访问 22522 端口. 如果需要修改端口, 建议使用 navichina 项目中的 build-navidrome.sh 脚本重新构建一个镜像
```

### 2. 自己编译打包运行
***确保本地安装了 node, go 和 TagLib***. 具体版本要求见 [Navidrome](https://www.navidrome.org/docs/installation/build-from-source/)
```shell
git clone https://github.com/TooAndy/navichina.git
cd navichina
# 需要 docker 环境. 默认构建为 deluan/navidrome:develop 镜像
sh build-navidrome.sh
# 通过 docker 的方式, 运行本项目的代理软件和部署修改源码重新编译后的 deluan/navidrome:develop 镜像
# 注意修改 navichina.yaml 中的配置
docker compose -f navichina.yaml up -d
```
> 如果需要修改本代理插件的端口, 在 `build-navidrome.sh` 脚本中修改 `PORT` 变量

> 如果需要使用其他方式运行本插件和 navidrome, 可以自己摸索一下, 就这几行代码, 比较简单

## 说明
项目中的大量代码从 [LrcApi](https://github.com/HisAtri/LrcApi) 项目复制过来. 感谢 LrcApi 开源贡献 @HisAtri

## 协议
GPL-3.0 license

## 相关链接
1. [Navidrome 官网](https://www.navidrome.org/)
2. [官方 Navidrome github 仓库](https://github.com/navidrome/navidrome)
2. [tooandy/navidrome/ github 仓库](https://github.com/tooandy/navidrome)
2. [LrcApi](https://github.com/HisAtri/LrcApi)
3. [音流 StreamMusic](https://github.com/gitbobobo/StreamMusic)
