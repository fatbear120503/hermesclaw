#!/usr/bin/env python3
"""
HermesClaw v1.0 - 智能体配置管理器
支持：首次安装配置 / 后续增删改智能体 / 微信二维码绑定
"""

import json, os, sys, re, time, subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
CONFIG_FILE = PROJECT_DIR / "config" / "agents.json"
ENV_FILE = PROJECT_DIR / "config" / ".env"

def print_banner(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_success(msg): print(f"✅ {msg}")
def print_info(msg): print(f"ℹ️  {msg}")
def print_warning(msg): print(f"⚠️  {msg}")
def print_step(step, total, msg): print(f"\n🔹 [{step}/{total}] {msg}" if total else f"\n🔹 {msg}")

def input_default(prompt, default=""):
    r = input(f"{prompt} [{default}]: ").strip()
    return r if r else default

def input_secret(prompt):
    import getpass
    return getpass.getpass(f"{prompt}: ").strip()

def yes_no(prompt, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        r = input(f"{prompt} [{d}]: ").strip().lower()
        if not r: return default
        if r in ("y","yes","是"): return True
        if r in ("n","no","否"): return False
        print("请输入 y 或 n")

# ═══════════════════════════════════════════════════════
# 预设模型模板（供参考，用户可自由修改）
# ═══════════════════════════════════════════════════════
MODEL_TEMPLATES = {
    "openai_compatible": {
        "type": "openai_api",
        "description": "OpenAI-compatible API (通用)"
    },
    "anthropic": {
        "type": "openai_api",
        "description": "Anthropic Claude API"
    },
    "local": {
        "type": "openai_api",
        "description": "本地 LLM 服务 (如 Ollama, vLLM)"
    }
}

# ═══════════════════════════════════════════════════════
# 保存/加载配置
# ═══════════════════════════════════════════════════════

def load_agents():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1.0.0", "agents": {}, "settings": {"prefix_map": {"all:": "all"}, "timeouts": {"cloud": 20, "local": 15, "aggregate": 35}}}

def save_agents(data):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_env(entries):
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, v in entries.items():
        lines.append(f"{k}={v}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def load_env_entries():
    if not ENV_FILE.exists(): return {}
    entries = {}
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, v = line.split("=", 1)
                entries[k] = v
    return entries

# ═══════════════════════════════════════════════════════
# 注册智能体
# ═══════════════════════════════════════════════════════

def prompt_add_agent(is_first=False):
    print_banner("添加新智能体" if not is_first else "配置你的第一个智能体")

    agents = load_agents()
    existing = set(agents["agents"].keys())

    # 自动生成短代号
    idx = 1
    while f"ai{idx}" in existing:
        idx += 1
    default_id = f"ai{idx}"

    print("📋 智能体信息（留空使用默认值）：")
    agent_id = input_default("短代号 (小写英文+数字，如: hm, gpt4, deepseek)", default_id).lower()
    if not re.match(r'^[a-z][a-z0-9_]*$', agent_id):
        print_warning("代号格式错误，请使用小写英文开头")
        return False
    if agent_id in existing:
        print_warning(f"代号 {agent_id} 已存在")
        return False

    name = input_default("显示名称 (如: ⚡ Hermes)", f"🤖 Agent-{agent_id}")
    short_name = input_default("英文简称 (如: hermes)", agent_id)

    print("\n📡 API 类型：")
    print("  1) OpenAI-Compatible API (通用)")
    print("  2) 本地服务 (localhost/内网)")
    print("  3) placeholder (由主智能体生成，如 OpenClaw)")
    type_choice = input_default("选择类型", "1")

    agent_type = "openai_api"
    is_local = False
    if type_choice == "2":
        is_local = True
    elif type_choice == "3":
        agent_type = "placeholder"

    description = input_default("描述", "自定义智能体")

    agent = {
        "name": name,
        "short_name": short_name,
        "type": agent_type,
        "enabled": True,
        "description": description
    }

    if agent_type != "placeholder":
        print("\n🔗 API 配置：")
        url = input_default("API URL (如: https://api.openai.com/v1/chat/completions)", "")
        if not url:
            print_warning("URL 不能为空")
            return False
        agent["url"] = url

        model = input_default("模型名称 (如: gpt-4, claude-3-sonnet)", "")
        if model:
            agent["model"] = model

        api_key = input_secret("API Key (必填)")
        if not api_key:
            print_warning("API Key 不能为空")
            return False
        agent["api_key"] = api_key

        system_prompt = input_default("系统提示词 (可选)", "You are a helpful assistant.")
        agent["system_prompt"] = system_prompt

        timeout = int(input_default("超时秒数 (默认20)", "20"))
        agent["timeout"] = timeout
        agent["max_tokens"] = int(input_default("最大生成 token (默认2048)", "2048"))

        # 保存到 agents.json 时去掉 api_key，存到 .env
        env_key = f"{agent_id.upper()}_API_KEY"
        agent["api_key_env"] = env_key
        del agent["api_key"]

    # 保存
    agents["agents"][agent_id] = agent
    agents["settings"]["prefix_map"][f"{agent_id}:"] = agent_id
    save_agents(agents)

    # 保存 api_key 到 .env
    if "api_key_env" in agent:
        env = load_env_entries()
        env_key = agent["api_key_env"]
        # 从原始输入重新获取 key（刚才删了）
        # 实际上需要重新提示... 修复：先保存再处理
        print("\n⚠️ 需要重新输入 API Key 保存到环境变量")
        key_val = input_secret(f"API Key ({env_key})")
        env[env_key] = key_val
        save_env(env)

    print_success(f"智能体 '{name}' ({agent_id}) 已添加！")
    return True


def prompt_edit_agent():
    agents = load_agents()
    if not agents["agents"]:
        print_warning("还没有任何智能体")
        return

    print_banner("编辑智能体")
    ids = list(agents["agents"].keys())
    for i, aid in enumerate(ids, 1):
        a = agents["agents"][aid]
        status = "✅" if a.get("enabled") else "❌"
        print(f"  {i}. {status} {aid} - {a['name']}")

    sel = input_default("选择编号 (0取消)", "0")
    if sel == "0": return
    try:
        aid = ids[int(sel)-1]
    except:
        print_warning("无效选择")
        return

    agent = agents["agents"][aid]
    print(f"\n编辑: {agent['name']} ({aid})")
    print("(留空保持原值)")

    name = input_default("名称", agent.get("name", ""))
    if name: agent["name"] = name

    if agent["type"] != "placeholder":
        url = input_default("URL", agent.get("url", ""))
        if url: agent["url"] = url

        model = input_default("模型", agent.get("model", ""))
        if model: agent["model"] = model

        new_key = input_default("新 API Key (输入 'keep' 保留原值)", "keep")
        if new_key != "keep" and new_key:
            env_key = agent.get("api_key_env", f"{aid.upper()}_API_KEY")
            env = load_env_entries()
            env[env_key] = new_key
            save_env(env)
            print_success("API Key 已更新")

        sp = input_default("系统提示词", agent.get("system_prompt", ""))
        if sp: agent["system_prompt"] = sp

    agent["enabled"] = yes_no("启用此智能体?", agent.get("enabled", True))
    save_agents(agents)
    print_success(f"'{agent['name']}' 已更新")


def prompt_delete_agent():
    agents = load_agents()
    if not agents["agents"]:
        print_warning("没有可删除的智能体")
        return

    print_banner("删除智能体")
    ids = list(agents["agents"].keys())
    for i, aid in enumerate(ids, 1):
        a = agents["agents"][aid]
        print(f"  {i}. {aid} - {a['name']}")

    sel = input_default("选择编号 (0取消)", "0")
    if sel == "0": return
    try:
        aid = ids[int(sel)-1]
    except:
        return

    if yes_no(f"确认删除 '{aid}'?", False):
        del agents["agents"][aid]
        # 清理 prefix_map
        to_remove = [k for k,v in agents["settings"]["prefix_map"].items() if v == aid]
        for k in to_remove:
            del agents["settings"]["prefix_map"][k]
        save_agents(agents)
        print_success(f"'{aid}' 已删除")


def prompt_list_agents():
    agents = load_agents()
    print_banner("🤖 已配置的智能体")
    if not agents["agents"]:
        print_warning("还没有任何智能体")
        return

    env = load_env_entries()
    for aid, a in agents["agents"].items():
        status = "✅ 启用" if a.get("enabled") else "❌ 禁用"
        t = a.get("type", "unknown")
        key_status = ""
        if "api_key_env" in a:
            key_env = a["api_key_env"]
            has_key = "✅" if env.get(key_env, "").startswith("sk-") else "⚠️"
            key_status = f" | Key: {has_key}"
        print(f"\n  {status} [{aid}] {a['name']} ({t}){key_status}")
        if "url" in a:
            print(f"      URL: {a['url']}")
        if "model" in a:
            print(f"      Model: {a['model']}")
        trigger = f"{aid}:"
        print(f"      微信触发: {trigger}")


def generate_wechat_qrcode():
    """生成微信配置二维码"""
    print_banner("微信绑定配置")
    print_info("此功能需要 OpenClaw 微信通道已配置")
    print_info("请确保 openclaw-weixin 已安装并运行")
    print()

    # 检查 openclaw 配置
    oc_config = Path.home() / ".openclaw" / "config.yaml"
    if not oc_config.exists():
        print_warning("OpenClaw 配置未找到，请先安装 OpenClaw")
        return

    print("微信绑定步骤：")
    print("  1. 确保 OpenClaw Gateway 运行: openclaw gateway run")
    print("  2. 扫描二维码登录微信")
    print("  3. 在 config/agents.json 中配置前缀映射")
    print()

    # 生成二维码文本
    agents = load_agents()
    config_text = "HermesClaw 智能体配置:\n"
    for aid, a in agents["agents"].items():
        if a.get("enabled"):
            config_text += f"  {aid}: = {a['name']}\n"

    print(config_text)

    # 尝试生成二维码图片
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(config_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = PROJECT_DIR / "config" / "wechat_qrcode.png"
        img.save(qr_path)
        print_success(f"二维码已保存: {qr_path}")
    except ImportError:
        print_warning("未安装 qrcode 模块，请运行: pip install qrcode[pil]")
        print_info(f"配置文本:\n{config_text}")


def install_wizard():
    """首次安装向导"""
    print_banner("🐿️  HermesClaw v1.0 - 首次安装向导")
    print("欢迎使用 HermesClaw 多智能体调度系统！")
    print("此向导将帮助您配置要调用的 AI 智能体。\n")

    agents = load_agents()

    # 默认添加 OpenClaw（占位符）
    if "oc" not in agents["agents"]:
        agents["agents"]["oc"] = {
            "name": "🐿️ 小松鼠",
            "short_name": "openclaw",
            "type": "placeholder",
            "enabled": True,
            "description": "OpenClaw 主智能体 (由主智能体在线生成)"
        }
        agents["settings"]["prefix_map"]["oc:"] = "oc"
        save_agents(agents)
        print_success("已自动添加 OpenClaw (oc:)")

    print("📋 选项：")
    print("  1. 从预设模板快速添加")
    print("  2. 自定义添加智能体")
    print("  3. 跳过 (稍后手动配置)")

    choice = input_default("选择", "1")

    if choice == "1":
        # 预设模板
        presets = [
            ("hm", "⚡ Hermes", "http://localhost:8642/v1/chat/completions", "sensenova-6.7-flash-lite", "HERMES_API_KEY"),
            ("cherry", "🍒 Agnes AI", "https://apihub.agnes-ai.com/v1/chat/completions", "agnes-2.0-flash", "CHERRY_API_KEY"),
            ("wb", "🤖 WorkBuddy", "https://api.siliconflow.cn/v1/chat/completions", "Qwen/Qwen3-8B", "WORKBUDDY_API_KEY"),
            ("ds", "🔴 DeepSeek", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat", "DEEPSEEK_API_KEY"),
            ("gpt", "🟢 GPT-4", "https://api.openai.com/v1/chat/completions", "gpt-4", "OPENAI_API_KEY"),
        ]

        for aid, name, url, model, env_key in presets:
            if yes_no(f"添加 {name}?", aid in ("cherry", "wb")):
                agents = load_agents()
                key = input_secret(f"  {name} API Key (sk-...)")
                if key:
                    agents["agents"][aid] = {
                        "name": name,
                        "short_name": aid,
                        "type": "openai_api",
                        "enabled": True,
                        "url": url,
                        "model": model,
                        "api_key_env": env_key,
                        "system_prompt": f"你是{name}，洛桑贡秋的私人助理。",
                        "timeout": 20,
                        "max_tokens": 2048
                    }
                    agents["settings"]["prefix_map"][f"{aid}:"] = aid

                    env = load_env_entries()
                    env[env_key] = key
                    save_env(env)
                    print_success(f"  {name} 已添加")
                    save_agents(agents)

    elif choice == "2":
        while yes_no("继续添加智能体?", True):
            prompt_add_agent(is_first=True)

    print_banner("🎉 安装完成！")
    print("已配置的智能体：")
    prompt_list_agents()

    if yes_no("生成微信配置二维码?", True):
        generate_wechat_qrcode()

    print("\n🚀 使用方式：")
    print("  微信: 输入 'oc:问题' 或 'hm:问题' 或 'all:问题'")
    print("  CLI: python3 scripts/dispatch.py all '问题'")


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("install", "setup"):
        install_wizard()
    elif args[0] == "add":
        prompt_add_agent()
    elif args[0] == "edit":
        prompt_edit_agent()
    elif args[0] == "delete":
        prompt_delete_agent()
    elif args[0] == "list":
        prompt_list_agents()
    elif args[0] == "qrcode":
        generate_wechat_qrcode()
    elif args[0] == "help":
        print_banner("HermesClaw 配置管理器")
        print("用法: python3 setup.py <命令>")
        print("  install    - 首次安装向导")
        print("  add        - 添加智能体")
        print("  edit       - 编辑智能体")
        print("  delete     - 删除智能体")
        print("  list       - 列出所有智能体")
        print("  qrcode     - 生成微信配置二维码")
    else:
        print(f"未知命令: {args[0]}")
        print("运行: python3 setup.py help")

if __name__ == "__main__":
    main()
