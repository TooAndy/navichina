import argparse
import json
import logging
import os

logger = logging.getLogger(__name__)

# 启动参数解析器
parser = argparse.ArgumentParser(description="navidrome 网易云代理插件")
# 添加一个 `--port` 参数，默认值 22522
parser.add_argument('--port', type=int, default=22522, help='应用的运行端口，默认 22522')
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
kw_args, unknown_args = parser.parse_known_args()


# 按照次序筛选首个非Bool False（包括None, '', 0, []等）值；
# False, None, '', 0, []等值都会转化为None
def first(*args):
    """
    返回第一个非False值
    :param args:
    :return:
    """
    result = next(filter(lambda x: x, args), None)
    return result


class DefaultConfig:
    def __init__(self):
        self.ip = '*'
        self.port = 22522


class ConfigFile:
    """
    读取json配置文件
    """

    def __init__(self):
        json_config = {
            "server": {
                "ip": "*",
                "port": 22522
            }
        }
        file_path = os.path.join(os.getcwd(), "config", "config.json")
        try:
            with open(file_path, "r+") as json_file:
                json_config = json.load(json_file)
        except FileNotFoundError:
            # 如果文件不存在，则创建文件并写入初始配置
            directory = os.path.dirname(file_path)
            if not os.path.exists(directory):
                os.makedirs(directory)
            with open(file_path, "w+") as json_file:
                json.dump(json_config, json_file, indent=4)
        self.server = json_config.get("server", {})
        self.port = self.server.get("port", 0)
        self.ip = self.server.get("ip", "*")


# 环境变量定义值
class EnvVar:
    def __init__(self):
        self.port = os.environ.get('API_PORT', None)


env_args = EnvVar()
config_args = ConfigFile()
default = DefaultConfig()


# 按照优先级筛选出有效值
class GlobalArgs:
    def __init__(self):
        self.port = first(env_args.port, kw_args.port, config_args.port, default.port)
        self.ip = first(config_args.ip, default.ip)
        self.debug = kw_args.debug
        self.version = "1.0.0"
