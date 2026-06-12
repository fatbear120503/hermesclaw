#!/usr/bin/env python3
"""
HermesClaw 配置向导
完整版 - 支持模型选择、路由设置
"""

import json
import os
import sys
from pathlib import Path

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.HEADER}{text.center(60)}{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}\n")

def print_step(step, total, text):
    print(f"{Colors.CYAN}[{step}/{total}] {text}{Colors.END}")

def input_default(prompt, default):
    result = input(f"{prompt} [{default}]: ").strip()
    return result if result else default

def yes_no(prompt, default=True):
    default_str = "Y/n" if default else "y/N"
    result = input(f"{prompt} [{default_str}]: ").strip().lower()
    if not result:
        return default
    return result in ['y', 'yes']

def main():
    print_header("🦀 HermesClaw 配置向导")
    print("欢迎使用 HermesClaw 完整配置向导！")
    print("此向导将帮助您配置多 Agent 路由系统。\n")
    
    config = {
        "router": {},
        "agents": {},
        "prefixes": {},
        "plugin": {}
    }
    
    # Step 1: Router 配置
    print_step(1, 5, "Router 基础配置")
    config["router"]["host"] = input_default("Router 监听地址", "0.0.0.0")
    config["router"]["port"] = int(input_default("Router 端口", "18889"))
    config["router"]["log_level"] = input_default("日志级别 (debug/info/warning/error)", "info")
    
    # Step 2: Agent 配置
    print_step(2, 5, "Agent 配置")
    
    print(f"\n{Colors.BLUE}配置可用的 AI Agent:{Colors.END}")
    
    # Hermes Agent
    print(f"\n{Colors.BOLD}Hermes Agent (本地 AI){Colors.END}")
    if yes_no("启用 Hermes Agent?", True):
        config["agents"]["hm"] = {
            "name": "Hermes Agent",
            "endpoint": input_default("  端点地址", "http://localhost:9119"),
            "description": "本地 AI agent (SenseNova 6.7 Flash-Lite)",
            "enabled": True,
            "model": input_default("  模型名称", "SenseNova 6.7 Flash-Lite")
        }
        config["prefixes"]["hm:"] = "hm"
    
    # GPT Agent
    print(f"\n{Colors.BOLD}GPT Agent (云端 AI){Colors.END}")
    if yes_no("启用 GPT Agent?", False):
        config["agents"]["gpt"] = {
            "name": "GPT Agent",
            "endpoint": input_default("  端点地址", "http://localhost:18890"),
            "description": "Cloud-based GPT agent",
            "enabled": True,
            "model": input_default("  模型名称", "gpt-4")
        }
        config["prefixes"]["gpt:"] = "gpt"
    
    # Step 3: 聚合组配置
    print_step(3, 5, "聚合回复配置")
    print(f"\n{Colors.BLUE}聚合回复 = 同时问多个 Agent，合并所有回答{Colors.END}")
    
    config["aggregate_groups"] = {}
    
    # both: 聚合组
    print(f"\n{Colors.BOLD}both: 前缀聚合{Colors.END}")
    print("  输入 both: 问题时，同时发给哪些 Agent？")
    
    both_agents = []
    if "hm" in config["agents"] and config["agents"]["hm"]["enabled"]:
        if yes_no("  包含 Hermes Agent?", True):
            both_agents.append("hm")
    if yes_no("  包含 OpenClaw (小松鼠)?", True):
        both_agents.append("openclaw")
    
    if both_agents:
        config["aggregate_groups"]["both"] = both_agents
        config["prefixes"]["both:"] = "both"
        print(f"  ✅ both: → {', '.join(both_agents)}")
    
    # all: 聚合组（如果启用了 GPT）
    if "gpt" in config["agents"] and config["agents"]["gpt"]["enabled"]:
        print(f"\n{Colors.BOLD}all: 前缀聚合{Colors.END}")
        print("  输入 all: 问题时，同时发给哪些 Agent？")
        
        all_agents = []
        if "hm" in config["agents"] and config["agents"]["hm"]["enabled"]:
            if yes_no("  包含 Hermes Agent?", True):
                all_agents.append("hm")
        if yes_no("  包含 OpenClaw (小松鼠)?", True):
            all_agents.append("openclaw")
        if yes_no("  包含 GPT Agent?", True):
            all_agents.append("gpt")
        
        if all_agents:
            config["aggregate_groups"]["all"] = all_agents
            config["prefixes"]["all:"] = "all"
            print(f"  ✅ all: → {', '.join(all_agents)}")
    
    # Step 4: OpenClaw 配置
    print_step(4, 5, "OpenClaw 集成配置")
    config["openclaw"] = {
        "gateway": input_default("OpenClaw Gateway 地址", "http://localhost:18789"),
        "auto_route": yes_no("无前缀消息自动路由到 OpenClaw?", True)
    }
    config["prefixes"]["oc:"] = "oc"
    
    # Step 5: Plugin 配置
    print_step(5, 5, "Plugin 配置")
    config["plugin"] = {
        "port": int(input_default("Plugin 端口", "3001")),
        "max_retries": int(input_default("最大重试次数", "3")),
        "retry_delay": int(input_default("重试间隔 (ms)", "1000"))
    }
    
    # 保存配置
    print_header("配置确认")
    
    print(f"{Colors.BLUE}Router:{Colors.END}")
    print(f"  地址: {config['router']['host']}:{config['router']['port']}")
    print(f"  日志: {config['router']['log_level']}")
    
    print(f"\n{Colors.BLUE}Agents:{Colors.END}")
    for key, agent in config['agents'].items():
        status = f"{Colors.GREEN}启用{Colors.END}" if agent['enabled'] else f"{Colors.WARNING}禁用{Colors.END}"
        print(f"  [{key}] {agent['name']} - {status}")
        print(f"    端点: {agent['endpoint']}")
        if 'model' in agent:
            print(f"    模型: {agent['model']}")
    
    print(f"\n{Colors.BLUE}前缀映射:{Colors.END}")
    for prefix, agent in config['prefixes'].items():
        print(f"  {prefix} → {agent}")
    
    if "aggregate_groups" in config and config["aggregate_groups"]:
        print(f"\n{Colors.BLUE}聚合组:{Colors.END}")
        for group, agents in config["aggregate_groups"].items():
            print(f"  {group}: → {', '.join(agents)}")
    
    print(f"\n{Colors.BLUE}OpenClaw:{Colors.END}")
    print(f"  Gateway: {config['openclaw']['gateway']}")
    print(f"  自动路由: {'是' if config['openclaw']['auto_route'] else '否'}")
    
    # 保存文件
    if yes_no("\n保存配置?", True):
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        
        config_file = config_dir / "wizard.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 同时生成 .env 文件
        env_file = config_dir / ".env"
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(f"# Router Configuration\n")
            f.write(f"APP_NAME=HermesClaw Router\n")
            f.write(f"VERSION=0.1.0\n")
            f.write(f"PORT={config['router']['port']}\n")
            f.write(f"HOST={config['router']['host']}\n")
            f.write(f"\n")
            f.write(f"# Agent Endpoints\n")
            for key, agent in config['agents'].items():
                if agent['enabled']:
                    f.write(f"HERMESCLAW_AGENT_{key.upper()}={agent['endpoint']}\n")
            f.write(f"\n")
            # Aggregate groups
            if "aggregate_groups" in config and config["aggregate_groups"]:
                f.write(f"# Aggregate Groups (prefix -> comma-separated agent keys)\n")
                for group, agents in config["aggregate_groups"].items():
                    f.write(f"HERMESCLAW_AGGREGATE_{group.upper()}={','.join(agents)}\n")
                f.write(f"\n")
            f.write(f"# OpenClaw Gateway\n")
            f.write(f"HERMESCLAW_OPENCLAW_GATEWAY={config['openclaw']['gateway']}\n")
            f.write(f"\n")
            f.write(f"# Timeouts\n")
            f.write(f"HERMESCLAW_REQUEST_TIMEOUT=30\n")
            f.write(f"HERMESCLAW_MAX_RETRIES={config['plugin']['max_retries']}\n")
            f.write(f"\n")
            f.write(f"# Logging\n")
            f.write(f"HERMESCLAW_LOG_LEVEL={config['router']['log_level'].upper()}\n")
        
        print(f"\n{Colors.GREEN}✅ 配置已保存!{Colors.END}")
        print(f"   JSON 配置: {config_file}")
        print(f"   环境变量: {env_file}")
        
        # 生成启动脚本
        start_script = Path("start.sh")
        with open(start_script, 'w') as f:
            f.write("#!/bin/bash\n\n")
            f.write("echo '🦀 启动 HermesClaw...'\n\n")
            f.write("# 启动 Router\n")
            f.write("echo '📡 启动 Router...'\n")
            f.write("cd router\n")
            f.write("source venv/bin/activate\n")
            f.write("python run.py &\n")
            f.write("ROUTER_PID=$!\n")
            f.write("cd ..\n\n")
            f.write("# 启动 Plugin\n")
            f.write("echo '🔌 启动 Plugin...'\n")
            f.write("cd plugin\n")
            f.write("npm start &\n")
            f.write("PLUGIN_PID=$!\n")
            f.write("cd ..\n\n")
            f.write("echo ''\n")
            f.write("echo '✅ HermesClaw 已启动'\n")
            f.write(f"echo '   Router: http://{config['router']['host']}:{config['router']['port']}'\n")
            f.write(f"echo '   Plugin: http://localhost:{config['plugin']['port']}'\n")
            f.write("echo ''\n")
            f.write("echo '按 Ctrl+C 停止'\n\n")
            f.write("trap 'kill $ROUTER_PID $PLUGIN_PID; exit' INT\n")
            f.write("wait\n")
        
        start_script.chmod(0o755)
        print(f"   启动脚本: {start_script}")
        
        print(f"\n{Colors.CYAN}使用方式:{Colors.END}")
        print("   1. 安装依赖: ./install.sh")
        print("   2. 启动服务: ./start.sh")
        print("   3. 运行测试: ./test.sh")
    else:
        print(f"\n{Colors.WARNING}配置未保存{Colors.END}")
    
    print(f"\n{Colors.GREEN}🎉 配置向导完成!{Colors.END}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}配置已取消{Colors.END}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.FAIL}错误: {e}{Colors.END}")
        sys.exit(1)
