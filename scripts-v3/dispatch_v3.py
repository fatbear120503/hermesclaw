"""
HermesClaw v3 - 调度引擎 v3.2
纯串行版：串行调用 4 个智能体，避免任何并发阻塞
"""
import json, os, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent

# ── 加载环境变量 ──

def load_env(env_path: Path):
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"\''))

load_env(BASE_DIR / "config" / ".env")
load_env(Path.home() / ".hermes" / ".env")

CONFIG = json.load(open(SCRIPT_DIR / "models.json"))

# ── 核心 API 调用 ──

def call_api(url: str, api_key: str, model: str, query: str,
             system: str = None, temperature=0.7, max_tokens=512,
             timeout=15, top_p=None) -> str:
    """调用 OpenAI Compatible API，返回文本或错误标记"""
    import urllib.request, urllib.error, ssl, certifi

    ctx = ssl.create_default_context()
    ctx.load_verify_locations(certifi.where())

    msgs = [{"role": "user", "content": query}]
    if system:
        msgs.insert(0, {"role": "system", "content": system})
        if "sensenova" in model.lower() or "localhost" in url:
            msgs = [{"role": "user",
                    "content": f"[@设定]\n{system}\n\n[@用户问题]\n{query}"}]

    payload = {
        "model": model, "messages": msgs,
        "temperature": temperature, "stream": False,
        "max_tokens": max_tokens
    }
    if top_p is not None:
        payload["top_p"] = top_p

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"]
            return str(result)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        return f"[@HTTP错误 {e.code}] {body[:200]}"
    except Exception as e:
        return f"[@调用失败] {type(e).__name__}: {e}"


# ── 单模型调用包装 ──

def call_single(name: str, query: str) -> dict:
    """调用单个模型，返回结构化结果"""
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    cfg = all_models.get(name)
    if not cfg:
        return {"name": name, "content": "[@未配置]", "elapsed": 0, "error": True}

    url = cfg.get("url", "")
    api_key = os.environ.get(cfg.get("api_key", ""), "")

    if not url:
        return {"name": cfg.get("name", name), "content": "[@URL未配置]",
                "elapsed": 0, "error": True}
    if not api_key:
        return {"name": cfg.get("name", name), "content": "[@API Key未配置]",
                "elapsed": 0, "error": True}

    start = time.time()
    content = call_api(
        url, api_key,
        cfg.get("model", ""), query,
        system=cfg.get("system"),
        temperature=cfg.get("temperature", 0.7),
        max_tokens=cfg.get("max_tokens", 512),
        timeout=cfg.get("timeout", 15),
        top_p=cfg.get("top_p")
    )
    elapsed = round(time.time() - start, 2)

    error = content.startswith("[@")
    return {"name": cfg.get("name", name), "content": content,
            "elapsed": elapsed, "error": error}


# ── 串行调用所有模型（核心） ──

def call_all_serial(query: str) -> dict:
    """串行串行串行调用所有启用的模型，依次：hermes -> cherry -> wb -> openclaw"""
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}
    # 按固定顺序：本地先（快），然后 cloud
    order = ["hermes", "cherry", "wb", "openclaw"]
    enabled = [(n, all_models[n]) for n in order
               if n in all_models and all_models[n].get("enabled", False)]

    results = {}
    print(f"\n{'='*50}", file=sys.stderr)
    print(f"[@调度开始] 串行调用 {len(enabled)} 个模型", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)

    for name, cfg in enabled:
        desc = cfg.get("description", name)
        print(f"[{time.strftime('%H:%M:%S')}] ▶️ 呼叫 {desc}...", flush=True, file=sys.stderr)

        result = call_single(name, query)
        results[name] = result

        status = "✅" if not result["error"] else "❌"
        print(f"[{time.strftime('%H:%M:%S')}] {status} {desc} 完成 ({result['elapsed']}s)\n",
              flush=True, file=sys.stderr)

    return results


# ── 聚合分析 ──

