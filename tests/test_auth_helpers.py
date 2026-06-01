"""Auth_Service 测试用辅助函数。"""
import os

from domain_manager.auth import AuthService, hash_password
from domain_manager.models import User
from domain_manager.store import DataStore


def make_auth(tmp_dir, username="admin", password="correct horse battery", clock=None):
    """构造一个带预置管理员账户的 AuthService。"""
    store = DataStore(os.path.join(str(tmp_dir), "auth.db"))
    store.initialize()
    store.save_user(User(username=username, password_hash=hash_password(password)))
    svc = AuthService(store, clock=clock)
    svc.load()
    return svc
