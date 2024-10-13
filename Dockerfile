# 第一阶段：安装GCC
FROM python:3.11-alpine as gcc_installer

# 安装GCC及其他依赖
# RUN apk update --repository=https://mirrors.aliyun.com/alpine/v3.20/main \
#     --repository=https://mirrors.aliyun.com/alpine/v3.20/community && \
#     apk add --no-cache gcc musl-dev jpeg-dev zlib-dev libjpeg-turbo-dev

RUN echo "https://mirrors.aliyun.com/alpine/v3.20/main" > /etc/apk/repositories && \
    echo "https://mirrors.aliyun.com/alpine/v3.20/community" >> /etc/apk/repositories && \
    apk update && \
    apk add --no-cache gcc musl-dev jpeg-dev zlib-dev libjpeg-turbo-dev


# 第二阶段：安装Python依赖
FROM gcc_installer as requirements_installer

# 设置工作目录
WORKDIR /app

# 只复制 requirements.txt，充分利用 Docker 缓存层
COPY ./requirements.txt /app/

# 安装Python依赖
RUN pip install --no-user --prefix=/install -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# 第三阶段：运行环境
FROM python:3.11-alpine

# 设置工作目录
WORKDIR /app

# 复制Python依赖
COPY --from=requirements_installer /install /usr/local

# 复制项目代码
COPY ./ /app

# 设置启动命令
CMD ["python", "/app/app.py"]
