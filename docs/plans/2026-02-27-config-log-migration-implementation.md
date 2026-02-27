# Config 和 Log 存放位置迁移实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 将 expert-auditor-pro 插件的 config 和 log 从插件目录迁移到 `~/.claude/plugin/expert-auditor-pro/`

**Architecture:** 集中管理路径常量到 paths.py，实现安全的文件权限控制和迁移逻辑

**Tech Stack:** Python, pathlib, os

---

### Task 1: 创建 paths.py 集中管理路径

**Files:**
- Create: `expert-auditor-pro/scripts/paths.py`

**Step 1: 创建 paths.py 文件**

```python
"""路径常量集中管理"""
import os
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
    """获取配置路径"""
    # 检查是否已迁移
    if (BASE_DIR / ".migrated").exists():
        return CONFIG_FILE

    # 首次运行：检查旧路径
    if OLD_CONFIG_FILE.exists():
        return OLD_CONFIG_FILE
    return CONFIG_FILE


def safe_write_config(content: str):
    """原子写配置文件，防止竞态条件"""
    ensure_dirs()
    # 原子操作：创建文件时直接指定权限
    fd = os.open(str(CONFIG_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)


def cleanup_old_files():
    """清理旧路径的残留文件，保留备份"""
    if OLD_CONFIG_FILE.exists():
        backup_path = OLD_CONFIG_FILE.with_suffix('.json.bak')
        OLD_CONFIG_FILE.rename(backup_path)
    if OLD_LOG_DIR.exists():
        import shutil
        backup_log = OLD_LOG_DIR.parent / f"{OLD_LOG_DIR.name}.bak"
        shutil.move(str(OLD_LOG_DIR), str(backup_log))
```

**Step 2: 验证文件创建**

Run: `ls -la expert-auditor-pro/scripts/paths.py`
Expected: 文件存在

**Step 3: Commit**

```bash
git add expert-auditor-pro/scripts/paths.py
git commit -m "feat: add paths.py for centralized path management"
```

---

### Task 2: 修改 main.py 引用 paths.py

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:33-39`

**Step 1: 删除旧路径定义 (行 33-36)**

删除:
```python
# 配置路径
PLUGIN_DIR = Path(__file__).parent.parent
CONFIG_FILE = PLUGIN_DIR / "config.json"
LOG_DIR = Path.home() / ".cache" / "expert-auditor-pro" / "logs"

# 确保日志目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)
```

**Step 2: 添加新导入**

在 import 区域后添加:
```python
from paths import get_config_path, LOG_DIR, ensure_dirs, CONFIG_FILE

# 启动时确保目录存在
ensure_dirs()
```

**Step 3: 修改 load_config 函数使用 get_config_path**

找到 `load_config` 函数，将:
```python
def load_config() -> dict:
    if not CONFIG_FILE.exists():
```
改为:
```python
def load_config() -> dict:
    config_path = get_config_path()
    if not config_path.exists():
```

**Step 4: 测试运行**

Run: `cd expert-auditor-pro && uv run scripts/main.py --help`
Expected: 正常输出帮助信息，无报错

**Step 5: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "refactor: migrate to paths.py for config/log locations"
```

---

### Task 3: 修改 config_manager.py 引用 paths.py

**Files:**
- Modify: `expert-auditor-pro/scripts/config_manager.py:10`

**Step 1: 删除旧路径定义 (行 10)**

删除:
```python
CONFIG_FILE = Path(__file__).parent.parent / "config.json"
```

**Step 2: 添加新导入**

在 import 区域后添加:
```python
from paths import CONFIG_FILE, ensure_dirs, safe_write_config
```

**Step 3: 修改 save_config 使用 safe_write_config**

找到 `save_config` 函数，将:
```python
def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
```
改为:
```python
def save_config(config: dict) -> None:
    content = json.dumps(config, indent=4, ensure_ascii=False)
    safe_write_config(content)
```

**Step 4: 测试配置写入**

Run: `cd expert-auditor-pro && uv run scripts/config_manager.py --set-qwen-key "test-key-123"`
Expected: 输出 "Qwen API Key 已保存"，检查 `~/.claude/plugin/expert-auditor-pro/config.json` 是否创建

**Step 5: 验证权限**

Run: `ls -la ~/.claude/plugin/expert-auditor-pro/config.json`
Expected: `-rw-------` (0600 权限)

**Step 6: Commit**

```bash
git add expert-auditor-pro/scripts/config_manager.py
git commit -m "refactor: migrate config_manager to use paths.py"
```

---

### Task 4: 更新 CLAUDE.md 文档

**Files:**
- Modify: `CLAUDE.md:60-70`

**Step 1: 更新配置路径说明**

将:
```markdown
### 配置文件位置

- API Keys: `expert-auditor-pro/config.json`
- 日志: `~/.cache/expert-auditor-pro/logs/`
```

改为:
```markdown
### 配置文件位置

- API Keys: `~/.claude/plugin/expert-auditor-pro/config.json`
- 日志: `~/.claude/plugin/expert-auditor-pro/logs/`
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update config path in CLAUDE.md"
```

---

### Task 5: 清理 .gitignore

**Files:**
- Modify: `expert-auditor-pro/.gitignore`

**Step 1: 删除旧规则**

删除以下行:
```
config.json
logs/
```

**Step 2: Commit**

```bash
git add expert-auditor-pro/.gitignore
git commit -m "chore: remove config/log from gitignore (now in ~/.claude/plugin/)"
```

---

### Task 6: 清理旧配置文件

**Step 1: 检查旧文件是否存在**

Run: `ls -la expert-auditor-pro/config.json 2>/dev/null && echo "EXISTS" || echo "NOT EXISTS"`
Expected: NOT EXISTS 或文件已不存在

**Step 2: 如果存在，手动删除**

```bash
rm expert-auditor-pro/config.json
git add expert-auditor-pro/config.json
git commit -m "chore: remove old config.json from plugin directory"
```

---

### Task 7: 集成测试

**Step 1: 运行完整审计测试**

Run: `cd expert-auditor-pro && echo '{"plan": "test plan", "cwd": "/tmp"}' | uv run scripts/main.py`
Expected: 能正常读取配置并运行

**Step 2: 验证日志写入新路径**

Run: `ls -la ~/.claude/plugin/expert-auditor-pro/logs/`
Expected: info.jsonl 和 debug.jsonl 存在

**Step 3: Commit**

```bash
git status
git add -A
git commit -m "feat: complete config/log migration to ~/.claude/plugin/"
```
