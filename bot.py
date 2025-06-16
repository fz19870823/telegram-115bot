import os  
import configparser
import sys
import time
import random
import httpx
import aiohttp
import logging
import traceback
from telegram import Update, BotCommand
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)

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

        cid = load_user_cid(user_id) or "0"
        success, result = await add_cloud_download_task(access_token, links, cid)
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
    config = read_config()
    section = f"user_{user_id}"

    # 检查用户是否已存在于配置文件中
    if section in config:
        await update.message.reply_text('你好，我是你的机器人！请发送磁力链接（magnet）或电驴链接（ed2k）进行识别。')
    else:
        # 用户不存在于配置文件中，保存用户信息并回复提示
        save_user_cid(user_id, "0")  # 保存用户 CID 默认值为 0
        response_text = (
            '你好，我是你的机器人！请发送磁力链接（magnet）或电驴链接（ed2k）进行识别。\n'
            f'👤 用户 ID: {user_id}\n'
            f'📁 CID: 0（默认值）'
        )
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


async def ask_cid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: ask_cid")
    await update.message.reply_text("请输入你的 115 CID：")
    return ASK_CID

async def save_cid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: save_cid")
    cid = update.message.text.strip()
    user_id = str(update.effective_user.id)

    try:
        save_user_cid(user_id, cid)
        await update.message.reply_text(f"CID 已保存为：{cid}")
        return ConversationHandler.END
    except Exception:
        logging.error(f"保存 CID 时发生异常:\n{traceback.format_exc()}")
        await update.message.reply_text("保存 CID 时发生错误。")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Executing: cancel")
    await update.message.reply_text("已取消设置 refresh_token。")
    return ConversationHandler.END

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理 /status 命令，返回用户 ID、CID、access_token 和 refresh_token。
    如果未设定 CID，则返回默认值 0。
    """
    user_id = str(update.effective_user.id)
    cid = load_user_cid(user_id) or "0"
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

    # 新增：计算 access_token 有效期并转换为北京时间
    expire_at = tokens["access_token_expire_at"]
    if expire_at > 0:
        expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_at))
    else:
        expire_time = "未知"

    response_text = (
        f"👤 用户 ID: {user_id}\n"
        f"📁 CID: {cid}\n"
        f"🔑 Access Token: {tokens['access_token']}\n"
        f"⏰ Access Token 有效期: {expire_time}\n"  # 新增：显示 access_token 有效期
        f"🔄 Refresh Token: {tokens['refresh_token']}"
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

    cid = load_user_cid(user_id)
    if not cid:
        await update.message.reply_text("未设置 CID，请先通过 /set_cid 设置。")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        try:
            # 第一步：创建新文件夹
            folder_id, folder_name = await create_folder(client, cid)
            logging.info(f"已创建文件夹：{folder_name}（CID: {folder_id}）")

            # 第二步：列出视频文件并找出大于200MB的文件
            files = await list_files(client, cid)
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
            # 修改：接收 delete_ids 和 deleted_names
            delete_ids, deleted_names = await delete_files(client, cid, exclude_ids={folder_id})
            logging.info("目录清理完成")

            # 发送整理结果
            result_text = "视频文件整理完成！\n"
            result_text += f"移动文件数: {len(moved_files)}\n"
            result_text += f"删除文件/文件夹数: {len(delete_ids)}\n\n"  # 修改：使用 delete_ids 的长度
            result_text += "移动的文件详情:\n"
            for file in moved_files:
                result_text += f"- 文件名: {file['name']}, 大小: {file['size'] / (1024 * 1024):.2f} MB\n"
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
async def list_files(client, cid):
    url = "https://proapi.115.com/open/ufile/files"
    params = {
        "cid": str(cid),
        "type": 4,  # 视频类型
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

async def setup_commands(app):
    logging.info("Executing: setup_commands")
    await app.bot.set_my_commands([
        BotCommand(command="start", description="开始与机器人交互"),
        BotCommand(command="set_refresh_token", description="设置 115 的 refresh_token"),
        BotCommand(command="set_cid", description="设置 115 的 CID"),
        BotCommand(command="status", description="查看用户状态（包括用户 ID、CID、access_token 和 refresh_token）"),
        BotCommand(command="quota", description="查看离线任务配额信息"),
        BotCommand(command="organize_videos", description="整理视频文件")  # 新增命令
    ])

def main():
    logging.info("Executing: main")
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
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("quota", handle_quota))
    app.add_handler(CommandHandler("organize_videos", handle_organize_videos))  # 注册新命令
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_task))

    app.run_polling()

if __name__ == '__main__':
    main()

