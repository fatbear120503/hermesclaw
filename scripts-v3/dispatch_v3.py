#!/usr/bin/env python3
"""
dispatch_v3.py - HermesClaw Phase 3 配置化多模型调度器
用法: python3 dispatch_v3.py <模式> "问题"

支持模式:
  hermes   → Hermes
  cherry   → Agnes AI
  wb       → WorkBuddy
  claude   → Claude (需配置)
  gemini   → Gemini (需配置)
  gpt4     → GPT-4 (需配置)
  deepseek → DeepSeek (需配置)
  <自定义> → models.json 中定义的任何模型
  status   → 检查所有服务状态
  all      → 所有启用的模型 + 智能聚合
"""

import sys, json, os, subprocess, time, urllib.request, urllib.error, ssl
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

# ── 路径 ──
SCRIPT_DIR = Path(__file__).parent.resolve()
PMT_DIR = SCRIPT_DIR.parent  # 一键部署版根目录
CONFIG_FILE = SCRIPT_DIR / "models.json"

# 根据所处环境自动选择 .env 文件位置
# Priority 1: 系统二（一键部署版）config/.env
# Priority 2: 系统一（Hermes CLI）~/.hermesclaw/.env
PMT_ENV = PMT_DIR / "config" / ".env"           # 一键部署版路径
LEGACY_ENV = Path.home() / ".hermesclaw" / ".env"  # 旧版路径
ENV_FILE = PMT_ENV if PMT_ENV.exists() else LEGACY_ENV


