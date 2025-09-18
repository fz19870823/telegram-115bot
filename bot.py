import os  
import configparser
import sys
import time
import random
import httpx
import aiohttp
import logging
import traceback
from telegram import Update, Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler, CallbackQueryHandler)

# 修改：明确指定日志文件路径
LOG_FILE = os.path.join(os.path.dirname(__file__), 'bot.log')

# 修改：设置日志，将所有日志合并到一个文件中
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',  # 增加毫秒精度
    datefmt='%Y-%m-%d %H:%M:%S',  # 指定日期时间格式
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),  # 存储所有级别的日志
        logging.StreamHandler(sys.stdout)  # 输出到控制台
    ]
)

CONFIG_FILE = 'config.ini'
ASK_REFRESH_TOKEN = 1
ASK_CID = 2  # 新增CID请求状态

API_REFRESH_URL = "https://passportapi.115.com/open/refreshToken"
API_ADD_TASK_URL = "https://proapi.115.com/open/offline/add_task_urls"

# 可通过环境变量覆盖 Telegram API 基址，方便使用私有反向代理
# 示例: https://my.telegram.proxy
TELEGRAM_API_BASE_URL = os.environ.get('TELEGRAM_API_BASE_URL') or os.environ.get('TELEGRAM_API_URL')

def get_bot_token():
    logging.info("Executing: get_bot_token")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token

    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if 'telegram' in config and 'token' in config['telegram']:
            return config['telegram']['token']

    logging.error("未找到 TELEGRAM_BOT_TOKEN 环境变量，且 config.ini 中也无 token。")
    sys.exit(1)

def read_config():
    logging.info("Executing: read_config")
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    return config

def write_config(config):
    logging.info("Executing: write_config")
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def load_user_tokens(user_id):
    logging.info("Executing: load_user_tokens")
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
    logging.info("Executing: save_user_tokens")
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
    logging.info("Executing: load_user_cid")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        return None
    return config[section].get("cid")

def save_user_cid(user_id, cid):
    logging.info("Executing: save_user_cid")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}
    config[section]['cid'] = cid
    write_config(config)

def save_user_download_folder(user_id, folder_id, folder_path):
    """保存用户的下载文件夹设置"""
    logging.info("Executing: save_user_download_folder")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}
    config[section]['download_folder_id'] = folder_id
    config[section]['download_folder_path'] = folder_path
    write_config(config)

def load_user_download_folder(user_id):
    """加载用户的下载文件夹设置"""
    logging.info("Executing: load_user_download_folder")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        return None, None
    return config[section].get("download_folder_id"), config[section].get("download_folder_path")

def save_user_archive_folder(user_id, folder_id, folder_path):
    """保存用户的归档文件夹设置"""
    logging.info("Executing: save_user_archive_folder")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        config[section] = {}
    config[section]['archive_folder_id'] = folder_id
    config[section]['archive_folder_path'] = folder_path
    write_config(config)

def load_user_archive_folder(user_id):
    """加载用户的归档文件夹设置"""
    logging.info("Executing: load_user_archive_folder")
    config = read_config()
    section = f"user_{user_id}"
    if section not in config:
        return None, None
    return config[section].get("archive_folder_id"), config[section].get("archive_folder_path")

def extract_links(text):
    logging.info("Executing: extract_links")
    return text.strip().split('\n')

async def refresh_access_token(refresh_token):
    logging.info("Executing: refresh_access_token")
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
    logging.info("Executing: check_and_get_access_token")
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
        logging.error(f"检查和获取 access_token 时发生异常: {str(e)}\n堆栈信息:\n{traceback.format_exc()}")
        return None

async def add_cloud_download_task(access_token, urls, wp_path_id="0"):
    logging.info("Executing: add_cloud_download_task")
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
                
                resp_json = await resp.json()  # 仅调用一次
                if resp_json.get("state") is True and resp_json.get("code") == 0:
                    return True, resp_json
                else:
                    # 修改：返回完整的响应内容
                    return False, resp_json
    except Exception:
        logging.error(f"添加任务时发生异常:\n{traceback.format_exc()}")
        return False, {"error": "请求过程中发生异常"}

