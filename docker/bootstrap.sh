#!/bin/sh

echo "[WSDB] for more information please see https://github.com/whiteout-project/bot"

cd /app

if [ -z "${DISCORD_BOT_TOKEN}" ]; then
    echo "please set DISCORD_BOT_TOKEN"
    exit 1
fi

if [ "${WOS_WRITE_TOKEN_FILE}" = "1" ]; then
    echo "${DISCORD_BOT_TOKEN}" > bot_token.txt
fi

if [ "${UPDATE}" = "1" ]; then
    ARGS="--autoupdate"
else
    ARGS="--no-update"
fi

if [ "${BETA}" = "1" ]; then
    ARGS="$ARGS --beta"
fi

if [ "${DEBUG}" = "1" ]; then
    ARGS="$ARGS --debug"
fi

python main.py $ARGS
