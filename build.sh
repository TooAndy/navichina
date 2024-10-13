### 此文件用于构建本地Docker镜像
docker build -t tooandy/navichina:1.0.0 .

docker compose -f navichina.yaml up -d
# docker logs -f navichina