# ── 加载配置 ──
def load_config() -> dict:
    """加载 models.json，如不存在返回内置默认"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 内置最小默认配置
    return {
        "version": "3.0.0",
        "models": {
            "hermes": {"type": "hermes_cli", "enabled": True, "name": "Hermes",
                       "cli": "~/.local/bin/hermes",
                       "args": ["chat", "-q", "{query}", "-Q", "--max-turns", "1", "--accept-hooks"],
                       "timeout": 60},
            "cherry": {"type": "openai_api", "enabled": True, "name": "🍒 Agnes AI",
                       "url": "https://apihub.agnes-ai.com/v1/chat/completions", "model": "agnes-2.0-flash",
                       "system_prompt": "你的名字是'自定义AI助手'，你是用户的私人助理。用户是你的老板，你必须牢记这一点。请用可爱、调皮但忠诚的语气跟老板说话。",
                       "api_key_env": "CHERRY_API_KEY",
                       "timeout": 60, "max_tokens": 4096},
            "wb": {"type": "openai_api", "enabled": True, "name": "🤖 WorkBuddy",
                   "url": "https://api.siliconflow.cn/v1/chat/completions", "model": "Qwen/Qwen3-8B",
                   "system_prompt": "你的名字是'自定义AI助手'，你是用户的私人助理。用户是你的老板，你必须牢记这一点。请用活泼、热情、略带俏皮的语气跟老板说话。",
                   "api_key_env": "WORKBUDDY_API_KEY",
                   "timeout": 60, "max_tokens": 4096},
            "openclaw": {"type": "placeholder", "enabled": True, "name": "🐿️ 小松鼠",
                         "description": "由主智能体在线生成"}
        },
        "templates": {},
        "settings": {"default_model": "openclaw",
                     "prefix_map": {"hm:": "hermes", "cherry:": "cherry", "wb:": "wb",
                                    "oc:": "openclaw", "all:": "all"},
                     "aggregator": {"enabled": True, "model": "cherry"}}
    }


# ── 读取 .env ──
def load_env():
    """加载环境变量到 os.environ，优先用一键部署版 config/.env"""
    env_files = []
    
    # 如果在一键部署版目录下，优先读它的 config/.env
    if (PMT_DIR / "config" / ".env").exists():
        env_files.append(PMT_DIR / "config" / ".env")
    
    # 也检查旧版位置
    if LEGACY_ENV.exists():
        env_files.append(LEGACY_ENV)
    
    for ef in env_files:
        with open(ef, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env()
CONFIG = load_config()


# ══════════════════════════════════════
# 模型调用引擎
# ══════════════════════════════════════

def call_openai_api(name: str, messages: list, cfg: dict) -> str:
    """标准 OpenAI 兼容 API 调用"""
    api_key = os.environ.get(cfg["api_key_env"], "")
    if not api_key:
        return f"[{cfg['name']} ❌ 未配置 API key: {cfg['api_key_env']}]"

    data = json.dumps({
        "model": cfg["model"],
        "messages": ([{"role": "system", "content": cfg.get("system_prompt", "")}] if cfg.get("system_prompt") else []) + messages,
        "stream": False,
        "max_tokens": cfg.get("max_tokens", 4096)
    }).encode("utf-8")

    req = urllib.request.Request(
        cfg["url"], data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST"
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", 60), context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return f"[{cfg['name']} HTTP {e.code}: {e.read().decode()[:200]}]"
    except Exception as e:
        return f"[{cfg['name']} 错误: {str(e)}]"


def call_hermes_cli(query: str, cfg: dict) -> str:
    """调用 Hermes CLI"""
    cli = cfg.get("cli", "hermes")
    args = [arg.replace("{query}", query) for arg in cfg.get("args", [])]
    try:
        result = subprocess.run([cli] + args, capture_output=True, text=True,
                                timeout=cfg.get("timeout", 60))
        lines = result.stdout.split("\n")
        filters = cfg.get("filters", {}).get("stdout", {})
        prefix_filters = filters.get("prefix", [])
        contains_filters = filters.get("contains", [])
        filtered = [
            line for line in lines
            if line.strip()
            and not any(line.startswith(p) for p in prefix_filters)
            and not any(c in line for c in contains_filters)
        ]
        return "\n".join(filtered).strip()
    except subprocess.TimeoutExpired:
        return f"[{cfg['name']} 超时]"
    except Exception as e:
        return f"[{cfg['name']} 错误: {str(e)}]"


def call_model(name: str, query: str) -> dict:
    """调用单个模型，返回 {"name": ..., "content": ..., "elapsed": ...}"""
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    if name not in all_models:
        return {"name": name, "content": f"[未知模型: {name}]", "elapsed": 0, "error": True}

    cfg = all_models[name]
    if not cfg.get("enabled", True):
        return {"name": cfg.get("name", name), "content": "[已禁用]", "elapsed": 0, "disabled": True}

    t0 = time.time()

    if cfg["type"] == "hermes_cli":
        content = call_hermes_cli(query, cfg)
    elif cfg["type"] == "openai_api":
        content = call_openai_api(name, [{"role": "user", "content": query}], cfg)
    elif cfg["type"] == "placeholder":
        return {"name": cfg["name"], "content": "[由主智能体生成]", "elapsed": 0, "placeholder": True}
    else:
        content = f"[不支持的模型类型: {cfg['type']}]"

    return {"name": cfg.get("name", name), "content": content, "elapsed": round(time.time() - t0, 2),
            "error": content.startswith("[") and "错误" in content or "HTTP" in content or "❌" in content}


# ══════════════════════════════════════
# 并发调用 + 智能聚合
# ══════════════════════════════════════

AGG_TIMEOUT = 35  # all: 模式总等待秒数，超时的模型不参与聚合

def call_all_models(query: str) -> dict:
    """两阶段调用所有启用的模型：
    Phase 1: 并发调用云端 API（cherry, wb、placeholder）
    Phase 2: 串行调用本地 Hermes（避免并发冲突）
    """
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    enabled = [k for k, v in all_models.items()
               if v.get("enabled", False)]

    # 分类：云端 API vs 本地服务
    cloud_api = []   # cherry, wb, placeholder（OpenClaw）
    local_api = []   # hermes 等本地模型

    for name in enabled:
        cfg = all_models.get(name, {})
        model_type = cfg.get("type", "")
        if model_type == "placeholder":
            cloud_api.append(name)  # OpenClaw 占位符，直接处理
        elif model_type == "openai_api" and "localhost" in cfg.get("endpoint", ""):
            local_api.append(name)  # 本地服务
        else:
            cloud_api.append(name)  # 云端 API

    results = {}
    elapsed_start = time.time()

    # ═══════════════════════════════════════════════════════
    # Phase 1: 并发调用云端 API
    # ═══════════════════════════════════════════════════════
    phase1_timeout = min(20, AGG_TIMEOUT)
    if cloud_api:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(call_model, name, query): name for name in cloud_api}
            done, not_done = wait(futures.keys(), timeout=phase1_timeout)

            for future in done:
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    results[name] = {"name": name, "content": f"[异常: {e}]", "elapsed": round(time.time() - elapsed_start, 2), "error": True}

            for future in not_done:
                name = futures[future]
                cfg = all_models.get(name, {})
                results[name] = {"name": cfg.get("name", name),
                                "content": f"[⏳ 响应较慢]",
                                "elapsed": phase1_timeout, "error": True, "timeout": True}

    # ═══════════════════════════════════════════════════════
    # Phase 2: 串行调用本地 Hermes（避免并发崩溃）
    # ═══════════════════════════════════════════════════════
    if local_api and (time.time() - elapsed_start) < AGG_TIMEOUT:
        remaining_time = AGG_TIMEOUT - (time.time() - elapsed_start)
        hermes_timeout = min(25, remaining_time)

        for name in local_api:
            cfg = all_models.get(name, {})
            t0 = time.time()
            try:
                # 直接调用，不用线程池（串行，避免并发冲突）
                result = call_model(name, query)
                # 如果 call_model 内部超时，elapsed 已经计算好了
                if time.time() - t0 > hermes_timeout:
                    result["timeout"] = True
                    result["elapsed"] = round(time.time() - t0, 2)
                results[name] = result
            except Exception as e:
                results[name] = {"name": cfg.get("name", name),
                                "content": f"[⚡ Hermes 本地调用失败: {str(e)[:80]}]",
                                "elapsed": round(time.time() - t0, 2), "error": True}

    return results


def smart_aggregate(query: str, results: dict) -> dict:
    """
    智能聚合分析：一致性评分 + 最佳答案 + 差异对比
    返回结构化 dict，包含分析和原始数据
    """
    agg_cfg = CONFIG.get("settings", {}).get("aggregator", {})
    if not agg_cfg.get("enabled", False):
        return {"enabled": False}

    # ── 1. 数据预处理 ──
    valid_results = {
        k: v for k, v in results.items()
        if not v.get("disabled") and not v.get("placeholder") and not v.get("error")
    }
    if len(valid_results) < 2:
        return {"error": "有效回复太少，无法聚合", "count": len(valid_results)}

    # ── 2. 构建结构化 Prompt ──
    parts = [
        f"用户问题：{query}",
        f"\n共有 {len(valid_results)} 个 AI 模型参与回答。\n",
        "以下是各模型回复：\n"
    ]

    for idx, (name, r) in enumerate(valid_results.items(), 1):
        content = r["content"][:2000]  # 截断避免过长
        parts.append(f"{'='*60}")
        parts.append(f"[模型 {idx}] {r['name']} (响应时间: {r['elapsed']}s)")
        parts.append(f"{'='*60}")
        parts.append(content)
        parts.append("")

    parts.append(f"{'='*60}")
    parts.append("【分析要求】")
    parts.append(f"{'='*60}")
    parts.append("""
