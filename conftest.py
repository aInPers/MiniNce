"""根级 conftest.py - 在任何 minince 模块导入前设置测试环境变量。

必须放在项目根目录，pytest 会优先加载此文件。
"""
import os

# 标记为测试环境，使 config.py 自动注入测试密钥
os.environ.setdefault("ENVIRONMENT", "testing")