async def handle_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: handle_add_task")
    try:
        user_id = str(update.effective_user.id)
        access_token = await check_and_get_access_token(user_id, context)
        if not access_token:
            return

        links = extract_links(update.message.text.strip())
        if not links:
            await update.message.reply_text("未检测到有效的下载链接，请发送支持的磁力链（magnet）或电驴链接（ed2k）。")
            return

        # 获取下载文件夹设置
        download_folder_id, download_folder_path = load_user_download_folder(user_id)
        if not download_folder_id:
            await update.message.reply_text("请先通过 /set_download_folder 设置下载文件夹。")
            return

        success, result = await add_cloud_download_task(access_token, links, download_folder_id)
        if success:
            tasks = result.get("data", [])
            if not tasks:
                await update.message.reply_text("未检测到任何任务信息。")
                return

            success_count = sum(1 for task in tasks if task.get("state", False))
            failure_messages = []

            for task in tasks:
                if not task.get("state", False):
                    failure_messages.append(f"\n❌ 失败链接: {task['url']}\n错误信息: {task.get('message', '未知错误')}")

            if success_count > 0:
                success_text = f"✅ 成功添加 {success_count} 个任务。"
                if failure_messages:
                    success_text += "\n以下任务添加失败：" + "\n".join(failure_messages)
                await send_long_message(update, context, success_text)
            elif failure_messages:
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
    logging.info("Executing: start")
    user_id = str(update.effective_user.id)

    # 获取用户的文件夹设置状态
    download_folder_id, download_folder_path = load_user_download_folder(user_id)
    archive_folder_id, archive_folder_path = load_user_archive_folder(user_id)

    response_text = '你好，我是你的机器人！请发送磁力链接（magnet）或电驴链接（ed2k）进行识别。\n\n'
    response_text += f'👤 用户 ID: {user_id}\n'
    response_text += f'📁 下载文件夹: {download_folder_path or "未设置"}\n'
    response_text += f'📦 归档文件夹: {archive_folder_path or "未设置"}\n\n'

    if not download_folder_id:
        response_text += '⚠️ 请先使用 /set_download_folder 设置下载文件夹\n'
    if not archive_folder_id:
        response_text += '⚠️ 请先使用 /set_archive_folder 设置归档文件夹\n'

    await update.message.reply_text(response_text)

async def ask_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: ask_refresh_token")
    await update.message.reply_text("请输入你的 115 refresh_token：")
    return ASK_REFRESH_TOKEN

async def save_refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: save_refresh_token")
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
        logging.error(f"保存 refresh_token 时发生异常:\n{traceback.format_exc()}")
        await update.message.reply_text("保存 refresh_token 时发生错误。")
        return ConversationHandler.END


