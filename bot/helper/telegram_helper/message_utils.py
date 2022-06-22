import shutil, psutil
import logging
import threading
from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time, sleep
from math import ceil
from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import head as rhead

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TimedOut, BadRequest, RetryAfter
from telegram.message import Message
from telegram.update import Update
from pyrogram.errors import FloodWait
from telegram.ext import CallbackQueryHandler, CallbackContext

from bot import *
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import setInterval

COUNT = 0
PAGE_NO = 1

FINISHED_PROGRESS_STR = "▰"
UNFINISHED_PROGRESS_STR = "▱"
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
    msg, buttons = get_readable_message()
    with status_reply_dict_lock:
        for chat_id in list(status_reply_dict.keys()):
            if status_reply_dict[chat_id] and msg != status_reply_dict[chat_id].text:
                if buttons == "":
                    editMessage(msg, status_reply_dict[chat_id])
                else:
                    editMessage(msg, status_reply_dict[chat_id], buttons)
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
        
def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    if total == 0:
        p = 0
    else:
        p = round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    cPart = p % 8 - 1
    p_str = FINISHED_PROGRESS_STR * cFull
    if cPart >= 0:
        # p_str += PROGRESS_INCOMPLETE[cPart]
        p_str += FINISHED_PROGRESS_STR
    p_str += UNFINISHED_PROGRESS_STR * (PROGRESS_MAX_SIZE - cFull)
    p_str = f"[{p_str}]"
    return p_str

def progress_bar(percentage):
    """Returns a progress bar for download
    """
    #percentage is on the scale of 0-1
    comp = FINISHED_PROGRESS_STR
    ncomp = UNFINISHED_PROGRESS_STR
    pr = ""

    if isinstance(percentage, str):
        return "NaN"
    try:
        percentage=int(percentage)
    except:
        percentage = 0

    for i in range(1,11):
        if i <= int(percentage/10):
            pr += comp
        else:
            pr += ncomp
    return pr

