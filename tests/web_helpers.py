"""Web 层测试辅助：构建测试用 Flask app 与已登录客户端。"""
import os
from datetime import datetime

from domain_manager import crypto
from domain_manager.web.app import create_app

TEST_ADMIN = "admin"
TEST_PASSWORD = "test-pass-123"


def make_app(tmp_dir, clock=None):
    """构建一个使用临时数据库与固定密钥的测试 app。"""
    os.environ["DM_ADMIN_USER"] = TEST_ADMIN
    os.environ["DM_ADMIN_PASSWORD"] = TEST_PASSWORD
    key = crypto.generate_key()
    db_path = os.path.join(str(tmp_dir), "web.db")
    app = create_app(
        db_path=db_path,
        encryption_key=key,
        clock=clock or datetime.now,
        secret_key="test-secret",
    )
    app.config["TESTING"] = True
    return app


def login(client):
    """以默认管理员登录，返回响应。"""
    return client.post(
        "/login",
        data={"username": TEST_ADMIN, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