async def set_download_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置下载文件夹"""
    logging.info("Executing: set_download_folder")
    await show_folder_selection(update, context, "0", 0, "download")

async def set_archive_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置归档文件夹"""
    logging.info("Executing: set_archive_folder")
    await show_folder_selection(update, context, "0", 0, "archive")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: cancel")
    await update.message.reply_text("已取消设置 refresh_token。")
    return ConversationHandler.END

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理 /status 命令，返回用户状态信息
    """
    user_id = str(update.effective_user.id)
    tokens = load_user_tokens(user_id)

    if not tokens or not tokens.get("refresh_token"):
        await update.message.reply_text("你还没有保存 115 的 refresh_token，请先通过 /set_refresh_token 设置。")
        return

    now = int(time.time())
    access_token_valid = False
    if tokens["access_token"] and tokens["access_token_expire_at"] > now:
        access_token_valid = True

    # 如果 access_token 无效，尝试刷新
    if not access_token_valid:
        data, err = await refresh_access_token(tokens["refresh_token"])
        if err:
            await update.message.reply_text(f"刷新 access_token 失败：{err}")
            return

        # 更新 access_token 和 refresh_token
        save_user_tokens(user_id, data['access_token'], data['refresh_token'], data['expires_in'])
        tokens = load_user_tokens(user_id)

    # 计算 access_token 有效期并转换为北京时间
    expire_at = tokens["access_token_expire_at"]
    if expire_at > 0:
        expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_at))
    else:
        expire_time = "未知"

    # 获取文件夹设置
    download_folder_id, download_folder_path = load_user_download_folder(user_id)
    archive_folder_id, archive_folder_path = load_user_archive_folder(user_id)

    response_text = (
        f"� 用户 ID: {user_id}\n"
        f"🔑 Access Token: {tokens['access_token'][:20]}...\n"
        f"⏰ Access Token 有效期: {expire_time}\n"
        f"🔄 Refresh Token: {tokens['refresh_token'][:20]}...\n\n"
        f"📁 下载文件夹: {download_folder_path or '未设置'}\n"
        f"📦 归档文件夹: {archive_folder_path or '未设置'}"
    )
    await update.message.reply_text(response_text)

async def get_quota_info(access_token):
    logging.info("Executing: get_quota_info")
    url = "https://proapi.115.com/open/offline/get_quota_info"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logging.error(f"获取配额信息失败，状态码: {resp.status}")
                    return None, f"获取配额信息失败，状态码: {resp.status}"
                resp_json = await resp.json()
                if resp_json.get("state") is True and resp_json.get("code") == 0:
                    return resp_json.get("data"), None
                else:
                    error_msg = resp_json.get("message") or resp_json.get("error") or "获取配额信息失败，未知错误。"
                    logging.error(f"获取配额信息失败: {error_msg}")
                    return None, error_msg
    except Exception as e:
        logging.error(f"获取配额信息时发生异常: {e}")
        return None, "获取配额信息时发生异常"

async def handle_quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: handle_quota")
    try:
        user_id = str(update.effective_user.id)
        access_token = await check_and_get_access_token(user_id, context)
        if not access_token:
            return

        quota_data, err = await get_quota_info(access_token)
        if err:
            await update.message.reply_text(f"❌ 获取配额信息失败：{err}")
            return

        # 预处理配额数据，防止出现 None 的情况
        quota_data = quota_data or {}
        quota_data.setdefault('count', 0)
        quota_data.setdefault('used', 0)
        quota_data.setdefault('surplus', 0)
        quota_data.setdefault('package', [])

        # 格式化配额信息
        formatted_quota = "📊 **配额信息**\n\n"
        formatted_quota += f"总配额: {quota_data.get('count', 0)}\n"
        formatted_quota += f"已用配额: {quota_data.get('used', 0)}\n"
        formatted_quota += f"剩余配额: {quota_data.get('surplus', 0)}\n\n"

        for package in quota_data.get("package", []):
            package = package or {}
            package.setdefault('name', '未知类型')
            package.setdefault('count', 0)
            package.setdefault('used', 0)
            package.setdefault('surplus', 0)
            package.setdefault('expire_info', [])

            formatted_quota += f"📦 **{package.get('name', '未知类型')}**\n"
            formatted_quota += f"  - 总配额: {package.get('count', 0)}\n"
            formatted_quota += f"  - 已用配额: {package.get('used', 0)}\n"
            formatted_quota += f"  - 剩余配额: {package.get('surplus', 0)}\n"
            formatted_quota += f"  - 明细项过期信息:\n"

            expire_info_list = package.get("expire_info", [])
            if not expire_info_list:
                formatted_quota += "    - 无过期信息\n"
            else:
                for expire_info in expire_info_list:
                    expire_info = expire_info or {}
                    expire_info.setdefault('surplus', 0)
                    expire_info.setdefault('expire_time', 0)

                    formatted_quota += f"    - 剩余配额: {expire_info.get('surplus', 0)}\n"
                    expire_time = expire_info.get('expire_time', 0)
                    if expire_time > 0:
                        formatted_quota += f"    - 过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_time))}\n"
                    else:
                        formatted_quota += "    - 过期时间: 未知\n"
            formatted_quota += "\n"

        await send_long_message(update, context, formatted_quota)
    except Exception as e:
        logging.error(f"获取配额信息时发生内部错误:\n{traceback.format_exc()}")
        await update.message.reply_text("❌ 获取配额信息时发生内部错误。")

async def handle_organize_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理 /organize_videos 命令，执行视频文件整理逻辑。
    """
    logging.info("Executing: handle_organize_videos")
    user_id = str(update.effective_user.id)
    access_token = await check_and_get_access_token(user_id, context)
    if not access_token:
        return

    # 获取下载文件夹设置
    download_folder_id, download_folder_path = load_user_download_folder(user_id)
    if not download_folder_id:
        await update.message.reply_text("请先通过 /set_download_folder 设置下载文件夹。")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        try:
            # 第一步：创建新文件夹
            folder_id, folder_name = await create_folder(client, download_folder_id)
            logging.info(f"已创建文件夹：{folder_name}（CID: {folder_id}）")

            # 第二步：列出视频文件并找出大于200MB的文件
            files = await list_files(client, download_folder_id)
            big_video_ids = []
            moved_files = []
            for file in files:
                if file.get("fc") == "1" and int(file.get("fs", 0)) > 200 * 1024 * 1024:
                    big_video_ids.append(file["fid"])
                    moved_files.append({
                        "name": file.get("fn", "未知文件名"),
                        "size": int(file.get("fs", 0))
                    })
            logging.info(f"准备移动的文件数: {len(big_video_ids)}")

            # 移动文件
            await move_files(client, big_video_ids, folder_id)
            logging.info("文件移动完成")

            # 第三步：清空目录（排除新建文件夹）
            delete_ids, deleted_names = await delete_files(client, download_folder_id, exclude_ids={folder_id})
            logging.info("目录清理完成")

            # 发送整理结果
            result_text = "视频文件整理完成！\n"
            result_text += f"移动文件数: {len(moved_files)}\n"
            result_text += f"删除文件/文件夹数: {len(delete_ids)}\n\n"  # 修改：使用 delete_ids 的长度

            # 记录移动的文件详情到日志中
            for file in moved_files:
                logging.info(f"移动的文件: {file['name']}, 大小: {file['size'] / (1024 * 1024):.2f} MB")

            await send_long_message(update, context, result_text)
        except Exception as e:
            logging.error(f"视频文件整理失败: {e}")
            await update.message.reply_text(f"❌ 视频文件整理失败：{e}")

