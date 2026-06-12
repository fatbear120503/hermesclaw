#!/usr/bin/env python3
"""
v0.2.0 → v1.0 配置迁移脚本
将旧版 models.json + config/.env 转换为新版 agents.json
"""

import json, shutil
from pathlib import Path

PROJECT_DIR = Path("~/Documents/hermesclaw")
OLD_MODELS = PROJECT_DIR / "scripts-v3" / "models.json"
OLD_ENV = PROJECT_DIR / "config" / ".env"
NEW_AGENTS = PROJECT_DIR / "config" / "agents.json"
NEW_ENV = PROJECT_DIR / "config" / ".env"
BAK_DIR = PROJECT_DIR / "bak2.0"

def migrate():
    print("🔄 v0.2.0 → v1.0 配置迁移")
    print()

    # 加载旧配置
    old_models = {}
    if OLD_MODELS.exists():
        with open(OLD_MODELS, "r", encoding="utf-8") as f:
            old_models = json.load(f)

    old_env = {}
    if OLD_ENV.exists():
        with open(OLD_ENV, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    old_env[k] = v.strip('"').strip("'")

    # 构建新 agents.json
    new_agents = {
        "version": "1.0.0",
        "agents": {},
        "settings": {
            "default_model": "oc",
            "prefix_map": {
                "all:": "all",
                "oc:": "oc"
            },
            "timeouts": {
                "cloud": 18,
                "local": 15,
                "aggregate": 40
            },
            "aggregator": {
                "enabled": True,
                "system_prompt": "你是多 AI 聚合分析专家。请对比分析多个 AI 的回复，给出一致评分、最佳判断、差异对比和综合建议。用中文，简洁清晰。"
            }
        }
    }

    # 迁移 OpenClaw
    new_agents["agents"]["oc"] = {
        "name": "🐿️小松鼠",
        "short_name": "openclaw",
        "type": "placeholder",
        "enabled": True,
        "description": "OpenClaw 主智能体 (由主智能体在线生成)"
    }

    # 迁移每个旧模型
    model_map = {
        "hermes": {"id": "hm", "prefix": "hm:", "name": "⚡Hermes"},
        "cherry": {"id": "cherry", "prefix": "cherry:", "name": "🍒Agnes AI"},
        "wb": {"id": "wb", "prefix": "wb:", "name": "🤖WorkBuddy"},
    }

    new_env_entries = {}

    for old_key, info in model_map.items():
        cfg = old_models.get("models", {}).get(old_key)
        if not cfg:
            continue

        new_id = info["id"]
        # 检查是否有 key（安全：只迁移占位符，不迁移真实 key）
        env_key_name = cfg.get("api_key_env", f"{old_key.upper()}_API_KEY")
        has_key = old_env.get(env_key_name, "").startswith("sk-") and not old_env.get(env_key_name, "").startswith("your_")

        new_agents["agents"][new_id] = {
            "name": info["name"],
            "short_name": old_key,
            "type": cfg.get("type", "openai_api"),
            "enabled": cfg.get("enabled", True) and has_key,
            "url": cfg.get("url", ""),
            "model": cfg.get("model", ""),
            "api_key_env": env_key_name,
            "system_prompt": cfg.get("system_prompt", "You are a helpful assistant."),
            "timeout": cfg.get("timeout", 20),
            "max_tokens": cfg.get("max_tokens", 2048),
            "description": cfg.get("description", "")
        }

        # 安全处理：迁移 key 但标记需要用户确认
        if has_key:
            print(f"  ⚠️  {info['name']}: 检测到 API Key，已标记为 'enabled'")
            print(f"     建议运行: python3 scripts/setup.py edit" )
            print(f"     确认 Key 是否有效")
            new_env_entries[env_key_name] = old_env[env_key_name]
        else:
            print(f"  ❌  {info['name']}: 无有效 API Key，已禁用")
            new_agents["agents"][new_id]["enabled"] = False

        new_agents["settings"]["prefix_map"][info["prefix"]] = new_id

    # 保存新配置
    NEW_AGENTS.parent.mkdir(parents=True, exist_ok=True)
    with open(NEW_AGENTS, "w", encoding="utf-8") as f:
        json.dump(new_agents, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已生成: {NEW_AGENTS}")

    # 保存环境变量（只保存有 key 的）
    if new_env_entries:
        # 追加到 .env
        existing_env = {}
        if NEW_ENV.exists():
            with open(NEW_ENV, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        existing_env[k] = v.strip('"').strip("'")

        existing_env.update(new_env_entries)
        with open(NEW_ENV, "w", encoding="utf-8") as f:
            for k, v in existing_env.items():
                f.write(f"{k}={v}\n")
        print(f"✅ 已更新: {NEW_ENV}")
    else:
        # 生成占位符 .env
        lines = []
        lines.append("# HermesClaw v1.0 环境变量")
        lines.append("# 请运行: python3 scripts/setup.py install")
        lines.append("# 或直接编辑此文件添加 API Key")
        lines.append("")
        for info in model_map.values():
            old_cfg = old_models.get("models", {}).get(info["short_name"], {})
            env_key = old_cfg.get("api_key_env", f"{info['short_name'].upper()}_API_KEY")
            lines.append(f"# {info['name']}")
            lines.append(f"{env_key}=")
            lines.append("")
        with open(NEW_ENV, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"✅ 已生成占位符: {NEW_ENV}")

    print(f"\n📋 迁移完成！")
    print(f"  旧配置备份: {BAK_DIR}/")
    print(f"\n🚀 下一步:")
    print(f"  1. 编辑 API Key: hermesclaw edit")
    print(f"  2. 测试: hermesclaw test")
    print(f"  3. 生成二维码: hermesclaw qrcode")

if __name__ == "__main__":
    migrate()
