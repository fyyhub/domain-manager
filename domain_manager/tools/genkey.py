"""生成一个 Fernet 加密主密钥。

用法：
    python -m domain_manager.tools.genkey
将输出一个可用于环境变量 DM_ENCRYPTION_KEY 的密钥。
"""
from .. import crypto


def main():
    print(crypto.generate_key())


if __name__ == "__main__":
    main()
