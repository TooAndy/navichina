### 此文件用于构建本地Docker镜像
docker build -t navichina:latest .

docker compose -f navichina.yaml up -d
# docker logs -f navichina