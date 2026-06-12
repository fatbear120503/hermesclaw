#!/usr/bin/env python3
"""
HermesClaw v1.0 - 新一代多模型调度器
特性：
  • 调用所有配置的智能体（无缺失）
  • 流式快显：先到的先显示
  • 聚合分析仅在 "all:聚合分析" 时触发
  • 两阶段调用：云端 API 并发 + 本地服务串行
  • 极限响应时间优化

用法: python3 dispatch.py <agent_id:> "问题"
     python3 dispatch.py all "问题"
     python3 dispatch.py all "聚合分析 问题"
"""

import sys, json, os, time, subprocess, threading, queue as queue_mod
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
AGENTS_FILE = PROJECT_DIR / "config" / "agents.json"
ENV_FILE = PROJECT_DIR / "config" / ".env"

# ═══════════════════════════════════════════════════════
# 极速加载配置
# ═══════════════════════════════════════════════════════

def load_env():
    """极速加载环境变量"""
    if not ENV_FILE.exists(): return {}
    env = {}
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v.strip('"').strip("'")
    return env

def load_agents():
    """加载智能体配置"""
    if AGENTS_FILE.exists():
        with open(AGENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 空配置回退
    return {"version": "1.0.0", "agents": {}, "settings": {"prefix_map": {"all:": "all"}, "timeouts": {"cloud": 18, "local": 15, "aggregate": 40}}}

ENV = load_env()
AGENTS = load_agents()

# ═══════════════════════════════════════════════════════
# 极速 API 调用
# ═══════════════════════════════════════════════════════

def call_openai_api(name, messages, cfg) -> str:
    """调用 OpenAI-Compatible API"""
    url = cfg.get("url", "")
    model = cfg.get("model", "")
    # 优先从 agents.json 的 env_key 读取，其次 .env
    api_key = cfg.get("api_key", "")
    if not api_key and "api_key_env" in cfg:
        api_key = ENV.get(cfg["api_key_env"], "")
    sys_prompt = cfg.get("system_prompt", "You are a helpful assistant.")
    max_tok = cfg.get("max_tokens", 2048)

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": sys_prompt}] + messages,
        "max_tokens": max_tok,
        "stream": False
    }

    import json as json_mod
    data = json_mod.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key and not api_key.startswith("your"):
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urlopen(req, timeout=cfg.get("timeout", 18), context=ctx) as resp:
            body = json_mod.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except HTTPError as e:
        body = e.read().decode()
        err_msg = f"HTTP {e.code}"
        try:
            ej = json_mod.loads(body)
            err_msg += f": {ej.get('error', {}).get('message', body[:200])}"
        except:
            err_msg += f": {body[:200]}"
        return f"[{name} 错误: {err_msg}]"
    except Exception as e:
        return f"[{name} 错误: {str(e)[:120]}]"


def call_model(name: str, query: str) -> dict:
    """调用单个模型，返回 {name, content, elapsed, error, placeholder}"""
    t0 = time.time()
    cfg = AGENTS.get("agents", {}).get(name, {})

    if cfg.get("disabled") or not cfg.get("enabled", True):
        return {"name": cfg.get("name", name), "content": "[已禁用]", "elapsed": 0, "disabled": True}

    if cfg.get("type") == "placeholder":
        return {"name": cfg.get("name", name), "content": "[由主智能体在线生成]", "elapsed": 0, "placeholder": True}

    messages = [{"role": "user", "content": query}]
    content = call_openai_api(cfg.get("name", name), messages, cfg)
    elapsed = round(time.time() - t0, 2)
    return {"name": cfg.get("name", name), "content": content, "elapsed": elapsed,
            "error": content.startswith("[") and "错误" in content}


# ═══════════════════════════════════════════════════════
# 两阶段调用引擎
# ═══════════════════════════════════════════════════════

