import os  
import configparser

import sys
import time
import aiohttp
import logging
import traceback
from telegram import Update, BotCommand
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)

# 设置日志
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

CONFIG_FILE = 'config.ini'
ASK_REFRESH_TOKEN = 1
ASK_CID = 2  # 新增CID请求状态

API_REFRESH_URL = "https://passportapi.115.com/open/refreshToken"
API_ADD_TASK_URL = "https://proapi.115.com/open/offline/add_task_urls"

def get_bot_token():
    print("Executing: get_bot_token")
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
    print("Executing: read_config")
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    return config

def write_config(config):
    print("Executing: write_config")
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def load_user_tokens(user_id):
    print("Executing: load_user_tokens")
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
    print("Executing: save_user_tokens")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}

    config[section]['access_token'] = access_token
    config[section]['refresh_token'] = refresh_token
    expire_at = int(time.time()) + int(expires_in) - 60
    config[section]['access_token_expire_at'] = str(expire_at)

    write_config(config)

def load_user_cid(user_id):
    print("Executing: load_user_cid")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        return None
    return config[section].get("cid")

def save_user_cid(user_id, cid):
    print("Executing: save_user_cid")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}
    config[section]['cid'] = cid
    write_config(config)

def extract_links(text):
    print("Executing: extract_links")
    return text.strip().split('\n')

async def refresh_access_token(refresh_token):
    print("Executing: refresh_access_token")
    data = {"refresh_token": refresh_token}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_REFRESH_URL, data=data, headers=headers) as resp:
                if resp.status != 200:
                    logging.error(f"刷新access_token请求失败，状态码: {resp.status}")
                    return None, f"刷新access_token请求失败，状态码: {resp.status}"
                resp_json = await resp.json()
                if "access_token" in resp_json.get("data", {}) and "expires_in" in resp_json.get("data", {}):
                    return resp_json.get("data"), None
                else:
                    error_msg = resp_json.get("error") or resp_json.get("message") or resp_json.get("errno")
                    logging.error(f"刷新access_token失败: {error_msg}")
                    return None, f"刷新access_token失败: {error_msg}"
    except Exception as e:
        logging.error(f"刷新access_token时发生异常: {e}")
        return None, "刷新access_token时发生异常"

async def check_and_get_access_token(user_id, context):
    print("Executing: check_and_get_access_token")
    try:
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

        # 修改：保存新的 access_token 和 refresh_token
        save_user_tokens(user_id, data['access_token'], data['refresh_token'], data['expires_in'])
        return data['access_token']
    except Exception as e:
        logging.error(traceback.format_exc())
        return None

async def add_cloud_download_task(access_token, urls, wp_path_id="0"):
    print("Executing: add_cloud_download_task")
    payload = {
        "urls": "\n".join(urls),
        "wp_path_id": wp_path_id
    }
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_ADD_TASK_URL, data=payload, headers=headers) as resp:
                if resp.status != 200:
                    # 修改：返回完整的响应内容
                    resp_json = await resp.json()
                    return False, resp_json
                try:
                    resp_json = await resp.json()
                except:
                    print(await resp.text())
                    # sys.exit(0)
                if resp_json.get("state") is True and resp_json.get("code") == 0:
                    return True, resp_json
                else:
                    # 修改：返回完整的响应内容
                    return False, resp_json
    except Exception:
        logging.error(traceback.format_exc())
        return False, {"error": "请求过程中发生异常"}