# 生成随机中文字符串
def random_chinese(length=4):
    return ''.join(chr(random.randint(0x4E00, 0x9FA5)) for _ in range(length))

# 新增函数：创建文件夹
async def create_folder(client, parent_cid):
    url = "https://proapi.115.com/open/folder/add"
    name = random_chinese(random.randint(3, 6))
    data = {
        "pid": str(parent_cid),
        "file_name": name
    }
    response = await client.post(url, data=data)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"创建文件夹失败: {res}")
    return res["data"]["file_id"], res["data"]["file_name"]

# 新增函数：列出文件
async def list_files(client, cid, file_type=4):
    url = "https://proapi.115.com/open/ufile/files"
    params = {
        "cid": str(cid),
        "type": file_type,  # 4=视频类型, 0=所有类型
        "limit": 1150
    }
    response = await client.get(url, params=params)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"获取文件列表失败: {res}")
    return res.get("data", [])

# 新增函数：移动文件
async def move_files(client, file_ids, to_cid):
    if not file_ids:
        return
    url = "https://proapi.115.com/open/ufile/move"
    data = {
        "file_ids": ','.join(file_ids),
        "to_cid": str(to_cid)
    }
    response = await client.post(url, data=data)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"移动文件失败: {res}")

# 新增函数：删除文件
async def delete_files(client, cid, exclude_ids):
    url = "https://proapi.115.com/open/ufile/files"
    params = {
        "cid": str(cid),
        "limit": 1150,
        "show_dir": 1,
    }
    response = await client.get(url, params=params)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"列出文件失败: {res}")
    items = res.get("data", [])

    delete_ids = []
    deleted_names = []  # 新增：用于记录删除的文件（夹）名称
    for item in items:
        item_id = item.get("fid") or item.get("cid")
        if item_id and item_id not in exclude_ids:
            delete_ids.append(item_id)
            deleted_names.append(item.get("fn") or "未知文件名")  # 修改：使用 fn 字段记录文件名

    if delete_ids:
        del_url = "https://proapi.115.com/open/ufile/delete"
        data = {"file_ids": ",".join(delete_ids), "parent_id": str(cid)}
        del_resp = await client.post(del_url, data=data)
        del_res = del_resp.json()
        if not del_res.get("state"):
            raise Exception(f"删除文件失败: {del_res}")
        logging.info(f"已删除文件/文件夹数: {len(delete_ids)}，名称: {', '.join(deleted_names)}")  # 修改：增加删除文件（夹）名称的日志记录
    else:
        logging.info("无可删除内容。")

    # 新增：返回删除的文件 ID 和名称
    return delete_ids, deleted_names

# 新增函数：查找或创建指定路径的文件夹
async def find_or_create_folder_by_path(client, root_cid, folder_path):
    """
    根据路径查找或创建文件夹
    folder_path: 如 "/nc-17/归档"
    返回: (folder_id, folder_name)
    """
    logging.info(f"查找或创建文件夹路径: {folder_path}")

    # 分割路径
    path_parts = [part for part in folder_path.split('/') if part]
    current_cid = root_cid

    for part in path_parts:
        # 查找当前目录下是否存在该文件夹
        folder_found = False
        items = await list_all_items(client, current_cid)

        for item in items:
            # 检查是否为文件夹且名称匹配（文件夹的fc='0'）
            if str(item.get("fc")) == "0" and item.get("fn") == part:
                current_cid = item["fid"]  # 文件夹使用fid作为ID
                folder_found = True
                logging.info(f"找到文件夹: {part} (FID: {current_cid})")
                break

        # 如果没找到，则创建
        if not folder_found:
            current_cid, created_name = await create_folder_with_name(client, current_cid, part)
            logging.info(f"创建文件夹: {created_name} (FID: {current_cid})")

    return current_cid, path_parts[-1] if path_parts else "root"

