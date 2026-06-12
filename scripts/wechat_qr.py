#!/usr/bin/env python3
"""
HermesClaw v1.0 - 微信绑定二维码生成器
生成微信配置二维码，包含所有已配置的智能体
"""

import json, os, sys, textwrap
from pathlib import Path

# 尝试导入 qrcode
HAS_QRCODE = False
try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    pass

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
AGENTS_FILE = PROJECT_DIR / "config" / "agents.json"
ENV_FILE = PROJECT_DIR / "config" / ".env"

def load_agents():
    if not AGENTS_FILE.exists():
        return {"agents": {}}
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_text_qr(text, width=40):
    """用 Unicode 方块字符生成文本二维码"""
    try:
        import qrcode
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1)
        qr.add_data(text)
        qr.make(fit=True)
        # 转换成大字符
        module = qr.modules
        lines = []
        for i in range(0, len(module), 2):
            line = ""
            for j in range(len(module[0])):
                top = module[i][j]
                bottom = module[i+1][j] if i+1 < len(module) else False
                if top and bottom:
                    line += "█"
                elif top and not bottom:
                    line += "▀"
                elif not top and bottom:
                    line += "▄"
                else:
                    line += " "
            lines.append(line)
        return "\n".join(lines)
    except:
        return None

def generate_wechat_config():
    agents = load_agents()
    enabled = {k: v for k, v in agents.get("agents", {}).items() if v.get("enabled", False)}

    if not enabled:
        print("❌ 没有启用的智能体。请先运行: python3 scripts/setup.py install")
        return

    # 生成配置文本
    config_lines = ["🐿️ HermesClaw 智能体配置", "=" * 30, ""]
    config_lines.append("微信触发方式：")
    for aid, cfg in enabled.items():
        trigger = f"{aid}:"
        config_lines.append(f"  {trigger} {cfg['name']}")
    config_lines.append("")
    config_lines.append("all: → 调用所有智能体")
    config_lines.append("all:聚合分析 → 深度对比分析")

    config_text = "\n".join(config_lines)

    print(f"\n{'='*50}")
    print("🐿️  HermesClaw 微信配置")
    print(f"{'='*50}\n")
    print(config_text)
    print(f"\n{'='*50}\n")

    # 保存文本版
    txt_path = PROJECT_DIR / "config" / "wechat_config.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(config_text)
    print(f"✅ 配置文本已保存: {txt_path}")

    # 尝试生成二维码图片
    if HAS_QRCODE:
        qr_path = PROJECT_DIR / "config" / "wechat_qrcode.png"
        qr = qrcode.QRCode(version=3, box_size=10, border=4)
        qr.add_data(config_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(qr_path)
        print(f"✅ 二维码图片已保存: {qr_path}")

        # 尝试生成终端二维码
        text_qr = generate_text_qr(config_text)
        if text_qr:
            print(f"\n📱 终端二维码（截图发给用户）：")
            print(text_qr)
    else:
        print("\n💡 提示: 安装 qrcode 模块可生成二维码图片")
        print("   pip install qrcode[pil]")

    print(f"\n🚀 微信使用方法：")
    print("   1. 截图上述配置发到微信")
    print("   2. 用户发送 'oc:问题' 即可调用")
    print("   3. 发送 'all:问题' 调用全部")
    print(f"\n配置文件中定义的前缀映射：")
    for aid, cfg in enabled.items():
        print(f"   {aid}: → {cfg['name']}")

if __name__ == "__main__":
    generate_wechat_config()