async def handle_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: handle_add_task")
    try:
        user_id = str(update.effective_user.id)
        access_token = await check_and_get_access_token(user_id, context)
        if not access_token:
            return

        links = extract_links(update.message.text.strip())
        if not links:
            await update.message.reply_text("未检测到有效的下载链接，请发送支持的磁力链（magnet）或电驴链接（ed2k）。")
            return

        cid = load_user_cid(user_id) or "0"
        success, result = await add_cloud_download_task(access_token, links, cid)
        if success:
            tasks = result.get("data", [])
            if not tasks:
                await update.message.reply_text("未检测到任何任务信息。")
                return

            success_messages = []
            failure_messages = []

            for task in tasks:
                if task.get("state", False):
                    status = task.get("state", "未知状态")
                    infohash = task.get("info_hash", "无")
                    success_messages.append(f"\n🔗 链接: {task['url']}\n📦 状态: {status}\n🔑 Hash: {infohash}")
                else:
                    failure_messages.append(f"\n❌ 失败链接: {task['url']}\n错误信息: {task.get('message', '未知错误')}")

            if success_messages:
                success_text = "✅ 以下任务添加成功：" + "\n".join(success_messages)
                await send_long_message(update, context, success_text)
            if failure_messages:
                failure_text = "❌ 以下任务添加失败：" + "\n".join(failure_messages)
                await send_long_message(update, context, failure_text)
        else:
            error_msg = result.get("message") or result.get("error") or "添加任务失败，未知错误。"
            logging.error(f"添加任务失败: {error_msg}")
            await update.message.reply_text(f"❌ 添加任务失败：{error_msg}")
    except Exception as e:
        logging.error(f"添加任务时发生内部错误: {e}")
        await update.message.reply_text("❌ 添加任务时发生内部错误。")

# 新增函数：分段发送长消息
async def send_long_message(update, context, message):
    MAX_LENGTH = 4096
    if len(message) > MAX_LENGTH:
        chunks = [message[i:i+MAX_LENGTH] for i in range(0, len(message), MAX_LENGTH)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: start")
    await update.message.reply_text('你好，我是你的机器人！请发送磁力链接（magnet）或电驴链接（ed2k）进行识别。')

async def ask_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: ask_refresh_token")
    await update.message.reply_text("请输入你的 115 refresh_token：")
    return ASK_REFRESH_TOKEN

async def save_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: save_refresh_token")
    refresh_token = update.message.text.strip()
    user_id = str(update.effective_user.id)

    try:
        data, err = await refresh_access_token(refresh_token)
        if err:
            await update.message.reply_text(f"刷新access_token失败：{err}，请确认refresh_token是否正确。")
            return ConversationHandler.END

        # 保存新的 access_token 和 refresh_token（使用接口返回的新 token）
        save_user_tokens(user_id, data['access_token'], data['refresh_token'], data['expires_in'])

        await update.message.reply_text("refresh_token 和 access_token 已保存。")
        return ConversationHandler.END
    except Exception:
        logging.error(traceback.format_exc())
        await update.message.reply_text("保存 refresh_token 时发生错误。")
        return ConversationHandler.END


async def ask_cid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: ask_cid")
    await update.message.reply_text("请输入你的 115 CID：")
    return ASK_CID

async def save_cid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: save_cid")
    cid = update.message.text.strip()
    user_id = str(update.effective_user.id)

    try:
        save_user_cid(user_id, cid)
        await update.message.reply_text(f"CID 已保存为：{cid}")
        return ConversationHandler.END
    except Exception:
        logging.error(traceback.format_exc())
        await update.message.reply_text("保存 CID 时发生错误。")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Executing: cancel")
    await update.message.reply_text("已取消设置 refresh_token。")
    return ConversationHandler.END

async def setup_commands(app):
    print("Executing: setup_commands")
    await app.bot.set_my_commands([
        BotCommand(command="start", description="开始与机器人交互"),
        BotCommand(command="set_refresh_token", description="设置 115 的 refresh_token"),
        BotCommand(command="set_cid", description="设置 115 的 CID")
    ])

def main():
    print("Executing: main")
    token = get_bot_token()
    app = ApplicationBuilder().token(token).post_init(setup_commands).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("set_refresh_token", ask_refresh_token),
            CommandHandler("set_cid", ask_cid)
        ],
        states={
            ASK_REFRESH_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_refresh_token)],
            ASK_CID: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_cid)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_task))

    app.run_polling()

if __name__ == '__main__':
    main()