# 新增函数：创建指定名称的文件夹
async def create_folder_with_name(client, parent_cid, folder_name):
    url = "https://proapi.115.com/open/folder/add"
    data = {
        "pid": str(parent_cid),
        "file_name": folder_name
    }
    response = await client.post(url, data=data)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"创建文件夹失败: {res}")
    return res["data"]["file_id"], res["data"]["file_name"]

# 新增函数：列出所有项目（包括文件和文件夹）
async def list_all_items(client, cid):
    url = "https://proapi.115.com/open/ufile/files"
    params = {
        "cid": str(cid),
        "limit": 1150,
        "show_dir": 1,  # 显示文件夹
    }
    response = await client.get(url, params=params)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"获取项目列表失败: {res}")
    return res.get("data", [])

# 新增函数：获取文件夹列表（仅文件夹）
async def list_folders_only(client, cid, page=0, limit=1150):
    """获取指定目录下的文件夹列表"""
    url = "https://proapi.115.com/open/ufile/files"
    params = {
        "cid": str(cid),
        "limit": 1150,  # 设置为最大值，确保获取所有项目
        "offset": page * limit,
        "show_dir": 1  # 显示文件夹
    }
    response = await client.get(url, params=params)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"获取文件夹列表失败: {res}")

    # 根据官方文档，fc='0'表示文件夹，fc='1'表示文件
    all_items = res.get("data", [])

    # 处理fc字段可能是字符串或数字的情况
    folders = [item for item in all_items if str(item.get("fc")) == "0"]  # 转换为字符串比较

    # 添加调试信息
    logging.info(f"获取文件夹列表 - CID: {cid}, 总项目数: {len(all_items)}, 文件夹数: {len(folders)}")
    for i, folder in enumerate(folders[:3]):  # 只记录前3个文件夹的信息
        logging.info(f"文件夹 {i+1}: 名称={folder.get('fn', '未知')}, FID={folder.get('fid', '未知')}")

    return folders, len(folders)  # 返回实际的文件夹数量

# 新增函数：获取文件夹路径
async def get_folder_path(client, folder_id):
    """获取文件夹的完整路径"""
    if folder_id == "0":
        return "/"  # 根目录

    # 尝试通过文件列表API获取路径信息
    try:
        url = "https://proapi.115.com/open/ufile/files"
        params = {"cid": str(folder_id), "limit": 1}
        response = await client.get(url, params=params)
        res = response.json()

        if res.get("state") and res.get("path"):
            path_data = res.get("path", [])
            if path_data:
                # 构建路径字符串
                path_parts = [item.get("name", "") for item in path_data if item.get("name")]
                return "/" + "/".join(path_parts) if path_parts else "/"
    except Exception as e:
        logging.warning(f"获取路径时发生异常: {e}")

    # 如果无法获取路径，返回文件夹ID作为标识
    return f"/folder_{folder_id}"

# 新增函数：显示文件夹选择界面
async def show_folder_selection(update, context, current_cid="0", page=0, selection_type="download", parent_cid=None):
    """显示文件夹选择界面"""
    user_id = str(update.effective_user.id)
    access_token = await check_and_get_access_token(user_id, context)
    if not access_token:
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        try:
            # 获取文件夹列表（API获取所有，然后分页显示）
            all_folders, total_count = await list_folders_only(client, current_cid, 0, 1150)

            # 分页显示文件夹
            page_size = 8
            start_idx = page * page_size
            end_idx = start_idx + page_size
            folders = all_folders[start_idx:end_idx]

            logging.info(f"显示文件夹选择界面 - 总文件夹数: {total_count}, 当前页显示: {len(folders)}")

            # 获取当前路径
            current_path = await get_folder_path(client, current_cid)

            # 构建键盘
            keyboard = []

            # 如果不是根目录，添加上一层按钮
            if current_cid != "0" and parent_cid:
                keyboard.append([InlineKeyboardButton("⬆️ 上一层", callback_data=f"folder_up_{selection_type}_{parent_cid}_0")])

            # 添加文件夹列表
            for folder in folders:
                folder_name = folder.get("fn", "未知文件夹")
                folder_fid = folder.get("fid")  # 文件夹使用fid作为ID
                if len(folder_name) > 20:
                    display_name = folder_name[:17] + "..."
                else:
                    display_name = folder_name

                # 左侧显示文件夹名，右侧显示选择按钮
                keyboard.append([
                    InlineKeyboardButton(f"📁 {display_name}", callback_data=f"folder_enter_{selection_type}_{folder_fid}_0"),
                    InlineKeyboardButton("✅ 选择", callback_data=f"folder_select_{selection_type}_{folder_fid}")
                ])

            # 添加翻页按钮
            nav_buttons = []
            page_size = 8
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"folder_page_{selection_type}_{current_cid}_{page-1}"))

            if (page + 1) * page_size < total_count:
                nav_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"folder_page_{selection_type}_{current_cid}_{page+1}"))

            if nav_buttons:
                keyboard.append(nav_buttons)

            # 添加取消按钮
            keyboard.append([InlineKeyboardButton("❌ 取消", callback_data=f"folder_cancel_{selection_type}")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            folder_type_name = "下载文件夹" if selection_type == "download" else "归档文件夹"
            page_info = f"第 {page + 1} 页" if total_count > 8 else ""
            message_text = f"请选择{folder_type_name}:\n\n📍 当前路径: {current_path}\n📊 文件夹总数: {total_count} {page_info}"

            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message_text, reply_markup=reply_markup)

        except Exception as e:
            logging.error(f"显示文件夹选择界面失败: {e}")
            error_msg = f"❌ 获取文件夹列表失败：{e}"
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)

