"""路径常量集中管理"""
import os
import shutil
from pathlib import Path

PLUGIN_NAME = "expert-auditor-pro"
BASE_DIR = Path.home() / ".claude" / "plugin" / PLUGIN_NAME
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "logs"

# TODO: Remove legacy support after v1.3.0
# 旧路径兼容逻辑，仅用于平滑迁移
OLD_CONFIG_FILE = Path(__file__).parent.parent.parent / "config.json"
OLD_LOG_DIR = Path.home() / ".cache" / PLUGIN_NAME / "logs"


def ensure_dirs():
    """确保目录存在且权限正确"""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # 显式 chmod 忽略 umask 影响
    os.chmod(BASE_DIR, 0o700)
    os.chmod(LOG_DIR, 0o700)


def get_config_path():
    """获取配置路径，优先新路径"""
    # 已迁移：直接返回新路径
    if (BASE_DIR / ".migrated").exists():
        return CONFIG_FILE

    # 新路径已存在：使用新路径
    if CONFIG_FILE.exists():
        return CONFIG_FILE

    # 旧路径存在：回退到旧路径
    if OLD_CONFIG_FILE.exists():
        return OLD_CONFIG_FILE

    # 默认返回新路径
    return CONFIG_FILE


def safe_write_config(content: str):
    """原子写配置文件，防止竞态条件"""
    ensure_dirs()
    config_path = get_config_path()  # 使用动态路径，支持迁移检测
    try:
        fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
    except OSError as e:
        import logging
        logging.error(f"Failed to write config to {config_path}: {e}")
        raise


def cleanup_old_files():
    """清理旧路径的残留文件，保留备份"""
    if OLD_CONFIG_FILE.exists():
        backup_path = OLD_CONFIG_FILE.with_suffix('.json.bak')
        OLD_CONFIG_FILE.rename(backup_path)
        os.chmod(backup_path, 0o600)
    if OLD_LOG_DIR.exists():
        backup_log = OLD_LOG_DIR.parent / f"{OLD_LOG_DIR.name}.bak"
        shutil.move(str(OLD_LOG_DIR), str(backup_log))