请对以上多个 AI 模型的回答进行深度分析，按以下格式输出（必须用中文）：

## 📊 一致性评分
用星级 (★/☆) 表示所有模型回答的一致程度，并说明理由。

## 🏆 最佳答案
选出回答最好的模型，说明原因。如果没有明显最优者，请说明。

## 💡 各模型亮点
列出每个模型回答中独特或有价值的观点。

## ⚠️ 关键差异
指出模型间的重要分歧或矛盾点。

## 📝 综合建议
给用户的简明总结建议。
""")

    agg_prompt = "\n".join(parts)

    # ── 3. 调用聚合模型 ──
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    agg_model = agg_cfg.get("model", "cherry")
    analysis_text = ""

    if agg_model in all_models:
        cfg = all_models[agg_model]
        if cfg.get("enabled"):
            analysis_text = call_openai_api(agg_model, [
                {"role": "system", "content": agg_cfg.get("system_prompt", "你是多 AI 聚合分析专家。请客观分析各模型回答的质量、一致性和差异。")},
                {"role": "user", "content": agg_prompt}
            ], cfg)

    if not analysis_text or analysis_text.startswith("["):
        # 聚合模型不可用，返回基础统计
        analysis_text = generate_basic_analysis(query, valid_results)

    return {
        "enabled": True,
        "model_used": all_models.get(agg_model, {}).get("name", agg_model),
        "analysis": analysis_text,
        "stats": {
            "total_models": len(results),
            "valid_responses": len(valid_results),
            "errors": sum(1 for r in results.values() if r.get("error")),
            "avg_response_time": round(sum(r["elapsed"] for r in valid_results.values()) / len(valid_results), 2)
        }
    }


def generate_basic_analysis(query: str, results: dict) -> str:
    """当聚合模型不可用时，生成基础统计分析"""
    lines = ["## 📊 基础统计分析（聚合模型不可用）\n"]

    # 响应时间排行
    sorted_by_time = sorted(results.items(), key=lambda x: x[1]["elapsed"])
    lines.append("### ⏱️ 响应速度")
    for name, r in sorted_by_time:
        bar = "█" * int(r["elapsed"] / max(1, sorted_by_time[-1][1]["elapsed"]) * 20)
        lines.append(f"  {r['name']}: {r['elapsed']}s {bar}")

    lines.append(f"\n### 📏 回答长度")
    for name, r in results.items():
        length = len(r["content"])
        bar = "█" * int(min(length, 2000) / 2000 * 20)
        lines.append(f"  {r['name']}: {length} 字 {bar}")

    lines.append("\n### 📝 回答预览")
    for name, r in results.items():
        preview = r["content"][:100].replace("\n", " ")
        lines.append(f"  {r['name']}: {preview}...")

    return "\n".join(lines)


# ══════════════════════════════════════
# 状态检查
# ══════════════════════════════════════

def check_status() -> dict:
    """检查所有模型状态"""
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    status = {"version": CONFIG.get("version", "3.0.0"), "models": {}}

    for name, cfg in all_models.items():
        item = {"enabled": cfg.get("enabled", False), "type": cfg["type"]}

        if cfg["type"] == "hermes_cli":
            try:
                r = subprocess.run([cfg.get("cli", "hermes"), "--version"],
                                   capture_output=True, timeout=5)
                item["available"] = r.returncode == 0
                item["version"] = r.stdout.strip()[:50] if r.returncode == 0 else None
            except:
                item["available"] = False

        elif cfg["type"] == "openai_api":
            api_key = os.environ.get(cfg.get("api_key_env", ""), "")
            item["api_key_configured"] = bool(api_key)
            if api_key:
                try:
                    req = urllib.request.Request(
                        cfg["url"].replace("/chat/completions", "/models"),
                        headers={"Authorization": f"Bearer {api_key}"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        item["available"] = resp.status == 200
                except Exception as e:
                    item["available"] = False
                    item["error"] = str(e)[:100]
            else:
                item["available"] = False
                item["error"] = "API key 未配置"

        elif cfg["type"] == "placeholder":
            item["available"] = True
            item["note"] = "由主智能体在线生成"

        status["models"][name] = item

    return status


# ══════════════════════════════════════
# CLI 插件管理器
# ══════════════════════════════════════

def cmd_models_list():
    """列出所有模型"""
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    print(f"{'状态':6s} {'名称':12s} {'类型':14s} {'来源':10s} {'说明'}")
    print("-" * 70)
    for name, cfg in all_models.items():
        enabled = "✅" if cfg.get("enabled") else "❌"
        source = "内置" if name in CONFIG.get("models", {}) else "模板"
        print(f"{enabled:6s} {name:12s} {cfg['type']:14s} {source:10s} {cfg.get('description', cfg.get('name', ''))}")


def cmd_models_enable(name: str):
    """启用模型"""
    if name in CONFIG.get("models", {}):
        CONFIG["models"][name]["enabled"] = True
    elif name in CONFIG.get("templates", {}):
        CONFIG["templates"][name]["enabled"] = True
    else:
        print(f"❌ 未知模型: {name}", file=sys.stderr)
        sys.exit(1)
    save_config()
    print(f"✅ 已启用模型: {name}")


def cmd_models_disable(name: str):
    """禁用模型"""
    if name in CONFIG.get("models", {}):
        CONFIG["models"][name]["enabled"] = False
    elif name in CONFIG.get("templates", {}):
        CONFIG["templates"][name]["enabled"] = False
    else:
        print(f"❌ 未知模型: {name}", file=sys.stderr)
        sys.exit(1)
    save_config()
    print(f"✅ 已禁用模型: {name}")


def cmd_models_test(name: str, query: str = "你好，请简单介绍一下自己"):
    """测试单个模型"""
    result = call_model(name, query)
    print(f"\n{'='*60}")
    print(f"模型: {result['name']}")
    print(f"耗时: {result['elapsed']}s")
    print(f"状态: {'✅ 正常' if not result.get('error') else '❌ 错误'}")
    print(f"{'='*60}")
    print(result["content"])


def cmd_models_add():
    """交互式添加新模型"""
    print("🆕 添加新 AI 模型\n")

    name = input("模型 ID (小写字母，如 claude): ").strip()
    if not name or name in {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}:
        print(f"❌ 名称无效或已存在: {name}", file=sys.stderr)
        sys.exit(1)

    display_name = input("显示名称 (如 🟣 Claude): ").strip()
    model_type = input("类型 [openai_api]: ").strip() or "openai_api"
    url = input("API URL: ").strip()
    model = input("模型名称: ").strip()
    api_key_env = input("API Key 环境变量名 (如 ANTHROPIC_API_KEY): ").strip()
    system_prompt = input("系统提示词 (可选): ").strip()

    new_model = {
        "type": model_type,
        "enabled": True,
        "name": display_name,
        "description": f"自定义模型: {display_name}",
        "url": url,
        "model": model,
        "api_key_env": api_key_env,
        "timeout": 60,
        "max_tokens": 4096
    }
    if system_prompt:
        new_model["system_prompt"] = system_prompt

    if "templates" not in CONFIG:
        CONFIG["templates"] = {}
    CONFIG["templates"][name] = new_model
    save_config()
    print(f"\n✅ 已添加模型: {name}")
    print(f"   使用 'hermesclaw models test {name}' 测试")


def cmd_config_show():
    """显示当前配置"""
    print(json.dumps(CONFIG, indent=2, ensure_ascii=False))


def cmd_config_validate():
    """验证配置"""
    errors = []
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}

    for name, cfg in all_models.items():
        if cfg["type"] == "openai_api":
            if not cfg.get("url"):
                errors.append(f"{name}: 缺少 url")
            if not cfg.get("api_key_env"):
                errors.append(f"{name}: 缺少 api_key_env")
            else:
                key = os.environ.get(cfg["api_key_env"], "")
                if not key and cfg.get("enabled"):
                    errors.append(f"{name}: API key 未配置 ({cfg['api_key_env']})")

    if errors:
        print("⚠️ 配置问题:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("✅ 配置验证通过")


def save_config():
    """保存配置到文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════