# 新增函数：处理文件夹选择回调
async def handle_folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文件夹选择的回调"""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    parts = callback_data.split('_')

    if len(parts) < 3:
        await query.edit_message_text("❌ 无效的操作")
        return

    action = parts[1]  # enter, select, page, up, cancel
    selection_type = parts[2]  # download, archive

    user_id = str(update.effective_user.id)
    access_token = await check_and_get_access_token(user_id, context)
    if not access_token:
        return

    try:
        if action == "enter":
            # 进入文件夹
            folder_fid = parts[3]  # 文件夹的fid
            page = int(parts[4]) if len(parts) > 4 else 0

            # 进入子文件夹，使用fid作为新的cid
            # 这里需要获取当前的cid，暂时使用"0"作为parent_cid
            await show_folder_selection(update, context, folder_fid, page, selection_type, "0")

        elif action == "select":
            # 选择文件夹
            folder_fid = parts[3]  # 文件夹的fid

            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(headers=headers, timeout=20) as client:
                folder_path = await get_folder_path(client, folder_fid)

                if selection_type == "download":
                    save_user_download_folder(user_id, folder_fid, folder_path)
                    await query.edit_message_text(f"✅ 下载文件夹已设置为:\n📁 {folder_path}")
                else:  # archive
                    save_user_archive_folder(user_id, folder_fid, folder_path)
                    await query.edit_message_text(f"✅ 归档文件夹已设置为:\n📁 {folder_path}")

        elif action == "page":
            # 翻页
            current_folder_id = parts[3]
            page = int(parts[4])
            await show_folder_selection(update, context, current_folder_id, page, selection_type)

        elif action == "up":
            # 返回上一层
            parent_cid = parts[3]
            page = int(parts[4]) if len(parts) > 4 else 0
            await show_folder_selection(update, context, parent_cid, page, selection_type)

        elif action == "cancel":
            # 取消选择
            await query.edit_message_text("❌ 已取消文件夹选择")

    except Exception as e:
        logging.error(f"处理文件夹选择回调失败: {e}")
        await query.edit_message_text(f"❌ 操作失败：{e}")

async def handle_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理 /清理 命令，将所有目录下的文件移动到归档目录下
    """
    logging.info("Executing: handle_cleanup")
    user_id = str(update.effective_user.id)
    access_token = await check_and_get_access_token(user_id, context)
    if not access_token:
        return

    # 获取下载文件夹和归档文件夹设置
    download_folder_id, download_folder_path = load_user_download_folder(user_id)
    archive_folder_id, archive_folder_path = load_user_archive_folder(user_id)

    if not download_folder_id:
        await update.message.reply_text("请先通过 /set_download_folder 设置下载文件夹。")
        return

    if not archive_folder_id:
        await update.message.reply_text("请先通过 /set_archive_folder 设置归档文件夹。")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        try:
            await update.message.reply_text("🔄 开始清理操作...")
            await update.message.reply_text(f"📁 下载文件夹：{download_folder_path}")
            await update.message.reply_text(f"📁 归档文件夹：{archive_folder_path}")

            # 获取下载文件夹下的所有文件和文件夹
            await update.message.reply_text("📋 正在获取文件列表...")
            all_items = await list_all_items(client, download_folder_id)

            # 收集需要移动的项目
            items_to_move = []
            moved_items_info = []

            for item in all_items:
                item_id = item.get("fid") or item.get("cid")
                item_name = item.get("fn", "未知文件名")

                if item_id:
                    items_to_move.append(item_id)
                    moved_items_info.append({
                        "name": item_name,
                        "type": "文件夹" if item.get("cid") else "文件",
                        "size": int(item.get("fs", 0)) if item.get("fs") else 0
                    })

            if not items_to_move:
                await update.message.reply_text("✅ 下载文件夹已经是空的，无需清理。")
                return

            await update.message.reply_text(f"📦 找到 {len(items_to_move)} 个项目需要移动到归档目录...")

            # 移动所有文件和文件夹到归档目录
            await move_files(client, items_to_move, archive_folder_id)
            logging.info(f"已移动 {len(items_to_move)} 个项目到归档目录")

            # 发送清理结果
            result_text = "🎉 清理操作完成！\n\n"
            result_text += f"📁 下载文件夹：{download_folder_path}\n"
            result_text += f"📦 归档文件夹：{archive_folder_path}\n"
            result_text += f"📦 移动项目数：{len(moved_items_info)}\n\n"
            result_text += "移动的项目详情：\n"

            for i, item in enumerate(moved_items_info[:20], 1):  # 最多显示前20个
                size_info = ""
                if item["size"] > 0:
                    size_mb = item["size"] / (1024 * 1024)
                    if size_mb >= 1:
                        size_info = f" ({size_mb:.1f} MB)"
                    else:
                        size_info = f" ({item['size']} B)"

                result_text += f"{i}. {item['type']}: {item['name']}{size_info}\n"

            if len(moved_items_info) > 20:
                result_text += f"... 还有 {len(moved_items_info) - 20} 个项目\n"

            # 记录移动的项目详情到日志中
            for item in moved_items_info:
                logging.info(f"移动的{item['type']}: {item['name']}, 大小: {item['size']} 字节")

            await send_long_message(update, context, result_text)

        except Exception as e:
            logging.error(f"清理操作失败: {e}")
            await update.message.reply_text(f"❌ 清理操作失败：{e}")

