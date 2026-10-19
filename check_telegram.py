"""Read-only Telegram connectivity check; never prints the token."""
import asyncio
import logging

from dotenv import dotenv_values
from telegram import Bot
from telegram.request import HTTPXRequest

logging.disable(logging.CRITICAL)


async def check():
    config = dotenv_values('.env')
    try:
        proxy = config.get('TELEGRAM_PROXY_URL') or None
        async with Bot(config.get('TELEGRAM_BOT_TOKEN', ''), request=HTTPXRequest(proxy_url=proxy)) as bot:
            me = await bot.get_me()
            webhook = await bot.get_webhook_info()
            print('Telegram authorization OK')
            print('Username matches:', me.username == config.get('TELEGRAM_BOT_USERNAME', '').strip().lstrip('@'))
            print('Webhook configured:', bool(webhook.url))
    except Exception as error:
        print('Connection failed:', type(error).__name__)
        token = config.get('TELEGRAM_BOT_TOKEN', '')
        cause = error.__cause__
        while cause:
            detail = str(cause)
            if token:
                detail = detail.replace(token, '[REDACTED]')
            print('Cause:', type(cause).__name__, detail[:400])
            cause = cause.__cause__
        raise SystemExit(1) from None


if __name__ == '__main__':
    asyncio.run(check())