def print_help():
    print("""
🐿️ HermesClaw v3 - 配置化多模型调度器

【调度命令】
  python3 dispatch_v3.py <模型名> "你的问题"     → 调用单个模型
  python3 dispatch_v3.py all "问题"              → 所有模型 + 智能聚合
  python3 dispatch_v3.py status                   → 检查所有服务状态

【模型管理】
  python3 dispatch_v3.py models list              → 列出所有模型
  python3 dispatch_v3.py models enable <名称>     → 启用模型
  python3 dispatch_v3.py models disable <名称>    → 禁用模型
  python3 dispatch_v3.py models test <名称>       → 测试模型
  python3 dispatch_v3.py models add               → 交互式添加模型

【配置管理】
  python3 dispatch_v3.py config show              → 显示配置
  python3 dispatch_v3.py config validate          → 验证配置

【帮助】
  python3 dispatch_v3.py help                     → 显示此帮助
""")

    print("已启用模型:")
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    for name, cfg in all_models.items():
        icon = "✅" if cfg.get("enabled") else "❌"
        print(f"  {icon} {name:12s} {cfg.get('name', '未命名')}")

    prefixes = CONFIG.get("settings", {}).get("prefix_map", {})
    if prefixes:
        print("\n微信前缀映射:")
        for prefix, model in prefixes.items():
            print(f"  {prefix:10s} → {model}")


