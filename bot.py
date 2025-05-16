import os 
import configparser
import re
import sys
import time
import aiohttp
from telegram import Update, BotCommand
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)

CONFIG_FILE = 'config.ini'
ASK_REFRESH_TOKEN = 1

API_REFRESH_URL = "https://passportapi.115.com/open/refreshToken"
API_ADD_TASK_URL = "https://passportapi.115.com/open/offline/add_task_urls"

def get_bot_token():
    """获取Telegram机器人token"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token

    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if 'telegram' in config and 'token' in config['telegram']:
            return config['telegram']['token']

    print("未找到 TELEGRAM_BOT_TOKEN 环境变量，且 config.ini 中也无 token。", file=sys.stderr)
    sys.exit(1)

def read_config():
    """读取配置文件"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    return config

def write_config(config):
    """写入配置文件"""
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def load_user_tokens(user_id):
    """加载指定用户的tokens"""
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        return None
    return {
        "access_token": config[section].get("access_token"),
        "refresh_token": config[section].get("refresh_token"),
        "access_token_expire_at": int(config[section].get("access_token_expire_at", "0")),
    }

def save_user_tokens(user_id, access_token, refresh_token, expires_in):
    """保存指定用户的tokens及过期时间"""
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}

    config[section]['access_token'] = access_token
    config[section]['refresh_token'] = refresh_token
    expire_at = int(time.time()) + int(expires_in) - 60
    config[section]['access_token_expire_at'] = str(expire_at)

    write_config(config)

def extract_links(text):
    """从文本中提取所有支持的链接"""
    magnet_pattern = r"magnet:\?xt=urn:[a-zA-Z0-9:%.&=\-]+"
    ed2k_pattern = r"ed2k://\|file\|.+?\|"
    http_pattern = r"(https?://[^\s]+)"
    ftp_pattern = r"(ftp://[^\s]+)"

    magnets = re.findall(magnet_pattern, text)
    ed2ks = re.findall(ed2k_pattern, text)
    https = re.findall(http_pattern, text)
    ftps = re.findall(ftp_pattern, text)

    return magnets + ed2ks + https + ftps

async def refresh_access_token(refresh_token):
    """使用refresh_token刷新access_token"""
    data = {"refresh_token": refresh_token}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with aiohttp.ClientSession() as session:
        async with session.post(API_REFRESH_URL, data=data, headers=headers) as resp:
            if resp.status != 200:
                return None, f"刷新access_token请求失败，状态码: {resp.status}"
            resp_json = await resp.json()
            if resp_json.get("error") or resp_json.get("code", 0) != 0:
                return None, f"刷新access_token失败: {resp_json.get('message', resp_json.get('error'))}"
            return resp_json.get("data"), None

async def check_and_get_access_token(user_id, context):
    """确保有有效access_token，过期自动刷新"""
    tokens = load_user_tokens(user_id)
    if not tokens or not tokens.get("refresh_token"):
        await context.bot.send_message(chat_id=user_id, text="你还没有保存 115 的 refresh_token，请先通过 /set_refresh_token 设置。")
        return None

    now = int(time.time())
    if tokens["access_token"] and tokens["access_token_expire_at"] > now:
        return tokens["access_token"]

    data, err = await refresh_access_token(tokens["refresh_token"])
    if err:
        await context.bot.send_message(chat_id=user_id, text=f"刷新access_token失败：{err}")
        return None

    save_user_tokens(user_id, data['access_token'], data['refresh_token'], data['expires_in'])
    return data['access_token']

async def add_cloud_download_task(access_token, urls, wp_path_id="0"):
    """调用API添加云下载任务"""
    payload = {
        "urls": "\n".join(urls),
        "wp_path_id": wp_path_id
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(API_ADD_TASK_URL, data=payload, headers=headers) as resp:
            if resp.status != 200:
                return False, f"添加下载任务失败，状态码：{resp.status}"
            resp_json = await resp.json()
            if resp_json.get("state") is True and resp_json.get("code") == 0:
                return True, ""
            else:
                return False, resp_json.get("message") or "添加任务失败，未知错误。"

async def handle_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户发送的下载链接消息，添加任务"""
    user_id = str(update.effective_user.id)
    access_token = await check_and_get_access_token(user_id, context)
    if not access_token:
        return

    links = extract_links(update.message.text.strip())
    if not links:
        await update.message.reply_text("未检测到有效的下载链接，请发送支持的HTTP(S)、FTP、磁力链或电驴链接。")
        return

    success, msg = await add_cloud_download_task(access_token, links)
    if success:
        await update.message.reply_text("任务添加成功！")
    else:
        await update.message.reply_text(f"添加任务失败：{msg}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('你好，我是你的机器人！请发送磁力链接（magnet）、电驴链接（ed2k）或其他支持的下载链接进行识别。')

async def ask_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("请输入你的 115 refresh_token：")
    return ASK_REFRESH_TOKEN

async def save_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    refresh_token = update.message.text.strip()
    user_id = str(update.effective_user.id)

    data, err = await refresh_access_token(refresh_token)
    if err:
        await update.message.reply_text(f"刷新access_token失败：{err}，请确认refresh_token是否正确。")
        return ConversationHandler.END

    save_user_tokens(user_id, data['access_token'], data['refresh_token'], data['expires_in'])

    # 保存refresh_token到配置文件
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}
    config[section]['refresh_token'] = refresh_token
    write_config(config)

    await update.message.reply_text("refresh_token 和 access_token 已保存。")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("已取消设置 refresh_token。")
    return ConversationHandler.END

async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand(command="start", description="开始与机器人交互"),
        BotCommand(command="set_refresh_token", description="设置 115 的 refresh_token")
    ])

def main():
    token = get_bot_token()
    app = ApplicationBuilder().token(token).post_init(setup_commands).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("set_refresh_token", ask_refresh_token)],
        states={
            ASK_REFRESH_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_refresh_token)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_task))

    app.run_polling()

if __name__ == '__main__':
    main()
