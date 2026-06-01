"""pytest 与 Hypothesis 的全局测试配置。

注册一个 Hypothesis profile，保证每个属性测试至少运行 100 个随机用例
（符合 design.md 中 Testing Strategy 的约定：max_examples >= 100）。
"""
import os

# 在导入 domain_manager.auth 之前降低 PBKDF2 迭代次数，使口令哈希相关的
# 属性测试（大量随机用例）能在合理时间内完成。生产环境不设置此变量，
# 沿用 Werkzeug 默认的高强度迭代。安全属性（加盐/不可逆/可校验）与迭代次数无关。
os.environ.setdefault("DM_PBKDF2_ITERATIONS", "1000")

from hypothesis import settings, HealthCheck  # noqa: E402

# 全局 profile：每条属性测试至少 100 个用例。
settings.register_profile(
    "domain_manager",
    max_examples=100,
    deadline=None,  # 关闭单用例超时，避免 CI/慢机器误报
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("domain_manager")