# 新增函数：获取云下载任务列表
async def get_task_list(client, page=1):
    """获取云下载任务列表"""
    url = "https://proapi.115.com/open/offline/get_task_list"
    params = {"page": page}
    response = await client.get(url, params=params)
    res = response.json()
    if not res.get("state"):
        raise Exception(f"获取任务列表失败: {res}")
    return res.get("data", {})

# 新增函数：获取未完成任务
async def get_incomplete_tasks(client):
    """获取所有未完成的云下载任务"""
    incomplete_tasks = []
    page = 1

    while True:
        logging.info(f"获取第 {page} 页任务列表")
        data = await get_task_list(client, page)
        tasks = data.get("tasks", [])
        page_count = data.get("page_count", 1)

        if not tasks:
            break

        # 检查当前页是否有已完成任务
        has_completed_task = False
        current_page_incomplete = []

        for task in tasks:
            try:
                status = int(task.get("status", -1))
                if status == 2:  # 已完成任务
                    has_completed_task = True
                else:  # 未完成任务
                    current_page_incomplete.append(task)
            except (ValueError, TypeError) as e:
                logging.warning(f"任务状态转换失败: {task.get('status')}, 错误: {e}")
                # 如果状态无法转换，假设是未完成任务
                current_page_incomplete.append(task)

        # 添加当前页的未完成任务
        incomplete_tasks.extend(current_page_incomplete)

        logging.info(f"第 {page} 页：总任务 {len(tasks)}，未完成 {len(current_page_incomplete)}，有已完成任务: {has_completed_task}")

        # 如果当前页有已完成任务，说明后面都是已完成的，停止获取
        if has_completed_task:
            logging.info("发现已完成任务，停止获取后续页面")
            break

        # 如果已经是最后一页，停止获取
        if page >= page_count:
            break

        page += 1

    return incomplete_tasks

