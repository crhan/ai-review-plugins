# Config 和 Log 存放位置迁移设计

## 背景

当前 `expert-auditor-pro` 插件的配置文件和日志存放位置不够规范：
- config 放在插件目录内 (`expert-auditor-pro/config.json`)
- log 放在 `~/.cache/expert-auditor-pro/logs/`)

这导致：
1. 插件目录包含用户数据，不适合版本控制（需 gitignore）
2. 与 Claude Code 其他插件的数据存放位置不一致

## 目标

将配置和日志统一迁移到 `~/.claude/plugin/expert-auditor-pro/` 目录下。

## 方案

### 目录结构

```
~/.claude/plugin/expert-auditor-pro/
├── config.json    # API Keys 配置 (mode 0600)
└── logs/         # 日志目录 (mode 0700)
    ├── info.jsonl
    ├── debug.jsonl
    └── error.jsonl
```

### 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `expert-auditor-pro/scripts/paths.py` | **新建** - 集中管理路径常量 |
| `expert-auditor-pro/scripts/main.py` | 引用 paths.py 的常量 |
| `expert-auditor-pro/scripts/config_manager.py` | 引用 paths.py 的常量 |
| `CLAUDE.md` | 更新配置路径文档 |
| `.gitignore` | 移除 `config.json` 和 `logs/` 规则 |

### 实现细节

#### 1. paths.py - 集中管理路径

```python
"""路径常量集中管理"""
from pathlib import Path

PLUGIN_NAME = "expert-auditor-pro"
BASE_DIR = Path.home() / ".claude" / "plugin" / PLUGIN_NAME
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "logs"

# 兼容：旧路径 fallback
OLD_CONFIG_FILE = Path(__file__).parent.parent / "config.json"
OLD_LOG_DIR = Path.home() / ".cache" / PLUGIN_NAME / "logs"

def ensure_dirs():
    """确保目录存在且权限正确"""
    BASE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

def get_config_path():
    """获取配置路径：新路径优先，不存在则检查旧路径"""
    if CONFIG_FILE.exists():
        return CONFIG_FILE
    if OLD_CONFIG_FILE.exists():
        return OLD_CONFIG_FILE
    return CONFIG_FILE  # 默认返回新路径
```

#### 2. main.py 修改

```python
# 旧
from pathlib import Path
CONFIG_FILE = PLUGIN_DIR / "config.json"
LOG_DIR = Path.home() / ".cache" / "expert-auditor-pro" / "logs"

# 新
from paths import get_config_path, LOG_DIR, ensure_dirs, CONFIG_FILE

# 启动时确保目录存在
ensure_dirs()
config_path = get_config_path()  # 用于读取配置
```

#### 3. config_manager.py 修改

```python
# 旧
from pathlib import Path
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

# 新
from paths import CONFIG_FILE, ensure_dirs
```

#### 4. 权限控制

- 目录: `mode=0o700` (仅所有者读写执行)
- config.json: `mode=0o600` (仅所有者读写)

**防止竞态条件**：使用 `os.open` 原子性创建文件并设置权限：

```python
import os

def safe_write_config(content: str):
    ensure_dirs()
    # 原子操作：创建文件时直接指定权限
    fd = os.open(str(CONFIG_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
```

**显式 chmod 忽略 umask**：

```python
def ensure_dirs():
    """确保目录存在且权限正确"""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # 显式 chmod 忽略 umask 影响
    os.chmod(BASE_DIR, 0o700)
    os.chmod(LOG_DIR, 0o700)
```

#### 5. 旧文件清理

迁移成功后，重命名旧配置文件为 .bak 备份（不是直接删除）：

```python
def cleanup_old_files():
    """清理旧路径的残留文件，保留备份"""
    if OLD_CONFIG_FILE.exists():
        backup_path = OLD_CONFIG_FILE.with_suffix('.json.bak')
        OLD_CONFIG_FILE.rename(backup_path)  # 重命名为 .bak
    if OLD_LOG_DIR.exists():
        import shutil
        # 备份旧日志目录
        backup_log = OLD_LOG_DIR.parent / f"{OLD_LOG_DIR.name}.bak"
        shutil.move(str(OLD_LOG_DIR), str(backup_log))
```

#### 6. 错误处理

`ensure_dirs` 失败时直接报错，不静默 fallback：

```python
def ensure_dirs():
    """确保目录存在且权限正确"""
    try:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # 显式 chmod 忽略 umask 影响
        os.chmod(BASE_DIR, 0o700)
        os.chmod(LOG_DIR, 0o700)
    except PermissionError as e:
        raise RuntimeError(f"无法创建目录 {BASE_DIR}: {e}")
```

#### 7. 迁移状态标记

创建 `.migrated` 标记文件，记录迁移状态：

```python
def get_config_path():
    """获取配置路径"""
    # 检查是否已迁移
    if (BASE_DIR / ".migrated").exists():
        return CONFIG_FILE

    # 首次运行：检查旧路径
    if OLD_CONFIG_FILE.exists():
        return OLD_CONFIG_FILE
    return CONFIG_FILE
```

#### 8. TODO 标记

在 paths.py 中标记旧路径兼容逻辑的清理计划：

```python
# TODO: Remove legacy support after v1.3.0
# 旧路径兼容逻辑，仅用于平滑迁移
OLD_CONFIG_FILE = Path(__file__).parent.parent / "config.json"
```

#### 5. .gitignore 修改

移除以下行：
```
config.json
logs/
```

## 风险

1. **现有配置丢失** - 用户需要重新配置 API Keys（接受，因为用户选择了直接切换）
2. **文档不一致** - 确保所有文档都更新

## 实施步骤

1. 创建 `scripts/paths.py` - 集中管理路径常量，包含 fallback 逻辑和清理函数
2. 修改 `main.py` - 引用 paths.py，添加目录创建和权限设置
3. 修改 `config_manager.py` - 引用 paths.py，使用 safe_write_config
4. 更新 `CLAUDE.md` 文档
5. 清理 `.gitignore`
6. 手动删除旧配置文件 `expert-auditor-pro/config.json`
7. 测试运行确认路径正确
