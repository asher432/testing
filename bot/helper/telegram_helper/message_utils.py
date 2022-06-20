from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, CallbackQueryHandler
from telegram.message import Message
from re import match as re_match, findall as re_findall
from threading import Thread, Event
from requests import head as rhead
from telegram.update import Update
from math import ceil
from html import escape
from urllib.request import urlopen
import time
from time import sleep
import psutil
import shutil
from psutil import *
from shutil import *
from bot import botStartTime,DOWNLOAD_STATUS_UPDATE_INTERVAL, dispatcher, OWNER_ID, AUTO_DELETE_MESSAGE_DURATION, LOGGER, bot, \
    status_reply_dict, status_reply_dict_lock, download_dict, download_dict_lock, Interval, STATUS_LIMIT, DOWNLOAD_DIR
from bot.helper.ext_utils.bot_utils import get_readable_message, get_readable_file_size, get_readable_time, MirrorStatus, setInterval,get_progress_bar_string, progress_bar
from telegram.error import TimedOut, BadRequest, RetryAfter
from pyrogram.errors import FloodWait

from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.bot_commands import BotCommands

COUNT = 0
PAGE_NO = 1

FINISHED_PROGRESS_STR = "▓"
UNFINISHED_PROGRESS_STR = "░"
PROGRESS_MAX_SIZE = 100 // 8

def sendMessage(text: str, bot, message: Message):
    try:
        return bot.sendMessage(message.chat_id,
                            reply_to_message_id=message.message_id,
                            text=text, allow_sending_without_reply=True, parse_mode='HTMl', disable_web_page_preview=True)
    except RetryAfter as r:
        LOGGER.warning(str(r))
        sleep(r.retry_after * 1.5)
        return sendMessage(text, bot, message)
    except Exception as e:
        LOGGER.error(str(e))
        return

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def sendMarkup(text: str, bot, message: Message, reply_markup: InlineKeyboardMarkup):
    try:
        return bot.sendMessage(message.chat_id,
                            reply_to_message_id=message.message_id,
                            text=text, reply_markup=reply_markup, allow_sending_without_reply=True,
                            parse_mode='HTMl', disable_web_page_preview=True)
    except RetryAfter as r:
        LOGGER.warning(str(r))
        sleep(r.retry_after * 1.5)
        return sendMarkup(text, bot, message, reply_markup)
    except Exception as e:
        LOGGER.error(str(e))
        return

def editMessage(text: str, message: Message, reply_markup=None):
    try:
        bot.editMessageText(text=text, message_id=message.message_id,
                              chat_id=message.chat.id,reply_markup=reply_markup,
                              parse_mode='HTMl', disable_web_page_preview=True)
    except RetryAfter as r:
        LOGGER.warning(str(r))
        sleep(r.retry_after * 1.5)
        return editMessage(text, message, reply_markup)
    except Exception as e:
        LOGGER.error(str(e))
        return

def sendRss(text: str, bot):
    if rss_session is None:
        try:
            return bot.sendMessage(RSS_CHAT_ID, text, parse_mode='HTMl', disable_web_page_preview=True)
        except RetryAfter as r:
            LOGGER.warning(str(r))
            sleep(r.retry_after * 1.5)
            return sendRss(text, bot)
        except Exception as e:
            LOGGER.error(str(e))
            return
    else:
        try:
            with rss_session:
                return rss_session.send_message(RSS_CHAT_ID, text, disable_web_page_preview=True)
        except FloodWait as e:
            LOGGER.warning(str(e))
            sleep(e.value * 1.5)
            return sendRss(text, bot)
        except Exception as e:
            LOGGER.error(str(e))
            return


async def sendRss_pyro(text: str):
    rss_session = Client(name='rss_session', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, session_string=USER_STRING_SESSION, parse_mode=enums.ParseMode.HTML)
    await rss_session.start()
    try:
        return await rss_session.send_message(RSS_CHAT_ID, text, disable_web_page_preview=True)
    except FloodWait as e:
        LOGGER.warning(str(e))
        await asleep(e.value * 1.5)
        return await sendRss(text)
    except Exception as e:
        LOGGER.error(str(e))
        return

def deleteMessage(bot, message: Message):
    try:
        bot.deleteMessage(chat_id=message.chat.id,
                           message_id=message.message_id)
    except Exception as e:
        LOGGER.error(str(e))

def sendLogFile(bot, message: Message):
    with open('log.txt', 'rb') as f:
        bot.sendDocument(document=f, filename=f.name,
                          reply_to_message_id=message.message_id,
                          chat_id=message.chat_id)

def auto_delete_message(bot, cmd_message: Message, bot_message: Message):
    if AUTO_DELETE_MESSAGE_DURATION != -1:
        sleep(AUTO_DELETE_MESSAGE_DURATION)
        try:
            # Skip if None is passed meaning we don't want to delete bot xor cmd message
            deleteMessage(bot, cmd_message)
            deleteMessage(bot, bot_message)
        except AttributeError:
            pass

def delete_all_messages():
    with status_reply_dict_lock:
        for message in list(status_reply_dict.values()):
            try:
                deleteMessage(bot, message)
                del status_reply_dict[message.chat.id]
            except Exception as e:
                LOGGER.error(str(e))