# 新增函数：处理获取任务状态命令
async def handle_task_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /task_status 命令，显示未完成的云下载任务"""
    logging.info("Executing: handle_task_status")
    user_id = str(update.effective_user.id)
    access_token = await check_and_get_access_token(user_id, context)
    if not access_token:
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        try:
            await update.message.reply_text("🔄 正在获取云下载任务状态...")

            # 获取所有未完成任务
            incomplete_tasks = await get_incomplete_tasks(client)

            logging.info(f"获取到 {len(incomplete_tasks)} 个未完成任务")

            if not incomplete_tasks:
                await update.message.reply_text("✅ 当前没有未完成的云下载任务！")
                return

            # 构建任务状态消息
            result_text = f"📋 未完成的云下载任务 ({len(incomplete_tasks)} 个):\n\n"

            for i, task in enumerate(incomplete_tasks, 1):
                # 添加调试信息
                logging.info(f"处理任务 {i}: {task}")

                task_name = task.get("name", "未知任务")

                # 安全地转换百分比
                try:
                    percent_done = int(task.get("percentDone", 0))
                except (ValueError, TypeError):
                    percent_done = 0

                # 安全地转换状态
                try:
                    status = int(task.get("status", -1))
                except (ValueError, TypeError):
                    status = -1

                size_raw = task.get("size", 0)

                # 安全地转换文件大小为数字
                try:
                    size = int(size_raw) if size_raw else 0
                except (ValueError, TypeError):
                    logging.warning(f"文件大小转换失败: {size_raw} (类型: {type(size_raw)})")
                    size = 0

                # 状态描述
                status_desc = {
                    -1: "❌ 下载失败",
                    0: "⏳ 分配中",
                    1: "⬇️ 下载中"
                }.get(status, "❓ 未知状态")

                # 文件大小格式化
                if size > 0:
                    size_gb = size / (1024 * 1024 * 1024)
                    if size_gb >= 1:
                        size_info = f" ({size_gb:.1f} GB)"
                    else:
                        size_mb = size / (1024 * 1024)
                        size_info = f" ({size_mb:.1f} MB)"
                else:
                    size_info = ""

                # 进度条
                progress_bar = "█" * (percent_done // 10) + "░" * (10 - percent_done // 10)

                result_text += f"{i}. {status_desc}\n"
                result_text += f"📁 {task_name}{size_info}\n"
                result_text += f"📊 进度: {percent_done}% [{progress_bar}]\n\n"

                # 避免消息过长，最多显示20个任务
                if i >= 20:
                    result_text += f"... 还有 {len(incomplete_tasks) - 20} 个任务\n"
                    break

            await send_long_message(update, context, result_text)

        except Exception as e:
            logging.error(f"获取任务状态失败: {e}")
            await update.message.reply_text(f"❌ 获取任务状态失败：{e}")

async def setup_commands(app):
    logging.info("Executing: setup_commands")
    await app.bot.set_my_commands([
        BotCommand(command="start", description="开始与机器人交互"),
        BotCommand(command="set_refresh_token", description="设置 115 的 refresh_token"),
        BotCommand(command="set_download_folder", description="设置下载文件夹"),
        BotCommand(command="set_archive_folder", description="设置归档文件夹"),
        BotCommand(command="status", description="查看用户状态信息"),
        BotCommand(command="quota", description="查看离线任务配额信息"),
        BotCommand(command="task_status", description="查看未完成的云下载任务状态"),
        BotCommand(command="organize_videos", description="整理视频文件"),
        BotCommand(command="cleanup", description="将下载文件夹的所有文件移动到归档文件夹")
    ])

def main():
    logging.info("Executing: main")
    token = get_bot_token()
    # 如果设置了 TELEGRAM_API_BASE_URL，则将其作为 base_url 传入 ApplicationBuilder
    if TELEGRAM_API_BASE_URL:
        logging.info(f"使用自定义 Telegram API 基址: {TELEGRAM_API_BASE_URL}")
        app = ApplicationBuilder().token(token).base_url(TELEGRAM_API_BASE_URL).post_init(setup_commands).build()
    else:
        logging.info("使用默认的 Telegram API 基址")
        app = ApplicationBuilder().token(token).post_init(setup_commands).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("set_refresh_token", ask_refresh_token)
        ],
        states={
            ASK_REFRESH_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_refresh_token)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("quota", handle_quota))
    app.add_handler(CommandHandler("task_status", handle_task_status))
    app.add_handler(CommandHandler("organize_videos", handle_organize_videos))
    app.add_handler(CommandHandler("cleanup", handle_cleanup))
    app.add_handler(CommandHandler("set_download_folder", set_download_folder))
    app.add_handler(CommandHandler("set_archive_folder", set_archive_folder))
    app.add_handler(CallbackQueryHandler(handle_folder_callback))  # 处理文件夹选择回调
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_task))

    app.run_polling()

if __name__ == '__main__':
    main()