def call_all_models(query: str, result_queue: queue_mod.Queue) -> dict:
    """
    两阶段调用 + 流式快显
    Phase 1: 并发调用云端 API
    Phase 2: 串行调用本地服务
    每个完成的模型立即放入 result_queue
    """
    agents_all = AGENTS.get("agents", {})
    enabled = {k: v for k, v in agents_all.items() if v.get("enabled", False)}

    if not enabled:
        return {}

    # 分类
    cloud_agents = []   # 云端 API
    local_agents = []   # 本地服务 (localhost/127.0.0.1)
    placeholder_agents = []  # 占位符

    for aid, cfg in enabled.items():
        if cfg.get("type") == "placeholder":
            placeholder_agents.append(aid)
        elif cfg.get("type") == "openai_api":
            url = cfg.get("url", "")
            if "localhost" in url or "127.0.0.1" in url:
                local_agents.append(aid)
            else:
                cloud_agents.append(aid)
        else:
            cloud_agents.append(aid)

    results = {}
    start_time = time.time()
    timeouts = AGENTS.get("settings", {}).get("timeouts", {"cloud": 18, "local": 15, "aggregate": 40})

    # ── Phase 1: 云端 API 并发调用 ──
    def cloud_worker(aid):
        r = call_model(aid, query)
        results[aid] = r
        result_queue.put((aid, r))

    if cloud_agents:
        with ThreadPoolExecutor(max_workers=min(len(cloud_agents), 6)) as pool:
            pool.map(cloud_worker, cloud_agents)

    # ── Phase 2: 本地服务串行调用 ──
    # 等云端大部分完成后再串行调本地，避免资源冲突
    remaining = max(0, timeouts.get("local", 15) - (time.time() - start_time))
    for aid in local_agents:
        if time.time() - start_time > timeouts.get("aggregate", 40):
            r = {"name": agents_all.get(aid, {}).get("name", aid),
                 "content": "[⏳ 响应较慢]", "elapsed": round(time.time() - start_time, 2),
                 "error": True, "timeout": True}
            results[aid] = r
            result_queue.put((aid, r))
            continue
        # 串行调用
        r = call_model(aid, query)
        results[aid] = r
        result_queue.put((aid, r))

    # ── 占位符直接放入 ──
    for aid in placeholder_agents:
        r = call_model(aid, query)
        results[aid] = r
        result_queue.put((aid, r))

    result_queue.put(None)  # 结束标记
    return results


# ═══════════════════════════════════════════════════════
# 智能聚合分析
# ═══════════════════════════════════════════════════════

def smart_aggregate(query: str, results: dict) -> str:
    """用 cherry（或最快响应的模型）做聚合分析"""
    valid = {k: v for k, v in results.items()
             if not v.get("error") and not v.get("disabled") and not v.get("placeholder")
             and len(v.get("content", "")) > 20}

    if len(valid) < 2:
        return "⚠️ 有效回复太少，无法聚合"

    # 构建聚合 prompt - 精简版
    agg_prompt = f"""你是多 AI 聚合分析专家。用户问题：{query}

对比以下 AI 的回复，给出：
1. 一致性评分（1-5星）
2. 最佳答案（说明原因）
3. 各自亮点
4. 关键差异
5. 综合建议（50字内）

"""
    for k, v in valid.items():
        content = v["content"][:600]  # 缩短至600字
        agg_prompt += f"[{v['name']}]: {content}\n\n"

    # 直接用 cherry 做聚合，但缩短参数
    cherry_cfg = AGENTS.get("agents", {}).get("cherry", {})
    cherry_cfg_copy = dict(cherry_cfg) if cherry_cfg else {}
    cherry_cfg_copy["system_prompt"] = "你是多 AI 聚合分析专家。请对比各 AI 回复，给出简洁的评分、最佳答案、差异对比和综合建议。"
    cherry_cfg_copy["max_tokens"] = 800  # 减少输出长度
    cherry_cfg_copy["timeout"] = 25  # 聚合分析单独超时

    messages = [{"role": "user", "content": agg_prompt}]
    analysis = call_openai_api("聚合分析器", messages, cherry_cfg_copy)

    return analysis


# ═══════════════════════════════════════════════════════
# 显示引擎 - 流式快显
# ═══════════════════════════════════════════════════════

def display_streaming(results_queue: queue_mod.Queue, results: dict, total: int):
    """
    流式显示：先到的先展示
    已完成的显示 ✅，等待中的显示 ⏳
    """
    displayed = set()
    finished = False

    print()
    while not finished:
        try:
            item = results_queue.get(timeout=0.5)
            if item is None:
                finished = True
                continue
            aid, r = item
            displayed.add(aid)

            icon = "✅" if not r.get("error") else "❌"
            status = ""
            if r.get("disabled"):
                status = " [已禁用]"
            elif r.get("placeholder"):
                status = " [由主智能体生成]"
            elif r.get("timeout"):
                status = " [超时]"

            print(f"\n{icon} {r['name']}{status} ({r['elapsed']}s)")
            print("-" * 40)
            if not r.get("disabled") and not r.get("placeholder"):
                print(r["content"][:1200])
                if len(r["content"]) > 1200:
                    print("... (更多内容请查看详细日志)")

            # 显示进度
            remaining = total - len(displayed)
            if remaining > 0 and not finished:
                print(f"\n⏳ 等待 {remaining} 个智能体...")

        except queue_mod.Empty:
            # 检查是否还有未完成的
            remaining = total - len(displayed)
            if remaining > 0:
                waiting = [k for k in results if k not in displayed]
                # 不打印等待提示，避免刷屏
                pass
            if finished:
                break

    # 最终汇总
    if len(displayed) < total:
        missing = [AGENTS["agents"][k]["name"] for k in results if k not in displayed]
        if missing:
            print(f"\n❌ 未响应: {', '.join(missing)}")


