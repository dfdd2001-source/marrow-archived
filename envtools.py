"""共享环境工具：.env 读取的唯一实现。

此前 platform.py 与 scripts/marrow_onboard.py 各维护一份相同的 load_env，
现统一到这里。用法：
    sys.path.insert(0, <项目根>)
    from envtools import load_env
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_env():
    """当前环境变量与项目根 .env 合并（已存在的环境变量优先）。返回一份拷贝。"""
    env = dict(os.environ)
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env