def smart_aggregate(query: str, results: dict) -> dict:
    """聚合分析多个模型的回答"""
    settings = CONFIG.get("settings") or {}
    agg_cfg = settings.get("aggregator")
    if not agg_cfg or not agg_cfg.get("enabled", False):
        return {"error": "未启用"}

    valid = [v for v in results.values()
             if not v.get("error") and not v.get("placeholder")]
    if len(valid) < 2:
        return {"error": "有效回复不足", "count": len(valid)}

    # 构建聚合 Prompt
    parts = [
        f"用户问题：{query}",
        f"\n共 {len(valid)} 个 AI 参与回答。\n",
        "各模型回复如下：\n"
    ]

    for idx, (name, r) in enumerate(sorted(results.items(),
                                           key=lambda x: x[1].get("elapsed", 0)), 1):
        if r.get("error") or r.get("placeholder"):
            continue
        parts.append(f"{'='*50}")
        parts.append(f"[{idx}] {r['name']} ({r['elapsed']}s)")
        parts.append(f"{'='*50}")
        parts.append(r["content"][:1500])  # 截断避免过长
        parts.append("")

    parts.append(f"{'='*50}")
    parts.append("""
请对以上回答进行深度分析，按以下格式输出：

## 📊 一致性评分
用星级 (★/☆) 表示一致程度，说明理由。
评分标准：
- 有独立思考、反问、质疑 = 正面（加分）
- 只有具体数据/参数/型号 = 高分
- 泛泛而谈、套话 = 低分
- 暴露底层模型身份 = 严重扣分

## 🏆 最佳答案
选出最好的模型并说明原因。

## 💡 各模型亮点
每个模型独特或有价值的观点。

## ⚠️ 关键差异
重要分歧或矛盾点。

## 📝 综合建议
给用户的简明总结建议。
""")

    url = agg_cfg.get("url")
    api_key = os.environ.get(agg_cfg.get("api_key", "") or "") \
        if agg_cfg.get("api_key") else None

    if not url or not api_key:
        return {"error": "聚合模型未配置"}

    try:
        content = call_api(
            url, api_key, agg_cfg.get("model", "gpt-4o"),
            "\n".join(parts),
            system="你是一个严谨的 AI 评测专家。注意：不同意见、质疑、反问属于独立思考，应给予正面评价。必须输出中文。",
            temperature=0.5, max_tokens=2048, timeout=90
        )
    except Exception as e:
        content = f"[聚合分析调用失败: {e}]"

    return {"name": "📊 聚合分析", "content": content, "valid_count": len(valid)}


# ── 输出格式化 ──

def format_reply(results: dict, query: str, aggregated: dict = None) -> str:
    """格式化最终输出"""
    valid = [v for v in results.values() if not v.get("error")]
    errors = [v for v in results.values() if v.get("error")]
    total_time = round(sum(v.get("elapsed", 0) for v in valid), 1)

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"🎯 问题：{query[:50]}{'...' if len(query) > 50 else ''}")
    lines.append(f"{'='*55}\n")

    # 聚合分析优先展示
    if aggregated and not aggregated.get("error"):
        lines.append(aggregated["content"])
        lines.append(f"\n{'='*55}\n")

    # 各模型回复
    for name, result in sorted(results.items(),
                               key=lambda x: x[1].get("elapsed", 0)):
        status = "✅" if not result.get("error") else "❌"
        lines.append(f"{status} {result['name']} ({result['elapsed']}s)")
        lines.append(f"{'-'*40}")
        lines.append(result["content"])
        lines.append("")

    # 统计
    lines.append(f"{'='*55}")
    lines.append(f"📈 统计：{len(valid)} 成功 | {len(errors)} 失败 | 总耗时 {total_time}s")
    lines.append(f"{'='*55}")

    return "\n".join(lines)


# ── 入口 ──

def main():
    if len(sys.argv) < 2:
        print("用法: dispatch_v3.py <模式> [问题...]", file=sys.stderr)
        print("  模式: all | cherry | wb | hermes | openclaw | status | models",
              file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    query = " ".join(sys.argv[2:])
    all_models = {**CONFIG.get("models", {}), **CONFIG.get("templates", {})}

    if mode == "all":
        # 串行调用所有模型
        results = call_all_serial(query)

        # 如果 query 包含聚合分析关键词，或强制聚合
        force_agg = "聚合分析" in query or "对比" in query or "评测" in query
        if force_agg or True:  # all: 默认聚合
            print("\n[@聚合分析中...]", flush=True, file=sys.stderr)
            agg = smart_aggregate(query, results)
            if not agg.get("error"):
                results["aggregated"] = agg

        print(format_reply(results, query, results.get("aggregated")))

    elif mode in all_models:
        result = call_single(mode, query)
        print(f"[{result['name']} | {result['elapsed']}s]\n{result['content']}")

    elif mode == "status":
        env_ok = bool(os.environ.get("CHERRY_API_KEY"))
        print(json.dumps({
            "status": "ok",
            "mode": "serial",
            "env_loaded": env_ok,
            "models": {k: v.get("name", k)
                      for k, v in all_models.items() if v.get("enabled")}
        }, indent=2, ensure_ascii=False))

    elif mode == "models":
        print(json.dumps({
            k: {"name": v.get("name", k), "enabled": v.get("enabled", False)}
            for k, v in all_models.items()
        }, indent=2, ensure_ascii=False))
    else:
        print(f"未知模式: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
