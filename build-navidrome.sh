# 确保本地安装了 node, go 和 TagLib. 
# 具体版本要求可以参考: https://www.navidrome.org/docs/installation/build-from-source/

# 代理暴露的端口号
PORT=22522

# git clone https://github.com/navidrome/navidrome.git
# 使用国内镜像加速
echo "从 github 拉取最新 navidrome 代码"
git clone https://ghp.ci/https://github.com/navidrome/navidrome.git
cd navidrome

echo "更改 navidrome 中 lastfm 接口地址到本地的 $PORT 端口"
sed -i 's|apiBaseUrl = "https://ws.audioscrobbler.com/2.0/"|apiBaseUrl = "http://127.0.0.1:'${PORT}'/lastfm/"|' core/agents/lastfm/client.go

echo "更改 navidrome 中 spotify 接口地址到本地的 $PORT 端口"
find . -type f \( -name "*.go" -o -name "*.json" \) -exec sed -i 's|https://api.spotify.com/v1/|http://127.0.0.1:'${PORT}'/spotify/|g' {} +
echo "跳过 spotify 验证, 注意, 仍然需要在配置文件或环境变量中配置 Spotify.ID 和 Spotify.Secret, 但值可以随意填写."

sed -i '/token, err := c.authorize(ctx)/i \    token := ""' core/agents/spotify/client.go
sed -i '/token, err := c.authorize(ctx)/{N;N;N;d;}' core/agents/spotify/client.go
sed -i 's/err = c\.makeRequest(req, \&results)/err := c.makeRequest(req, \&results)/' core/agents/spotify/client.go
sed -i '0,/Expect(err).To(MatchError("spotify error(invalid_client): Invalid client"))/s//Expect(err).To(BeNil())/' client_test.go

# ln -s /var/lib/navidrome/navidrome.toml .
echo "10 秒后开始构建"
sleep 10

make setup
make build
# 可以用 make server 进行快速测试
# make server

# 打包为 docker 镜像. 默认为 deluan/navidrome:develop
make docker-image
