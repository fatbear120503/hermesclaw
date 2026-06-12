#!/bin/bash
set -e
PREFIX=$1
NAME=$2
BASE_URL=$3
MODEL=$4
ENV_KEY=$5
if [ -z "$PREFIX" ] || [ -z "$NAME" ] || [ -z "$BASE_URL" ] || [ -z "$MODEL" ]; then
    echo "Usage: ./add_platform.sh <prefix> <name> <base_url> <model> [env_key]"
    exit 1
fi
ENV_KEY=${ENV_KEY:-"${NAME^^}_API_KEY"}
cat >> .env << ENV
# === ${NAME} (${PREFIX}) ===
${ENV_KEY}=your-api-key-here
ENV
sed -i "/return router/i\\    # ${PREFIX} ${NAME}\\n    router.register(\\\"${PREFIX}\\\", PlatformConfig(\\n        name=\\\"${NAME}\\\",\\n        base_url=\\\"${BASE_URL}\\\",\\n        api_key=os.getenv(\\\"${ENV_KEY}\\\", \\\"\\\"),\\n        model=\\\"${MODEL}\\\",\\n    ))\\n" openclaw/config.py
echo "Platform '${NAME}' (${PREFIX}) added!"
echo "1. Set ${ENV_KEY} in .env"
echo "2. Run ./restart.sh to apply"