def get_readable_message():
    with download_dict_lock:
        num_active = 0
        num_waiting = 0
        num_upload = 0
        for stats in list(download_dict.values()):
            if stats.status() == MirrorStatus.STATUS_DOWNLOADING:
               num_active += 1
            if stats.status() == MirrorStatus.STATUS_WAITING:
               num_waiting += 1
            if stats.status() == MirrorStatus.STATUS_UPLOADING:
               num_upload += 1
        msg = f"<b>═════〣 ᴀʀᴋ ᴍɪʀʀᴏʀ 〣═════</b>\n\n"
        msg +=f"<b> DL : {num_active}  ||  UL : {num_upload}  ||  QUEUED : {num_waiting}</b>\n\n"
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            msg += f"<b>ɴᴀᴍᴇ :</b> <code>{escape(str(download.name()))}</code>"
            msg += f"\n\n<b>sᴛᴀᴛᴜs :</b> <i>{download.status()}</i>"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n\n{get_progress_bar_string(download)} {download.progress()}"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"\n\n<b>ᴄʟᴏɴᴇᴅ :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"\n\n<b>ᴜᴘʟᴏᴀᴅᴇᴅ :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                else:
                    msg += f"\n\n<b>ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                msg += f"\n<b>sᴘᴇᴇᴅ :</b> {download.speed()} | <b>ETA:</b> {download.eta()}"
                msg += f"\n<b>ᴇʟᴀᴘsᴇᴅ : </b>{get_readable_time(time.time() - download.message.date.timestamp())}"
                msg += f'\n<b>sᴏᴜʀᴄᴇ :</b> <a href="https://t.me/c/{str(download.message.chat.id)[4:]}/{download.message.message_id}">{download.message.from_user.first_name}</a>'
                try:
                    msg += f"\n<b>sᴇᴇᴅᴇʀs :</b> {download.aria_download().num_seeders}" \
                           f" | <b>ᴘᴇᴇʀs :</b> {download.aria_download().connections}"
                    msg += f"\n<b>ᴇɴɢɪɴᴇ : Aria2c</b>"
                except:
                    pass
                try:
                    msg += f"\n<b>sᴇᴇᴅᴇʀs :</b> {download.torrent_info().num_seeds}" \
                           f" | <b>ʟᴇᴇᴄʜᴇʀs :</b> {download.torrent_info().num_leechs}"
                    msg += f"\n<b>ᴇɴɢɪɴᴇ : qBittorrent</b>"
                except:
                    pass
                try:
                    if download.status() == MirrorStatus.STATUS_UPLOADING:
                        msg += f"\n<b>ᴇɴɢɪɴᴇ : Google Api</b>"
                except BaseException:
                    pass
                msg += f'\n<b>Requested User : </b> ️<code>{download.message.from_user.first_name}</code>️(<code>{download.message.from_user.id}</code>)'
                msg += f"\n<b>To Cancel : </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>Size : </b>{download.size()}"
                msg += f"\n<b>ᴇɴɢɪɴᴇ :</b> <code>qBittorrent</code>"
                msg += f"\n<b>sᴘᴇᴇᴅ : </b>{get_readable_file_size(download.torrent_info().upspeed)}/s"
                msg += f" | <b>ᴜᴘʟᴏᴀᴅᴇᴅ : </b>{get_readable_file_size(download.torrent_info().uploaded)}"
                msg += f"\n<b>Ratio : </b>{round(download.torrent_info().ratio, 3)}"
                msg += f" | <b>Time : </b>{get_readable_time(download.torrent_info().seeding_time)}"
                msg += f"\n<code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                msg += f"\n<b>Size : </b>{download.size()}"
            msg += "\n\n<b>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</b>\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f""
        dlspeed_bytes = 0
        upspeed_bytes = 0
        for download in list(download_dict.values()):
            spd = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in spd:
                    dlspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dlspeed_bytes += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in spd:
                    upspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    upspeed_bytes += float(spd.split('M')[0]) * 1048576
        bmsg += f"<b>DL:</b> {get_readable_file_size(dlspeed_bytes)}/s | <b>UL:</b> {get_readable_file_size(upspeed_bytes)}/s"

        buttons = ButtonMaker()
        buttons.sbutton("Refresh", str(ONE))
        buttons.sbutton("Stats", str(THREE))
        buttons.sbutton("Close", str(TWO))
        sbutton = InlineKeyboardMarkup(buttons.build_menu(3))

        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>Tasks:</b> {tasks}\n"
            buttons = ButtonMaker()
            buttons.sbutton("Prev", "status pre")
            buttons.sbutton(f"{PAGE_NO}/{pages}", str(THREE))
            buttons.sbutton("Next", "status nex")
            button = InlineKeyboardMarkup(buttons.build_menu(3))
            return msg + bmsg, button
        return msg + bmsg, 
            
ONE, TWO, THREE = range(3)
        
def refresh(update, context):
    query = update.callback_query
    query.edit_message_text(text="Refreshing Status...Please Wait!!")
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
        query.answer(text="Why are you Gay!", show_alert=True)

def pop_up_stats(update, context):
    query = update.callback_query
    stats = bot_sys_stats()
    query.answer(text=stats, show_alert=True)
    
def bot_sys_stats():
    currentTime = get_readable_time(time.time() - botStartTime)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage(DOWNLOAD_DIR).percent
    total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    stats = f"""
<b>CPU :</b> {progress_bar(cpu)} {cpu}%
<b>RAM :</b> {progress_bar(mem)} {mem}%
<b>DISK :</b> {progress_bar(disk)} {disk}%
<b>SENT :</b> {sent} || <b>RECV :</b> {recv}
<b>Team Ark Mirror ;)</b>
"""

    return stats

dispatcher.add_handler(CallbackQueryHandler(refresh, pattern='^' + str(ONE) + '$'))
dispatcher.add_handler(CallbackQueryHandler(close, pattern='^' + str(TWO) + '$'))
dispatcher.add_handler(CallbackQueryHandler(pop_up_stats, pattern='^' + str(THREE) + '$'))      