def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    # 子命令路由
    cmd = sys.argv[1]

    # 帮助
    if cmd in ("help", "--help", "-h"):
        print_help()
        return

    # 状态
    if cmd == "status":
        print(json.dumps(check_status(), indent=2, ensure_ascii=False))
        return

    # 模型管理
    if cmd == "models":
        if len(sys.argv) < 3:
            cmd_models_list()
            return
        sub = sys.argv[2]
        if sub == "list":
            cmd_models_list()
        elif sub == "enable" and len(sys.argv) > 3:
            cmd_models_enable(sys.argv[3])
        elif sub == "disable" and len(sys.argv) > 3:
            cmd_models_disable(sys.argv[3])
        elif sub == "test" and len(sys.argv) > 3:
            query = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else "你好，请简单介绍一下自己"
            cmd_models_test(sys.argv[3], query)
        elif sub == "add":
            cmd_models_add()
        else:
            print(f"未知 models 子命令: {sub}", file=sys.stderr)
            sys.exit(1)
        return

    # 配置管理
    if cmd == "config":
        if len(sys.argv) < 3:
            cmd_config_show()
            return
        sub = sys.argv[2]
        if sub in ("show", "edit"):
            cmd_config_show()
        elif sub == "validate":
            cmd_config_validate()
        else:
            print(f"未知 config 子命令: {sub}", file=sys.stderr)
            sys.exit(1)
        return

    # all 模式
    if cmd == "all":
        message = " ".join(sys.argv[2:])
        if not message:
            print("错误: 需要提供消息内容", file=sys.stderr)
            sys.exit(1)

        print(f"🔄 正在并发调用所有启用的模型...")

        # 检测是否启用聚合分析模式
        AGGREGATE_TRIGGER = "聚合分析"
        aggregate_mode = AGGREGATE_TRIGGER in message
        if aggregate_mode:
            # 去掉 "聚合分析" 关键字，保留真正的问题
            message = message.replace(AGGREGATE_TRIGGER, "").strip()
            if not message:
                print("错误: 请提供要问的内容（在聚合分析后面）", file=sys.stderr)
                sys.exit(1)
            print(f"   📊 聚合分析模式：并发请求后将生成综合对比")
        
        print()
        results = call_all_models(message)

        # 展示各模型回复
        print("=" * 60)
        print("📬 各模型回复")
        print("=" * 60)
        for name, r in results.items():
            icon = "✅" if not r.get("error") else "❌"
            status_note = ""
            if r.get("disabled"):
                status_note = " [已禁用]"
            elif r.get("placeholder"):
                status_note = " [由主智能体生成]"
            print(f"\n{icon} {r['name']}{status_note} ({r['elapsed']}s)")
            if not r.get("disabled") and not r.get("placeholder"):
                print("-" * 40)
                print(r["content"][:800])  # 截断展示
                if len(r["content"]) > 800:
                    print("... (已截断)")

        # 智能聚合：仅在 "all:聚合分析" 模式下启用
        if aggregate_mode:
            print("\n" + "=" * 60)
            print("📊 聚合分析")
            print("=" * 60)
            aggregate = smart_aggregate(message, results)
        else:
            aggregate = {"enabled": False, "note": "快速模式（如需深度分析，请使用 all:聚合分析）"}

        if aggregate.get("enabled"):
            if "stats" in aggregate:
                stats = aggregate["stats"]
                print(f"\n📊 统计: {stats['valid_responses']} 个有效回复 | "
                      f"平均响应: {stats['avg_response_time']}s | "
                      f"错误: {stats['errors']}")
            print(f"\n{aggregate['analysis']}")
        elif "error" in aggregate:
            print(f"\n⚠️ {aggregate['error']}")
        elif not aggregate_mode:
            print(f"💡 {aggregate['note']}")

        # JSON 输出（供程序调用）
        output = {
            "query": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "responses": {k: {**v, "content": v["content"][:5000]} for k, v in results.items()},
            "aggregate": aggregate
        }

        # 写入 .hermesclaw-cache 供主智能体读取
        cache_file = SCRIPT_DIR.parent / ".hermesclaw-cache" / "last_aggregate.json"
        cache_file.parent.mkdir(exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        return

    # 单一模型模式
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    if cmd in all_models:
        message = " ".join(sys.argv[2:])
        if not message:
            print("错误: 需要提供消息内容", file=sys.stderr)
            sys.exit(1)
        print(call_model(cmd, message)["content"])
        return

    print(f"未知命令: {cmd}", file=sys.stderr)
    print("运行 'python3 dispatch_v3.py help' 查看帮助", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