def update_all_messages():
    currentTime = get_readable_time((time.time() - botStartTime))
    msg = get_readable_message()
    msg += f"<b>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</b>\n\n" \
           f"<b>BOT UPTIME :</b> <b>{currentTime}</b>\n\n"
    with download_dict_lock:
        dlspeed_bytes = 0
        uldl_bytes = 0
        for download in list(download_dict.values()):
            speedy = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in speedy:
                    dlspeed_bytes += float(speedy.split('K')[0]) * 1024
                elif 'M' in speedy:
                    dlspeed_bytes += float(speedy.split('M')[0]) * 1048576 
            if download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'K' in speedy:
            	    uldl_bytes += float(speedy.split('K')[0]) * 1024
                elif 'M' in speedy:
                    uldl_bytes += float(speedy.split('M')[0]) * 1048576
        dlspeed = get_readable_file_size(dlspeed_bytes)
        ulspeed = get_readable_file_size(uldl_bytes)
        msg += f"<b>DL :</b> <b>{dlspeed}ps</b> || <b>UL :</b> <b>{ulspeed}ps</b>\n"
    with status_reply_dict_lock:
        for chat_id in list(status_reply_dict.keys()):
            if status_reply_dict[chat_id] and msg != status_reply_dict[chat_id].text:
                if len(msg) == 0:
                    msg = "Starting DL"
                try:
                    keyboard = [[InlineKeyboardButton(" REFRESH ", callback_data=str(ONE)),
                                 InlineKeyboardButton(" CLOSE ", callback_data=str(TWO)),],
                                [InlineKeyboardButton(" STATISTICS ", callback_data=str(THREE)),]]
                    editMessage(msg, status_reply_dict[chat_id], reply_markup=InlineKeyboardMarkup(keyboard))
                except Exception as e:
                    LOGGER.error(str(e))
                status_reply_dict[chat_id].text = msg

def sendStatusMessage(msg, bot):
    if len(Interval) == 0:
        Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
    progress, buttons = get_readable_message()
    with status_reply_dict_lock:
        if msg.chat.id in list(status_reply_dict.keys()):
            try:
                message = status_reply_dict[msg.chat.id]
                deleteMessage(bot, message)
                del status_reply_dict[msg.chat.id]
            except Exception as e:
                LOGGER.error(str(e))
                del status_reply_dict[msg.chat.id]
        if buttons == "":
            message = sendMessage(progress, bot, msg)
        else:
            message = sendMarkup(progress, bot, msg, buttons)
        status_reply_dict[msg.chat.id] = message

ONE, TWO, THREE = range(3)

def refresh(update, context):
    query = update.callback_query
    query.edit_message_text(text="Refreshing Status...Please Wait!")
    time.sleep(2)
    update_all_messages()
    
def close(update, context):
    chat_id  = update.effective_chat.id
    user_id = update.callback_query.from_user.id
    bot = context.bot
    query = update.callback_query
    admins = bot.get_chat_member(chat_id, user_id).status in ['creator', 'administrator'] or user_id in [OWNER_ID]
    if admins:
        delete_all_messages()
    else:
        query.answer(text="Why are you gay!!", show_alert=True)
        
def pop_up_stats(update, context):
    query = update.callback_query
    stats = bot_sys_stats()
    query.answer(text=stats, show_alert=True)

def bot_sys_stats():
    currentTime = get_readable_time(time.time() - botStartTime)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    total, used, free = shutil.disk_usage('.')
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    num_active = 0
    num_upload = 0
    num_split = 0
    num_extract = 0
    num_archi = 0
    tasks = len(download_dict)
    for stats in list(download_dict.values()):
       if stats.status() == MirrorStatus.STATUS_DOWNLOADING:
                num_active += 1
       if stats.status() == MirrorStatus.STATUS_UPLOADING:
                num_upload += 1
       if stats.status() == MirrorStatus.STATUS_ARCHIVING:
                num_archi += 1
       if stats.status() == MirrorStatus.STATUS_EXTRACTING:
                num_extract += 1
       if stats.status() == MirrorStatus.STATUS_SPLITTING:
                num_split += 1
    stats = f"""<b>
═════════〣 ᴀʀᴋ ᴍɪʀʀᴏʀ 〣═════════
ʙᴏᴛ ᴜᴘᴛɪᴍᴇ : {currentTime}
ᴄᴘᴜ : {progress_bar(cpu)} {cpu}%
ʀᴀᴍ : {progress_bar(mem)} {mem}%
ᴅɪsᴋ : {progress_bar(disk)} {disk}%
ᴛᴏᴛᴀʟ : {total}
ᴜsᴇᴅ : {used} || ғʀᴇᴇ : {free}
sᴇɴᴛ : {sent} || ʀᴇᴄᴠ : {recv}</b>
"""
    return stats

dispatcher.add_handler(CallbackQueryHandler(refresh, pattern="^" + str(ONE) + "$"))
dispatcher.add_handler(CallbackQueryHandler(close, pattern="^" + str(TWO) + '$'))
dispatcher.add_handler(CallbackQueryHandler(pop_up_stats, pattern="^" + str(THREE) + "$"))
