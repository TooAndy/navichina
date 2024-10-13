import logging
import sys

from waitress import serve
from args import GlobalArgs
from proxy import app

args = GlobalArgs()

def run_server(debug=False):
    if not debug:
        # Waitress WSGI 服务器
        serve(app, host=args.ip, port=args.port, threads=32, channel_timeout=30)
    else:
        app.run(host='*', port=args.port, debug=True)


if __name__ == '__main__':
    # 对Python版本进行检查（要求Python 3.10+）
    if sys.version_info < (3, 10):
        raise RuntimeError(
            "Python 3.10+ required, but you are using Python {}.{}.{}.".format(*sys.version_info[:3])
        )
    # 日志配置
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('')
    logger.info("正在启动服务器")
    # 启动
    run_server(args.debug)
