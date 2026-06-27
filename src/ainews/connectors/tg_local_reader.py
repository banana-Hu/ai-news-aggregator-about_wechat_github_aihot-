"""
Telegram Desktop tdata 本地缓存读取器（简化版）。
"""

import os
import struct
import hashlib
import sqlite3
import logging
import tempfile
from pathlib import Path

try:
    from Crypto.Cipher import AES
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

logger = logging.getLogger(__name__)


def _decrypt_tdf(data: bytes, key: bytes) -> bytes | None:
    """解密 TDF 加密数据。"""
    if data[:4] != b"TDF$":
        return None
    _, _, data_len = struct.unpack_from("<4sII", data, 0)
    enc = data[12:12 + data_len]
    cipher = AES.new(key, AES.MODE_CBC, iv=b"\x00" * 16)
    dec = cipher.decrypt(enc)
    pad = dec[-1]
    return dec[:-pad]


def load_tdata_key(tdata_path: str, password: str = "") -> bytes | None:
    """从 key_datas 加载解密密钥。"""
    kd = Path(tdata_path) / "key_datas"
    raw = kd.read_bytes()

    # key_datas 是序列化的 KeyData 列表
    # 格式：[[key_id(8), data]] 外层用 TDF 包裹
    if raw[:4] == b"TDF$":
        # 要解密 key_datas 本身需要一个主密钥
        # TDESKTOP 固定主密钥
        master = hashlib.sha256(b"c00l_waT3r_m3lOn!D0NuT").digest()
        dec = _decrypt_tdf(raw, master)
        if dec:
            raw = dec

    # 解析内部数据
    pos = 0
    count = struct.unpack_from("<I", raw, pos)[0]
    pos += 4

    expected_size = struct.unpack_from("<I", raw, pos)[0]
    pos += 4

    data = raw[pos:pos + expected_size]
    # 数据是 (key_id, encrypted_key) 对
    # 尝试不同的切分方式
    for key_len in [32, 40, 48, 56]:
        if len(data) >= key_len:
            enc_key = data[:key_len]
            # 用空密码派生密钥
            pass_key = hashlib.sha256(
                b"c00l_waT3r_m3lOn!D0NuT" + password.encode()
            ).digest()
            try:
                cipher = AES.new(pass_key, AES.MODE_ECB)
                k = cipher.decrypt(enc_key)
                if k[:4] != b"\x00" * 4:  # 非零即可能正确
                    logger.info(f"密钥获取成功 ({key_len} bytes)")
                    return k[:32]  # AES-256 key
            except Exception:
                continue

    logger.error("所有密钥尝试均失败，可能需要设置本地密码")
    return None


def iter_local_messages(
    tdata_path: str = r"D:\hu\Telegram Desktop\tdata",
    password: str = "",
    limit: int = 50,
) -> list[dict]:
    """从本地 Telegram Desktop 缓存读取消息。"""
    if not HAVE_CRYPTO:
        logger.error("请安装: pip install pycryptodome")
        return []

    key = load_tdata_key(tdata_path, password)
    if not key:
        return []

    # 找到最大的 .s 文件（主数据文件）
    s_files = sorted(Path(tdata_path).glob("*s"), key=lambda p: -p.stat().st_size)
    if not s_files:
        return []

    for sf in s_files[:1]:  # 只处理最大的
        db_data = _decrypt_tdf(sf.read_bytes(), key)
        if not db_data or db_data[:16] != b"SQLite format 3\x00":
            continue

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.write(db_data); tmp.close()

        try:
            conn = sqlite3.connect(tmp.name)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            logger.info(f"表: {[t[0] for t in tables[:10]]}")

            messages = []
            # Telegram Desktop 的关键表
            for tbl, in tables:
                if "message" in tbl.lower():
                    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
                    rows = conn.execute(f"SELECT * FROM {tbl} ORDER BY id DESC LIMIT {limit}").fetchall()
                    for row in rows:
                        messages.append(dict(zip(cols, row)))
            conn.close()
            return messages
        except Exception as e:
            logger.error(f"读取失败: {e}")
        finally:
            os.unlink(tmp.name)

    return []
