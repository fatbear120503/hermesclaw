import os
from openclaw.router import MultiPlatformRouter, PlatformConfig

def create_router():
    router = MultiPlatformRouter()
    
    router.register("hm:", PlatformConfig(
        name="SenseNova",
        base_url="https://api.sensenova.cn/v1",
        api_key=os.getenv("SENSENOVA_API_KEY", ""),
        model="SenseNova-6.7-Flash-Lite",
    ))
    
    router.register("gpt:", PlatformConfig(
        name="CherryStudio",
        base_url=os.getenv("GPT_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("GPT_API_KEY", ""),
        model=os.getenv("GPT_MODEL", "gpt-4o"),
    ))
    
    router.register("cherry:", PlatformConfig(
        name="Cherry",
        base_url="https://api.sensenova.cn/v1",
        api_key=os.getenv("CHERRY_API_KEY", ""),
        model=os.getenv("CHERRY_MODEL", "sensenova-6.7-flash-lite"),
    ))
    
    router.register("wb:", PlatformConfig(
        name="WorkBuddy",
        base_url=os.getenv("WorkBuddy_BASE_URL", "https://api.siliconflow.cn/v1"),
        api_key=os.getenv("WorkBuddy_API_KEY", ""),
        model=os.getenv("WorkBuddy_MODEL", "Qwen/Qwen3-8B"),
    ))
    
    return router
