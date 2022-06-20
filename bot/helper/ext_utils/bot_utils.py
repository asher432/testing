from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import *
import shutil
from shutil import *
from requests import head as rhead
from urllib.request import urlopen
from telegram import InlineKeyboardMarkup

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR
from bot.helper.telegram_helper.button_build import ButtonMaker

from telegram.error import RetryAfter
from telegram.ext import CallbackQueryHandler
from telegram.message import Message
from telegram.update import Update
from bot import *

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "Uploading..."
    STATUS_DOWNLOADING = "Downloading..."
    STATUS_CLONING = "Cloning...♻"
    STATUS_WAITING = "Queued...💤"
    STATUS_FAILED = "Failed . Cleaning Download..."
    STATUS_PAUSE = "Paused..."
    STATUS_ARCHIVING = "Archiving..."
    STATUS_EXTRACTING = "Extracting..."
    STATUS_SPLITTING = "Splitting...✂"
    STATUS_CHECKING = "CheckingUp..."
    STATUS_SEEDING = "Seeding..."

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time.time() + self.interval
        while not self.stopEvent.wait(nextTime - time.time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'
    
def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if status not in [MirrorStatus.STATUS_ARCHIVING, MirrorStatus.STATUS_EXTRACTING, MirrorStatus.STATUS_SPLITTING] and dl:
                if req_status == 'down' and (status not in [MirrorStatus.STATUS_SEEDING,
                                                            MirrorStatus.STATUS_UPLOADING,
                                                            MirrorStatus.STATUS_CLONING]):
                    return dl
                elif req_status == 'up' and status == MirrorStatus.STATUS_UPLOADING:
                    return dl
                elif req_status == 'clone' and status == MirrorStatus.STATUS_CLONING:
                    return dl
                elif req_status == 'seed' and status == MirrorStatus.STATUS_SEEDING:
                    return dl
                elif req_status == 'all':
                    return dl
    return None

FINISHED_PROGRESS_STR = "▓"
UNFINISHED_PROGRESS_STR = "░"
PROGRESS_MAX_SIZE = 100 // 8

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    cPart = p % 8 - 1
    p_str = FINISHED_PROGRESS_STR * cFull
    if cPart >=0:
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
    total, used, free, disk= disk_usage('/')
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
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
        msg = f"<b>═════════〣 ᴀʀᴋ ᴍɪʀʀᴏʀ 〣═════════</b>\n\n"
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
                    msg += f"\n<b>ᴇɴɢɪɴᴇ :</b><code>Aria2c</code>"
                except:
                    pass
                try:
                    msg += f"\n<b>sᴇᴇᴅᴇʀs :</b> {download.torrent_info().num_seeds}" \
                           f" | <b>ʟᴇᴇᴄʜᴇʀs :</b> {download.torrent_info().num_leechs}"
                    msg += f"\n<b>ᴇɴɢɪɴᴇ :</b><code>qBittorrent</code>"
                except:
                    pass
                try:
                    if download.status() == MirrorStatus.STATUS_UPLOADING:
                        msg += f"\n<b>ᴇɴɢɪɴᴇ :</b> <code>Google Api</code>"
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
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f"<b>CPU :</b> {cpu_percent()}% | <b>FREE :</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
        bmsg += f"\n<b>RAM :</b> {virtual_memory().percent}% | <b>UPTIME :</b> {get_readable_time(time.time() - botStartTime)}"
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
        bmsg += f"\n<b>DL:</b> {get_readable_file_size(dlspeed_bytes)}/s | <b>UL:</b> {get_readable_file_size(upspeed_bytes)}/s"
        
        buttons = ButtonMaker()
        buttons.sbutton("Statistics", str(THREE))
        sbutton = InlineKeyboardMarkup(buttons.build_menu(1))
        
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>Page:</b> {PAGE_NO}/{pages} | <b>Tasks:</b> {tasks}\n"
        try: 
            keyboard = [[InlineKeyboardButton(" REFRESH ", callback_data=str(ONE)),
                         InlineKeyboardButton(" CLOSE ", callback_data=str(TWO)),],
                        [InlineKeyboardButton(" STATISTICS ", callback_data=str(THREE)),]]
            editMessage(msg, status_reply_dict[chat_id], reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            LOGGER.error(str(e))
        status_reply_dict[chat_id].text = msg

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

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_unified_link(url: str):
    url1 = re_match(r'https?://(anidrive|driveroot|driveflix|indidrive|drivehub)\.in/\S+', url)
    url = re_match(r'https?://(appdrive|driveapp|driveace|gdflix|drivelinks|drivebit|drivesharer|drivepro)\.\S+', url)
    if bool(url1) == True:
        return bool(url1)
    elif bool(url) == True:
        return bool(url)
    else:
        return False

def is_udrive_link(url: str):
    if 'drivehub.ws' in url:
        return 'drivehub.ws' in url
    else:
        url = re_match(r'https?://(hubdrive|katdrive|kolop|drivefire|drivebuzz)\.\S+', url)
        return bool(url)
    
def is_sharer_link(url: str):
    url = re_match(r'https?://(sharer)\.pw/\S+', url)
    return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type

dispatcher.add_handler(CallbackQueryHandler(refresh, pattern='^' + str(ONE) + '$'))
dispatcher.add_handler(CallbackQueryHandler(close, pattern='^' + str(TWO) + '$'))
dispatcher.add_handler(CallbackQueryHandler(pop_up_stats, pattern='^' + str(THREE) + '$'))