# ═══════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("help", "-h", "--help"):
        print("""🐿️  HermesClaw v1.0 调度器

用法:
  python3 dispatch.py <agent_id>: "问题"     → 调用单个智能体
  python3 dispatch.py all "问题"             → 调用所有启用的智能体（流式快显）
  python3 dispatch.py all "聚合分析 问题"     → 深度聚合分析
  python3 dispatch.py status                 → 检查所有服务状态
  python3 dispatch.py list                   → 列出所有已配置的智能体
""")
        return

    if args[0] == "status":
        print("🤖 已配置的智能体：")
        for aid, cfg in AGENTS.get("agents", {}).items():
            status = "✅" if cfg.get("enabled") else "❌"
            key_ok = ""
            if "api_key_env" in cfg:
                key_ok = " 🔑" if ENV.get(cfg["api_key_env"], "").startswith("sk-") else " ⚠️"
            print(f"  {status} [{aid}] {cfg['name']} ({cfg.get('type')}){key_ok}")
        return

    if args[0] == "list":
        for aid, cfg in AGENTS.get("agents", {}).items():
            trigger = f"{aid}:"
            print(f"  {trigger} → {cfg['name']}")
        return

    # all 模式
    if args[0] == "all":
        query = " ".join(args[1:])
        if not query:
            print("❌ 错误: 请提供消息内容", file=sys.stderr)
            sys.exit(1)

        # 检测聚合分析模式
        AGGREGATE_TRIGGER = "聚合分析"
        aggregate_mode = AGGREGATE_TRIGGER in query
        if aggregate_mode:
            query = query.replace(AGGREGATE_TRIGGER, "").strip()
            if not query:
                print("❌ 错误: 请提供要问的内容（在聚合分析后面）", file=sys.stderr)
                sys.exit(1)

        agents_all = {k: v for k, v in AGENTS.get("agents", {}).items() if v.get("enabled", False)}
        if not agents_all:
            print("❌ 没有启用的智能体。请运行: python3 scripts/setup.py install", file=sys.stderr)
            sys.exit(1)

        print(f"🔄 正在调用 {len(agents_all)} 个智能体...")
        if aggregate_mode:
            print(f"   📊 聚合分析模式：等待所有响应后生成综合对比")
        else:
            print(f"   ⚡ 快速模式：先到的先显示")
        print()

        results_queue = queue_mod.Queue()
        call_thread = threading.Thread(target=call_all_models, args=(query, results_queue))
        call_thread.start()

        print("=" * 60)
        print("📬 各模型回复")
        print("=" * 60)

        # 收集全部结果用于聚合
        all_results = {}
        displayed = set()

        while True:
            try:
                item = results_queue.get(timeout=0.3)
                if item is None:
                    break
                aid, r = item
                all_results[aid] = r

                icon = "✅" if not r.get("error") else "❌"
                status = ""
                if r.get("disabled"):
                    status = " [已禁用]"
                elif r.get("placeholder"):
                    status = " [由主智能体生成]"
                elif r.get("timeout"):
                    status = " [超时]"

                print(f"\n{icon} {r['name']}{status} ({r['elapsed']}s)")
                if not r.get("disabled") and not r.get("placeholder"):
                    print("-" * 40)
                    content = r["content"]
                    print(content[:1200])
                    if len(content) > 1200:
                        print("... (已截断)")
                displayed.add(aid)

            except queue_mod.Empty:
                if not call_thread.is_alive():
                    break

        call_thread.join(timeout=2)

        # 聚合分析
        if aggregate_mode:
            print("\n" + "=" * 60)
            print("📊 聚合分析")
            print("=" * 60)
            print()
            analysis = smart_aggregate(query, all_results)
            print(analysis)
        elif not aggregate_mode:
            print(f"\n💡 快速模式完成（如需深度分析，请使用 all:聚合分析）")

        # JSON 缓存
        output = {
            "query": query,
            "aggregate_mode": aggregate_mode,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "responses": {k: {**v, "content": v["content"][:3000]} for k, v in all_results.items()},
        }
        cache_dir = SCRIPT_DIR.parent / ".hermesclaw-cache"
        cache_dir.mkdir(exist_ok=True)
        with open(cache_dir / "last_aggregate.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        return

    # 单一智能体模式
    prefix_map = AGENTS.get("settings", {}).get("prefix_map", {})
    agent_id = prefix_map.get(args[0], args[0].rstrip(":"))

    agents_cfg = AGENTS.get("agents", {})
    if agent_id not in agents_cfg:
        print(f"❌ 未知智能体: {agent_id}", file=sys.stderr)
        print(f"已配置: {', '.join(agents_cfg.keys())}", file=sys.stderr)
        sys.exit(1)

    query = " ".join(args[1:])
    if not query:
        print("❌ 请提供消息内容", file=sys.stderr)
        sys.exit(1)

    print(call_model(agent_id, query)["content"])


if __name__ == "__main__":
    main()
