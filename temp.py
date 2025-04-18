#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, utils
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, MessageMediaPhoto, MessageMediaDocument, PeerChannel, InputPeerChannel
from telethon.tl.types import InputMediaPhoto, InputMediaDocument, InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.utils import get_peer_id
import tempfile
from telethon.tl.types import DocumentAttributeFilename
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, ReadHistoryRequest
import random
# 瀵煎叆浜虹被琛屼负妯℃嫙妯″潡
from human_simulator import simulate_join_behavior, simulate_human_browsing
import logging.handlers
import json
import time
from logging.handlers import TimedRotatingFileHandler
import random
import mimetypes

# 姣忔棩娑堟伅闄愰璁剧疆 (鏂板)
MAX_DAILY_MESSAGES = 100  # 姣忓ぉ鏈€澶氳浆鍙?0鏉℃秷鎭?daily_message_count = 0  # 褰撳墠鏃ユ湡宸茶浆鍙戞秷鎭鏁?last_count_reset_date = datetime.now().date()  # 涓婃閲嶇疆璁℃暟鐨勬棩鏈?
# 娑堟伅杞彂鍐峰嵈鏃堕棿璁剧疆锛堟柊澧烇級
COOLDOWN_MIN = 5  # 鏈€灏忓喎鍗存椂闂?COOLDOWN_MAX = 20  # 鏈€澶у喎鍗存椂闂?COOLDOWN_MINUTES = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)  # 鍒濆鍐峰嵈鏃堕棿
last_forward_time = None  # 涓婃杞彂娑堟伅鐨勬椂闂?processing_message = False  # 鍒濆鍖栧鐞嗕腑鏍囧織涓?False

# 姣忔鐢熸垚鏂扮殑鍐峰嵈鏃堕棿鐨勫嚱鏁?def get_random_cooldown():
    return random.randint(COOLDOWN_MIN, COOLDOWN_MAX)

# 妫€鏌ユ槸鍚﹀彲浠ュ彂閫佹洿澶氭秷鎭?(鏂板)
def can_send_more_messages():
    """妫€鏌ユ槸鍚﹀凡杈惧埌姣忔棩娑堟伅闄愰锛屽闇€瑕佸垯閲嶇疆璁℃暟鍣?""
    global daily_message_count, last_count_reset_date, last_forward_time
    
    # 妫€鏌ユ棩鏈熸槸鍚﹀彉鏇达紝濡傛灉鏄柊鐨勪竴澶╁垯閲嶇疆璁℃暟
    today = datetime.now().date()
    if today > last_count_reset_date:
        logger.info(f"鏂扮殑涓€澶╁紑濮嬶紝閲嶇疆娑堟伅璁℃暟銆備笂涓€澶╁叡鍙戦€?{daily_message_count} 鏉℃秷鎭?)
        daily_message_count = 0
        last_count_reset_date = today
    
    # 妫€鏌ユ槸鍚﹁秴杩囨瘡鏃ラ檺棰?    if daily_message_count >= MAX_DAILY_MESSAGES:
        logger.warning(f"宸茶揪鍒版瘡鏃ユ秷鎭檺棰?({MAX_DAILY_MESSAGES})锛屼粖澶╀笉鍐嶈浆鍙戞洿澶氭秷鎭?)
        return False
    
    # 妫€鏌ユ槸鍚﹀湪鍐峰嵈鏃堕棿鍐咃紙鏂板锛?    if last_forward_time is not None:
        cooldown_seconds = COOLDOWN_MINUTES * 60
        elapsed_seconds = (datetime.now() - last_forward_time).total_seconds()
        
        if elapsed_seconds < cooldown_seconds:
            remaining_minutes = (cooldown_seconds - elapsed_seconds) / 60
            logger.info(f"姝ｅ湪鍐峰嵈涓紝璺濈涓嬫鍙浆鍙戣繕鏈?{remaining_minutes:.1f} 鍒嗛挓")
            return False
        else:
            logger.info(f"鍐峰嵈鏃堕棿宸茶繃锛屽彲浠ョ户缁浆鍙戞秷鎭?)
    else:
        # 娣诲姞鏃ュ織浠ョ‘璁ゆ病鏈夊垵濮嬪喎鍗存椂闂?        logger.info("鍒濇鍚姩锛屾棤鍐峰嵈鏃堕棿闄愬埗")
    
    return True

# 澧炲姞娑堟伅璁℃暟 (鏂板)
def increment_message_count():
    """澧炲姞宸插彂閫佹秷鎭鏁板苟璁板綍鏃ュ織"""
    global daily_message_count, last_forward_time, COOLDOWN_MINUTES
    daily_message_count += 1
    last_forward_time = datetime.now()  # 鏇存柊鏈€鍚庤浆鍙戞椂闂?    
    # 姣忔杞彂鍚庨兘闅忔満鐢熸垚鏂扮殑鍐峰嵈鏃堕棿
    COOLDOWN_MINUTES = get_random_cooldown()
    
    remaining = MAX_DAILY_MESSAGES - daily_message_count
    logger.info(f"浠婃棩宸茶浆鍙?{daily_message_count}/{MAX_DAILY_MESSAGES} 鏉℃秷鎭紝鍓╀綑閰嶉: {remaining} 鏉?)
    logger.info(f"宸插惎鍔?{COOLDOWN_MINUTES} 鍒嗛挓鍐峰嵈鏃堕棿锛屼笅娆″彲杞彂鏃堕棿: {(last_forward_time + timedelta(minutes=COOLDOWN_MINUTES)).strftime('%H:%M:%S')}")
    
    # 濡傛灉杈惧埌闄愰锛屽彂閫侀€氱煡
    if daily_message_count == MAX_DAILY_MESSAGES:
        logger.warning(f"宸茶揪鍒颁粖鏃ヨ浆鍙戦檺棰?({MAX_DAILY_MESSAGES} 鏉?锛岀瓑寰呮槑澶╃户缁?)
    
    # 淇濆瓨娑堟伅璁℃暟
    save_message_count_data()

# 淇濆瓨娑堟伅璁℃暟鏁版嵁
def save_message_count_data():
    """淇濆瓨褰撳墠娑堟伅璁℃暟鍜屾棩鏈熷埌鏂囦欢"""
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'message_count.json')
    try:
        data = {
            'count': daily_message_count,
            'date': last_count_reset_date.isoformat()
        }
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        logger.debug(f"宸蹭繚瀛樻秷鎭鏁版暟鎹? {daily_message_count} 鏉?(鏃ユ湡: {last_count_reset_date})")
    except Exception as e:
        logger.error(f"淇濆瓨娑堟伅璁℃暟鏁版嵁澶辫触: {e}")

# 鍔犺浇娑堟伅璁℃暟鏁版嵁
def load_message_count_data():
    """浠庢枃浠跺姞杞芥秷鎭鏁板拰鏃ユ湡鏁版嵁"""
    global daily_message_count, last_count_reset_date
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'message_count.json')
    
    # 姣忔閲嶅惎鍚庨噸缃秷鎭鏁?    daily_message_count = 0
    last_count_reset_date = datetime.now().date()
    logger.info(f"绋嬪簭閲嶅惎鍚庨噸缃粖鏃ユ秷鎭鏁? {daily_message_count}/{MAX_DAILY_MESSAGES}")
    
    # 濡傛灉甯屾湜瀹屽叏绂佺敤鎸佷箙鍖栧彲浠ュ垹闄や笅闈㈣繖娈典唬鐮?    # 浣嗕繚鐣欐枃浠跺啓鍏ュ姛鑳界敤浜庤褰曞巻鍙诧紝鍗充娇鎴戜滑涓嶅啀璇诲彇瀹?    if os.path.exists(data_file):
        try:
            # 浠呯敤浜庢棩蹇楄褰曞巻鍙茶鏁?            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            saved_date = datetime.fromisoformat(data['date']).date()
            saved_count = data['count']
            logger.info(f"涓婃杩愯鐨勬秷鎭鏁颁负: {saved_count} (鏃ユ湡: {saved_date})锛屽凡蹇界暐骞堕噸缃负0")
        except Exception as e:
            logger.debug(f"璇诲彇鍘嗗彶璁℃暟鏂囦欢澶辫触: {e}")
    else:
        logger.info("鏈壘鍒版秷鎭鏁版暟鎹枃浠讹紝浣跨敤鍒濆鍊?")

# 鍒涘缓logs鐩綍锛堝鏋滀笉瀛樺湪锛?logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# 鍒涘缓涓€涓€掑簭鍐欏叆鏃ュ織鐨勫鐞嗗櫒
class ReverseFileHandler(logging.FileHandler):
    """鍊掑簭鍐欏叆鏃ュ織鐨勬枃浠跺鐞嗗櫒锛屾渶鏂扮殑鏃ュ織浼氬嚭鐜板湪鏂囦欢鐨勯《閮?""
    
    def __init__(self, filename, mode='a', encoding=None, delay=False, max_cache_records=100):
        """
        鍒濆鍖栧鐞嗗櫒
        filename: 鏃ュ織鏂囦欢璺緞
        max_cache_records: 鍐呭瓨涓紦瀛樼殑鏈€澶ф棩蹇楄褰曟暟锛岃揪鍒版鏁伴噺浼氬埛鏂板埌鏂囦欢
        """
        super().__init__(filename, mode, encoding, delay)
        self.max_cache_records = max_cache_records
        self.log_records = []  # 鐢ㄤ簬缂撳瓨鏃ュ織璁板綍
        
        # 濡傛灉鏂囦欢宸插瓨鍦紝鍏堣鍙栫幇鏈夊唴瀹?        self.existing_logs = []
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            try:
                with open(filename, 'r', encoding=encoding or 'utf-8') as f:
                    self.existing_logs = f.readlines()
            except Exception:
                self.existing_logs = []
    
    def emit(self, record):
        """閲嶅啓emit鏂规硶锛屽皢鏃ュ織璁板綍缂撳瓨璧锋潵"""
        try:
            msg = self.format(record)
            self.log_records.append(msg + self.terminator)
            
            # 褰撶紦瀛樼殑璁板綍杈惧埌鏈€澶ф暟閲忔椂锛屽啓鍏ユ枃浠?            if len(self.log_records) >= self.max_cache_records:
                self.flush()
        except Exception:
            self.handleError(record)
    
    def flush(self):
        """灏嗙紦瀛樼殑鏃ュ織鍐欏叆鏂囦欢锛屾柊鏃ュ織鍦ㄥ墠闈?""
        if self.log_records:
            try:
                # 鍦ㄦ枃浠舵ā寮忎负'w'鐨勬儏鍐典笅锛屽厛灏嗘柊鏃ュ織鍐欏叆鏂囦欢
                with open(self.baseFilename, 'w', encoding=self.encoding) as f:
                    # 鍐欏叆鏂扮殑鏃ュ織璁板綍锛堝€掑簭锛?                    for record in reversed(self.log_records):
                        f.write(record)
                    # 鍐欏叆鏃х殑鏃ュ織璁板綍
                    for line in self.existing_logs:
                        f.write(line)
                
                # 灏嗘柊鏃ュ織娣诲姞鍒扮幇鏈夋棩蹇楃殑鍓嶉潰
                self.existing_logs = self.log_records + self.existing_logs
                self.log_records = []
            except Exception as e:
                # 濡傛灉鍑洪敊锛岄€€鍥炲埌鏍囧噯鍐欏叆鏂瑰紡
                print(f"鍊掑簭鍐欏叆鏃ュ織澶辫触: {e}锛屼娇鐢ㄦ爣鍑嗘柟寮忓啓鍏?)
                with open(self.baseFilename, 'a', encoding=self.encoding) as f:
                    for record in self.log_records:
                        f.write(record)
                self.log_records = []
    
    def close(self):
        """鍏抽棴澶勭悊鍣ㄦ椂鍒锋柊鎵€鏈夋棩蹇?""
        self.flush()
        super().close()

# 閰嶇疆鏃ュ織
# 鍒涘缓涓€涓棩蹇楄褰曞櫒
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 娓呴櫎宸叉湁鐨勫鐞嗗櫒
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 鍒涘缓涓€涓懡浠よ澶勭悊鍣?console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_format)
logger.addHandler(console_handler)

# 鍒涘缓涓€涓寜澶╁懡鍚嶇殑鍊掑簭鏃ュ織鏂囦欢澶勭悊鍣?today_date = datetime.now().strftime("%Y-%m-%d")
log_file_path = os.path.join(logs_dir, f'telegram_forwarder_{today_date}.log')
file_handler = ReverseFileHandler(
    filename=log_file_path,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)
logger.addHandler(file_handler)

# 璁板綍绋嬪簭鍚姩娑堟伅
logger.info("=" * 50)
logger.info("楂樼骇杞彂鏈哄櫒浜哄惎鍔?- %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
logger.info("=" * 50)

# 鍔犺浇鐜鍙橀噺
load_dotenv()

# Telegram API鍑瘉
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

# 鐢ㄦ埛浼氳瘽锛堥娆¤繍琛屽悗浼氱敓鎴愶紝闇€淇濆瓨锛?SESSION = os.getenv('USER_SESSION', '')

# 棰戦亾淇℃伅
SOURCE_CHANNELS = os.getenv('SOURCE_CHANNELS', '').split(',')
DESTINATION_CHANNEL = os.getenv('DESTINATION_CHANNEL')

# 娑堟伅鏍煎紡閫夐」
INCLUDE_SOURCE = os.environ.get('INCLUDE_SOURCE', 'True').lower() in ['true', '1', 'yes', 'y']
ADD_FOOTER = os.environ.get('ADD_FOOTER', 'True').lower() in ['true', '1', 'yes', 'y']
FOOTER_TEXT = os.environ.get('FOOTER_TEXT', '').strip()
FORMAT_AS_HTML = os.environ.get('FORMAT_AS_HTML', 'False').lower() in ['true', '1', 'yes', 'y']

# 鏍囬杩囨护璁剧疆
TITLE_FILTER = os.getenv('TITLE_FILTER', '')  # 鏍囬杩囨护鍏抽敭璇嶏紝澶氫釜鐢ㄩ€楀彿鍒嗛殧锛屼负绌哄垯涓嶈繃婊?# 灏員ITLE_KEYWORDS璁剧疆涓烘彁渚涚殑鍏抽敭璇嶅垪琛?TITLE_KEYWORDS = [
    "https://t.me/", 
    "绉佽亰", 
    "棰戦亾", 
    "鍦板潃", 
    "浠锋牸", 
    "鏍囩", 
    "浣嶇疆", 
    "鍚嶅瓧", 
    "鍙屽悜鏈哄櫒浜?, 
    "鐢垫姤", 
    "鑹哄悕"
]

# 瀛樺偍濯掍綋缁勭殑瀛楀吀锛岄敭涓哄獟浣撶粍ID锛屽€间负璇ョ粍鐨勬秷鎭垪琛?media_groups = {}

# 瀛樺偍娑堟伅鏄犲皠鍏崇郴鐨勫瓧鍏革紝鐢ㄤ簬璺熻釜杞彂鐨勬秷鎭?# 閿负 "鍘熼閬揑D_鍘熸秷鎭疘D"锛屽€间负鐩爣棰戦亾涓殑娑堟伅ID
messages_map = {}

# 杞彂琛屼负璁剧疆
FORWARD_MEDIA_GROUPS = os.environ.get('FORWARD_MEDIA_GROUPS', 'True').lower() in ['true', '1', 'yes', 'y']
EDIT_FORWARDED_MESSAGES = os.environ.get('EDIT_FORWARDED_MESSAGES', 'True').lower() in ['true', '1', 'yes', 'y']

class HumanLikeSettings:
    # 妯℃嫙浜虹被鎿嶄綔鐨勯棿闅旀椂闂磋寖鍥达紙绉掞級
    JOIN_DELAY_MIN = 30  # 鍔犲叆棰戦亾鏈€灏忓欢杩?    JOIN_DELAY_MAX = 60  # 鍔犲叆棰戦亾鏈€澶у欢杩燂紝澧炲姞寤惰繜涓婇檺鏇存帴杩戜汉绫?    
    # 鏈夋椂浜虹被浼氭殏鍋滃緢闀挎椂闂达紝妯℃嫙涓婂帟鎵€銆佹帴鐢佃瘽绛?    LONG_BREAK_CHANCE = 0.25  # 25%鐨勫嚑鐜囦細鏈変竴涓暱鏃堕棿鏆傚仠
    LONG_BREAK_MIN = 60  # 闀挎殏鍋滄渶灏忔椂闂达紙绉掞級
    LONG_BREAK_MAX = 60  # 闀挎殏鍋滄渶澶ф椂闂达紙绉掞級
    
    # 妯℃嫙浜虹被娲昏穬鍜岄潪娲昏穬鏃堕棿娈?    ACTIVE_HOURS_START = 7  # 娲昏穬鏃堕棿寮€濮嬶紙24灏忔椂鍒讹級
    ACTIVE_HOURS_END = 23   # 娲昏穬鏃堕棿缁撴潫锛?4灏忔椂鍒讹級
    NIGHT_SLOWDOWN_FACTOR = 2.5  # 闈炴椿璺冩椂娈靛欢杩熷€嶇巼
    
    # 涓嶅悓绫诲瀷娑堟伅鐨勯槄璇绘椂闂达紝鏍规嵁鍐呭闀垮害璋冩暣
    TEXT_READ_SPEED = 0.03  # 姣忎釜瀛楃鐨勯槄璇绘椂闂达紙绉掞級
    TEXT_READ_BASE = 1.5    # 鍩虹闃呰鏃堕棿锛堢锛?    IMAGE_VIEW_MIN = 3.0    # 鏌ョ湅鍥剧墖鐨勬渶灏忔椂闂达紙绉掞級
    IMAGE_VIEW_MAX = 8.0    # 鏌ョ湅鍥剧墖鐨勬渶澶ф椂闂达紙绉掞級
    VIDEO_VIEW_FACTOR = 0.3 # 瑙嗛鎸佺画鏃堕棿鐨勮鐪嬫瘮渚嬶紙鐪嬩竴涓?0绉掕棰戝彲鑳戒細鑺?0绉掞級
    
    # 娑堟伅杞彂鐨勫欢杩?    FORWARD_DELAY_MIN = 3   # 娑堟伅杞彂鏈€灏忓欢杩?    FORWARD_DELAY_MAX = 15  # 娑堟伅杞彂鏈€澶у欢杩?    
    # 浜虹被鍋跺皵浼氫腑鏂搷浣滄垨鏀瑰彉娉ㄦ剰鍔?    ATTENTION_SHIFT_CHANCE = 0.15  # 15%鐨勫嚑鐜囦細鏆傛椂鍒嗗績
    ATTENTION_SHIFT_MIN = 10  # 鍒嗗績鐨勬渶灏忔椂闂达紙绉掞級
    ATTENTION_SHIFT_MAX = 40  # 鍒嗗績鐨勬渶澶ф椂闂达紙绉掞級
    
    # 杈撳叆鍜屼氦浜掔殑閫熷害鍙樺寲
    TYPING_SPEED_MIN = 0.05  # 鏈€蹇墦瀛楅€熷害锛堟瘡瀛楃绉掓暟锛?    TYPING_SPEED_MAX = 0.15  # 鏈€鎱㈡墦瀛楅€熷害锛堟瘡瀛楃绉掓暟锛?    
    # 涓嶅啀璺宠繃浠讳綍娑堟伅锛岀‘淇濆叏閮ㄨ浆鍙?    SKIP_MESSAGE_CHANCE = 0.0  # 璁剧疆涓?锛岀鐢ㄩ殢鏈鸿烦杩囧姛鑳?    
    # 鍦ㄨ浆鍙戝ぇ閲忓獟浣撴椂璁剧疆闅忔満闂撮殧
    MEDIA_BATCH_DELAY_MIN = 0.5
    MEDIA_BATCH_DELAY_MAX = 5.0
    
    # 鍛ㄦ湡鎬ф椿璺冨害鍙樺寲锛堟ā鎷熷伐浣滄棩/鍛ㄦ湯妯″紡锛?    WEEKEND_ACTIVITY_BOOST = 1.3  # 鍛ㄦ湯娲昏穬搴︽彁鍗?    MONDAY_ACTIVITY_DROP = 0.7    # 鍛ㄤ竴娲昏穬搴︿笅闄?    
    @staticmethod
    def calculate_reading_time(message_length, has_media=False, media_type=None):
        """鏍规嵁娑堟伅闀垮害鍜屽獟浣撶被鍨嬭绠楃湡瀹炵殑闃呰鏃堕棿"""
        # 鍩虹闃呰鏃堕棿
        base_time = HumanLikeSettings.TEXT_READ_BASE
        
        # 鏂囧瓧闃呰鏃堕棿锛堥殢鍐呭闀垮害澧炲姞锛?        if message_length > 0:
            text_time = message_length * HumanLikeSettings.TEXT_READ_SPEED
            base_time += text_time
        
        # 濯掍綋鏌ョ湅鏃堕棿
        if has_media:
            if media_type == 'photo':
                base_time += random.uniform(HumanLikeSettings.IMAGE_VIEW_MIN, HumanLikeSettings.IMAGE_VIEW_MAX)
            elif media_type == 'video':
                # 鍋囪瑙嗛闀垮害锛屾牴鎹ぇ灏忔垨瀹為檯闀垮害璋冩暣
                video_duration = random.randint(10, 60)  # 鍋囪10-60绉掔殑瑙嗛
                base_time += video_duration * HumanLikeSettings.VIDEO_VIEW_FACTOR
            else:
                base_time += random.uniform(2.0, 6.0)  # 鍏朵粬濯掍綋绫诲瀷
        
        # 鍔犲叆涓€鐐归殢鏈哄彉鍖?        randomness = random.uniform(0.8, 1.2)
        return base_time * randomness
    
    @staticmethod
    def should_take_break():
        """鍒ゆ柇鏄惁搴旇妯℃嫙浼戞伅"""
        return random.random() < HumanLikeSettings.LONG_BREAK_CHANCE
    
    @staticmethod
    def get_break_time():
        """鑾峰彇浼戞伅鏃堕棿闀垮害"""
        return random.uniform(HumanLikeSettings.LONG_BREAK_MIN, HumanLikeSettings.LONG_BREAK_MAX)
    
    @staticmethod
    def adjust_delay_for_time_of_day():
        """鏍规嵁涓€澶╀腑鐨勬椂闂磋皟鏁村欢杩?""
        current_hour = datetime.now().hour
        
        # 妫€鏌ユ槸鍚﹀湪娲昏穬鏃堕棿鑼冨洿鍐?        if HumanLikeSettings.ACTIVE_HOURS_START <= current_hour < HumanLikeSettings.ACTIVE_HOURS_END:
            return 1.0  # 娲昏穬鏃堕棿锛屾甯稿欢杩?        else:
            # 闈炴椿璺冩椂闂达紝澧炲姞寤惰繜
            return HumanLikeSettings.NIGHT_SLOWDOWN_FACTOR
    
    @staticmethod
    def adjust_delay_for_day_of_week():
        """鏍规嵁鏄熸湡鍑犺皟鏁存椿璺冨害"""
        day_of_week = datetime.now().weekday()  # 0=鍛ㄤ竴锛?=鍛ㄦ棩
        
        if day_of_week == 0:  # 鍛ㄤ竴
            return HumanLikeSettings.MONDAY_ACTIVITY_DROP
        elif day_of_week >= 5:  # 鍛ㄦ湯
            return HumanLikeSettings.WEEKEND_ACTIVITY_BOOST
        else:  # 鏅€氬伐浣滄棩
            return 1.0

# 杈呭姪鍑芥暟锛氫粠閾炬帴涓彁鍙栭個璇峰搱甯?def extract_invite_hash(link):
    """浠嶵elegram閭€璇烽摼鎺ヤ腑鎻愬彇鍝堝笇鍊?""
    logger.info(f"姝ｅ湪鎻愬彇閭€璇峰搱甯岋紝閾炬帴: {link}")
    
    # 澶勭悊t.me/+XXXX鏍煎紡鐨勯摼鎺?    if '/+' in link:
        hash_value = link.split('/+', 1)[1].strip()
        logger.info(f"浠?+鏍煎紡閾炬帴鎻愬彇鍝堝笇鍊? {hash_value}")
        return hash_value
    
    # 澶勭悊t.me/joinchat/XXXX鏍煎紡鐨勯摼鎺?    if '/joinchat/' in link:
        hash_value = link.split('/joinchat/', 1)[1].strip()
        logger.info(f"浠?joinchat/鏍煎紡閾炬帴鎻愬彇鍝堝笇鍊? {hash_value}")
        return hash_value
        
    # 澶勭悊https://t.me/c/XXXX鏍煎紡锛堢鏈夐閬撶洿鎺ラ摼鎺ワ級
    if '/c/' in link:
        try:
            parts = link.split('/c/', 1)[1].strip().split('/')
            if parts and parts[0].isdigit():
                channel_id = int(parts[0])
                logger.info(f"浠?c/鏍煎紡閾炬帴鎻愬彇棰戦亾ID: {channel_id}")
                return channel_id
        except Exception as e:
            logger.error(f"鎻愬彇/c/鏍煎紡閾炬帴ID澶辫触: {e}")
            pass
    
    logger.warning(f"鏃犳硶浠庨摼鎺ヤ腑鎻愬彇閭€璇峰搱甯? {link}")        
    return None

# 杈呭姪鍑芥暟锛氫粠閾炬帴涓彁鍙栭閬撶敤鎴峰悕
def extract_username(link):
    """浠嶵elegram閾炬帴涓彁鍙栭閬撶敤鎴峰悕"""
    # 绉婚櫎鍗忚閮ㄥ垎
    link = link.replace('https://', '').replace('http://', '')
    
    # 澶勭悊t.me/username鏍煎紡
    if 't.me/' in link and '/+' not in link and '/joinchat/' not in link and '/c/' not in link:
        username = link.split('t.me/', 1)[1].strip()
        # 绉婚櫎棰濆鐨勮矾寰勯儴鍒?        if '/' in username:
            username = username.split('/', 1)[0]
        return username
    
    return None

# 瀛樺偍宸插姞鍏ラ閬撶殑璁板綍鏂囦欢
def save_joined_channels(channel_links):
    """淇濆瓨宸插姞鍏ョ殑棰戦亾閾炬帴鍒版枃浠?""
    channels_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'joined_channels.json')
    try:
        # 纭繚鎵€鏈夐摼鎺ラ兘鏄瓧绗︿覆锛屽苟绉婚櫎鍙兘鐨勭┖椤?        channel_links = [ch for ch in channel_links if ch]
        
        # 鏍囧噯鍖栧鐞嗛摼鎺?        normalized_links = []
        for ch in channel_links:
            if isinstance(ch, str):
                normalized_links.append(ch.strip())
            else:
                # 濡傛灉涓嶆槸瀛楃涓诧紝杞崲涓哄瓧绗︿覆
                normalized_links.append(str(ch))
        
        # 绉婚櫎閲嶅椤?        normalized_links = list(set(normalized_links))
        
        with open(channels_file, 'w', encoding='utf-8') as f:
            json.dump(normalized_links, f, ensure_ascii=False, indent=2)
        logger.info(f"宸蹭繚瀛?{len(normalized_links)} 涓凡鍔犲叆棰戦亾鐨勮褰?)
        return True
    except Exception as e:
        logger.error(f"淇濆瓨宸插姞鍏ラ閬撹褰曞け璐? {e}")
        return False

def load_joined_channels():
    """浠庢枃浠跺姞杞藉凡鍔犲叆鐨勯閬撻摼鎺?""
    channels_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'joined_channels.json')
    if not os.path.exists(channels_file):
        logger.info("鏈壘鍒板凡鍔犲叆棰戦亾鐨勮褰曟枃浠讹紝灏嗗垱寤烘柊璁板綍")
        return []
    
    try:
        with open(channels_file, 'r', encoding='utf-8') as f:
            joined_channels = json.load(f)
        
        # 鏍囧噯鍖栭摼鎺ユ牸寮?        joined_channels = [ch.strip() for ch in joined_channels if ch and isinstance(ch, str)]
        
        # 绉婚櫎閲嶅椤?        joined_channels = list(set(joined_channels))
        
        logger.info(f"宸插姞杞?{len(joined_channels)} 涓凡鍔犲叆棰戦亾鐨勮褰?)
        return joined_channels
    except Exception as e:
        logger.error(f"鍔犺浇宸插姞鍏ラ閬撹褰曞け璐? {e}")
        return []

# 妫€鏌ユ秷鎭唴瀹规槸鍚﹀寘鍚叧閿瘝
def contains_keywords(text):
    """妫€鏌ユ枃鏈槸鍚﹀寘鍚叧閿瘝鍒楄〃涓殑浠讳綍涓€涓叧閿瘝锛屽寘鎷壒娈婃牸寮忓'鍏抽敭璇嶏細鍊?鐨勫尮閰?""
    if not text:
        return False
    
    # 棣栧厛杩涜鐩存帴鍖归厤
    for keyword in TITLE_KEYWORDS:
        if keyword in text:
            logger.info(f"鎵惧埌鍏抽敭璇嶅尮閰? '{keyword}'")
            return True
    
    # 鐒跺悗妫€鏌ョ壒娈婃牸寮忥紝濡?鍚嶅瓧锛歺xx"銆?浣嶇疆锛歺xx"绛?    special_formats = ["鍚嶅瓧", "浣嶇疆", "浠锋牸", "鏍囩", "棰戦亾", "绉佽亰", "鑹哄悕"]
    for format_word in special_formats:
        # 浣跨敤姝ｅ垯琛ㄨ揪寮忓尮閰?鍏抽敭璇嶏細鍊?鎴?鍏抽敭璇?"鏍煎紡
        pattern = f"{format_word}[锛?].+"
        if re.search(pattern, text):
            logger.info(f"鎵惧埌鐗规畩鏍煎紡鍖归厤: '{format_word}锛?")
            return True
    
    return False

# 鑾峰彇娑堟伅鐨勫畬鏁存枃鏈唴瀹癸紙鍖呮嫭鏂囨湰銆佹爣棰樺拰瀹炰綋锛?def get_full_message_text(message):
    """鑾峰彇娑堟伅鐨勬墍鏈夊彲鑳藉寘鍚枃鏈殑鍐呭"""
    all_text = []
    
    # 娣诲姞涓绘枃鏈?    if message.text:
        all_text.append(message.text)
    
    # 娣诲姞娑堟伅鏍囬锛坈aption锛?    if hasattr(message, 'caption') and message.caption:
        all_text.append(message.caption)
    
    # 濡傛灉娑堟伅鏈夊疄浣擄紙濡傛寜閽€侀摼鎺ョ瓑锛夛紝涔熸彁鍙栧叾涓殑鏂囨湰
    if hasattr(message, 'entities') and message.entities:
        for entity in message.entities:
            if hasattr(entity, 'text') and entity.text:
                all_text.append(entity.text)
    
    # 妫€鏌ユ秷鎭殑鍏朵粬鍙兘灞炴€?    for attr in ['message', 'raw_text', 'content']:
        if hasattr(message, attr) and getattr(message, attr):
            content = getattr(message, attr)
            if isinstance(content, str):
                all_text.append(content)
    
    # 灏嗘墍鏈夋枃鏈悎骞朵负涓€涓瓧绗︿覆
    return "\n".join(all_text)

async def main():
    # 鍒涘缓鐢ㄦ埛瀹㈡埛绔?    # 瀹夊叏澶勭悊SESSION瀛楃涓?    try:
        if SESSION and SESSION.strip():
            # 灏濊瘯浣跨敤宸叉湁浼氳瘽
            client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
            logger.info("浣跨敤宸叉湁浼氳瘽鐧诲綍...")
        else:
            # 鍒涘缓鏂颁細璇?            client = TelegramClient(StringSession(), API_ID, API_HASH)
            logger.info("棣栨杩愯锛岄渶瑕侀獙璇佺櫥褰?..")
            logger.info("璇锋寜鎻愮ず杈撳叆鎵嬫満鍙凤紙鍖呭惈鍥藉浠ｇ爜锛屽锛?86xxxxxxxxxx锛夊拰楠岃瘉鐮?)
            logger.info("濡傛灉鎮ㄧ殑璐︽埛寮€鍚簡涓ゆ楠岃瘉锛岃繕闇€瑕佽緭鍏ユ偍鐨勫瘑鐮?)
    except ValueError:
        # SESSION瀛楃涓叉棤鏁?        client = TelegramClient(StringSession(), API_ID, API_HASH)
        logger.info("浼氳瘽瀛楃涓叉棤鏁堬紝鍒涘缓鏂颁細璇?..")
    
    # 纭繚鍚姩鏃舵病鏈変换浣曞喎鍗撮檺鍒?    global last_forward_time, processing_message
    last_forward_time = None
    processing_message = False  # 鏄庣‘閲嶇疆澶勭悊鏍囧織
    logger.info(f"鍒濆鍖栬浆鍙戞椂闂翠负 None锛岀‘淇濆惎鍔ㄦ椂鏃犲喎鍗撮檺鍒?)
    
    # 灏濊瘯鍔犺浇娑堟伅璁℃暟鏁版嵁
    load_message_count_data()
    
    try:
        # 鍚姩瀹㈡埛绔紝鏄惧紡鎸囧畾鎵嬫満鍙疯緭鍏ユ柟寮?        await client.start(phone=lambda: input('璇疯緭鍏ユ墜鏈哄彿 (鏍煎紡: +86xxxxxxxxxx): '))
        logger.info("鐧诲綍鎴愬姛!")
        
        # 鐢熸垚浼氳瘽瀛楃涓?        session_string = client.session.save()
        
        # 濡傛灉鏄柊浼氳瘽鎴栦細璇濆凡鏇存敼锛屼繚瀛樺埌.env鏂囦欢
        if not SESSION or session_string != SESSION:
            logger.info("鐢熸垚鏂扮殑浼氳瘽瀛楃涓?..")
            
            # 鏇存柊.env鏂囦欢
            try:
                # 璇诲彇褰撳墠.env鏂囦欢鍐呭
                env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
                with open(env_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                
                # 鏇存柊USER_SESSION琛?                updated = False
                for i, line in enumerate(lines):
                    if line.strip().startswith('USER_SESSION='):
                        lines[i] = f'USER_SESSION={session_string}\n'
                        updated = True
                        break
                
                # 濡傛灉娌℃湁鎵惧埌USER_SESSION琛岋紝娣诲姞涓€琛?                if not updated:
                    lines.append(f'USER_SESSION={session_string}\n')
                
                # 鍐欏洖.env鏂囦欢
                with open(env_path, 'w', encoding='utf-8') as file:
                    file.writelines(lines)
                
                logger.info("SESSION宸蹭繚瀛樺埌.env鏂囦欢")
            except Exception as e:
                logger.error(f"淇濆瓨SESSION鍒?env鏂囦欢澶辫触: {e}")
                logger.info("璇锋墜鍔ㄥ皢浠ヤ笅SESSION瀛楃涓叉坊鍔犲埌.env鏂囦欢涓殑USER_SESSION鍙橀噺锛?)
                logger.info(session_string)
    except Exception as e:
        logger.error(f"鐧诲綍杩囩▼鍑洪敊: {e}")
        return
    
    # 鍔犺浇宸插姞鍏ョ殑棰戦亾璁板綍
    joined_channel_links = load_joined_channels()
    
    # 灏濊瘯鑷姩鍔犲叆婧愰閬?    logger.info("灏濊瘯鑷姩鍔犲叆閰嶇疆鐨勬簮棰戦亾...")
    join_results = []
    raw_source_channels = []  # 瀛樺偍婧愰閬撶殑ID鎴栧疄浣?    
    # 鍑嗗鎵€鏈夐渶瑕佸姞鍏ョ殑棰戦亾鍒楄〃
    channels_to_join = []
    for ch_id in SOURCE_CHANNELS:
        ch_id = ch_id.strip()
        if not ch_id:
            continue
        
        # 鏍囧噯鍖栧鐞嗛閬撻摼鎺ヨ繘琛屾瘮杈?        if 't.me/' in ch_id.lower() or 'telegram.me/' in ch_id.lower():
            # 纭繚閾炬帴浠ttps://寮€澶?            if not ch_id.startswith('http'):
                if ch_id.startswith('t.me/'):
                    ch_id = 'https://' + ch_id
                elif ch_id.startswith('telegram.me/'):
                    ch_id = 'https://' + ch_id
        
        # 妫€鏌ユ槸鍚﹀凡鏈夎褰?- 浣跨敤閮ㄥ垎鍖归厤鑰屼笉鏄畬鍏ㄥ尮閰?        is_in_joined_list = False
        for joined_ch in joined_channel_links:
            # 1. 鐩存帴鍖归厤
            if ch_id == joined_ch:
                is_in_joined_list = True
                break
                
            # 2. 濡傛灉閮芥槸閾炬帴锛屼絾鏍煎紡鐣ユ湁涓嶅悓
            if ('t.me/' in ch_id.lower() and 't.me/' in joined_ch.lower()):
                # 鎻愬彇t.me/鍚庨潰鐨勯儴鍒嗚繘琛屾瘮杈?                ch_suffix = ch_id.lower().split('t.me/', 1)[1]
                joined_suffix = joined_ch.lower().split('t.me/', 1)[1]
                if ch_suffix == joined_suffix:
                    is_in_joined_list = True
                    ch_id = joined_ch  # 浣跨敤宸茶褰曠殑鏍煎紡
                    break
        
        # 鏍规嵁鏄惁宸插姞鍏ュ喅瀹氫笅涓€姝?        if is_in_joined_list:
            logger.info(f"璺宠繃宸茶褰曞姞鍏ョ殑棰戦亾: {ch_id}")
            # 灏濊瘯鐩存帴鑾峰彇瀹炰綋
            try:
                # 鑾峰彇棰戦亾瀹炰綋
                entity = await client.get_entity(ch_id)
                raw_source_channels.append(entity.id)
                logger.info(f"宸蹭粠璁板綍涓仮澶嶉閬? 銆寋entity.title}銆?)
                join_results.append(f"鉁?宸蹭粠璁板綍涓仮澶? {entity.title}")
                continue
            except Exception as e:
                logger.warning(f"鏃犳硶浠庤褰曟仮澶嶉閬?{ch_id}: {e}")
                # 濡傛灉鏃犳硶鎭㈠锛屽垯娣诲姞鍒板緟鍔犲叆鍒楄〃
                
        channels_to_join.append(ch_id)
    
    # 鏄剧ず鍑嗗鍔犲叆鐨勯閬撴€绘暟
    logger.info(f"鍑嗗鍔犲叆 {len(channels_to_join)} 涓閬擄紝灏嗘ā鎷熶汉绫绘搷浣滈€熷害...")
    
    # 澶勭悊姣忎釜棰戦亾锛屾坊鍔犻殢鏈哄欢杩?    channels_processed = 0
    newly_joined_channel_links = []  # 鏂板姞鍏ョ殑棰戦亾閾炬帴
    
    for ch_id in channels_to_join:
        channels_processed += 1
        
        # 妯℃嫙浜虹被琛屼负锛氬湪鍔犲叆姣忎釜棰戦亾鍓嶅鍔犻殢鏈哄欢杩?        human_delay = random.uniform(HumanLikeSettings.JOIN_DELAY_MIN, HumanLikeSettings.JOIN_DELAY_MAX)
        logger.info(f"[{channels_processed}/{len(channels_to_join)}] 绛夊緟 {human_delay:.1f} 绉掑悗灏濊瘯鍔犲叆涓嬩竴涓閬?..")
        await asyncio.sleep(human_delay)
        
        # 闅忔満娣诲姞闀挎椂闂存殏鍋滐紝妯℃嫙浜虹被鍙兘浼氭殏鏃剁寮€
        if random.random() < HumanLikeSettings.LONG_BREAK_CHANCE and channels_processed < len(channels_to_join):
            long_break = random.uniform(HumanLikeSettings.LONG_BREAK_MIN, HumanLikeSettings.LONG_BREAK_MAX)
            logger.info(f"妯℃嫙浜虹被鏆傛椂绂诲紑锛屼紤鎭?{long_break:.1f} 绉?..")
            await asyncio.sleep(long_break)
        
        # 妫€鏌ユ槸鍚︽槸閾炬帴鏍煎紡
        is_link = ('t.me/' in ch_id.lower() or 'telegram.me/' in ch_id.lower())
        
        try:
            # 棣栧厛妫€鏌ユ槸鍚﹀凡鍔犲叆姝ら閬擄紝鏃犺閾炬帴鏍煎紡濡備綍
            # 瀵逛簬閾炬帴褰㈠紡锛屽皾璇曠洿鎺ヨ幏鍙栧疄浣?            try:
                test_entity = await client.get_entity(ch_id)
                if test_entity:
                    logger.info(f"妫€娴嬪埌宸茬粡鏄閬撴垚鍛橈紝鏃犻渶閲嶅鍔犲叆: {test_entity.title if hasattr(test_entity, 'title') else ch_id}")
                    join_results.append(f"鉁?宸叉槸棰戦亾鎴愬憳: {test_entity.title if hasattr(test_entity, 'title') else ch_id}")
                    raw_source_channels.append(test_entity.id if hasattr(test_entity, 'id') else test_entity)
                    newly_joined_channel_links.append(ch_id)
                    
                    # 瀵瑰凡鍔犲叆鐨勯閬撹繘琛岃交搴︽祻瑙堟ā鎷?                    logger.info("瀵瑰凡鍔犲叆棰戦亾杩涜绠€鍗曟祻瑙?..")
                    await simulate_human_browsing(client, test_entity, 'light')
                    continue  # 宸插姞鍏ワ紝璺宠繃鍚庣画鍔犲叆娴佺▼
            except Exception as e:
                # 鑾峰彇瀹炰綋澶辫触锛屽彲鑳芥槸鏈姞鍏ユ垨鍏朵粬鍘熷洜锛岀户缁皾璇曞姞鍏?                logger.info(f"棰戦亾 {ch_id} 鍙兘灏氭湭鍔犲叆锛屽皢灏濊瘯鍔犲叆: {e}")
            
            if is_link:
                logger.info(f"妫€娴嬪埌棰戦亾閾炬帴: {ch_id}")
                # 鏍规嵁閾炬帴绫诲瀷澶勭悊
                invite_hash = extract_invite_hash(ch_id)
                username = extract_username(ch_id)
                
                if invite_hash and not isinstance(invite_hash, int):
                    # 閫氳繃閭€璇烽摼鎺ュ姞鍏?                    logger.info(f"灏濊瘯閫氳繃閭€璇烽摼鎺ュ姞鍏? {ch_id}")
                    try:
                        # 妯℃嫙浜虹被琛屼负锛氬厛娴忚閭€璇烽〉闈紝鍐嶅姞鍏?                        await asyncio.sleep(random.uniform(1.5, 4.0))
                        
                        # 澧炲姞鏇村璋冭瘯鏃ュ織锛屾樉绀哄彂閫佺粰API鐨勭簿纭弬鏁?                        logger.info(f"鍚慣elegram API鍙戦€両mportChatInviteRequest锛屽搱甯屽€? '{invite_hash}'")
                        
                        # 瀵逛簬+寮€澶寸殑閾炬帴锛屽皾璇曚袱绉嶆柟寮?                        success = False
                        channel_entity = None
                        
                        # 鏂瑰紡涓€锛氱洿鎺ヤ娇鐢ㄦ彁鍙栫殑鍝堝笇鍊?                        try:
                            result = await client(functions.messages.ImportChatInviteRequest(
                                hash=invite_hash
                            ))
                            if result and result.chats:
                                success = True
                                channel_id = result.chats[0].id
                                channel_entity = result.chats[0]
                                logger.info(f"鎴愬姛閫氳繃閭€璇烽摼鎺ュ姞鍏? 銆寋result.chats[0].title}銆?)
                                join_results.append(f"鉁?宸查€氳繃閭€璇烽摼鎺ュ姞鍏? {result.chats[0].title}")
                                # 璁板綍鏂板姞鍏ョ殑棰戦亾閾炬帴
                                newly_joined_channel_links.append(ch_id)
                        except Exception as e1:
                            error_str = str(e1).lower()
                            logger.error(f"绗竴绉嶆柟寮忓姞鍏ュけ璐? {e1}")
                            
                            # 妫€鏌ユ槸鍚︽槸宸茬粡鏄垚鍛樼殑閿欒
                            if "already a participant" in error_str:
                                logger.info("鐢ㄦ埛宸叉槸棰戦亾鎴愬憳锛屾棤闇€閲嶅鍔犲叆")
                                success = True
                                # 鐩存帴閫氳繃閾炬帴鑾峰彇棰戦亾瀹炰綋
                                try:
                                    channel_entity = await client.get_entity(ch_id)
                                    channel_id = channel_entity.id
                                    logger.info(f"鎴愬姛鑾峰彇宸插姞鍏ラ閬撶殑瀹炰綋: 銆寋channel_entity.title}銆?)
                                    join_results.append(f"鉁?宸叉槸棰戦亾鎴愬憳: {channel_entity.title}")
                                    # 璁板綍棰戦亾閾炬帴
                                    newly_joined_channel_links.append(ch_id)
                                except Exception as e_entity:
                                    logger.error(f"鑾峰彇宸插姞鍏ラ閬撳疄浣撳け璐? {e_entity}")
                            # 澶勭悊宸叉垚鍔熺敵璇峰姞鍏ヤ絾闇€瑕佺鐞嗗憳鎵瑰噯鐨勬儏鍐?                            elif "successfully requested to join" in error_str:
                                logger.info(f"宸叉垚鍔熺敵璇峰姞鍏ラ閬擄紝绛夊緟绠＄悊鍛樻壒鍑? {ch_id}")
                                join_results.append(f"鈴?宸茬敵璇峰姞鍏ワ紝绛夊緟鎵瑰噯: {ch_id}")
                                # 灏濊瘯鑾峰彇棰戦亾鐨勫熀鏈俊鎭紙鍗充娇鏈寮忓姞鍏ワ級
                                try:
                                    # 浣跨敤getFullChat API灏濊瘯鑾峰彇鍩烘湰淇℃伅
                                    await asyncio.sleep(random.uniform(1.0, 2.0))
                                    # 鍦ㄨ繖閲屼笉灏嗘棰戦亾娣诲姞鍒皊ource_channels锛屽洜涓哄皻鏈寮忓姞鍏?                                    # 浣嗘垜浠褰曡繖涓摼鎺ワ紝浠ヤ究灏嗘潵鍙兘閲嶈瘯
                                    newly_joined_channel_links.append(ch_id)
                                    logger.info(f"宸茶褰曞緟鎵瑰噯鐨勯閬撻摼鎺? {ch_id}")
                                except Exception as e_info:
                                    logger.debug(f"鏃犳硶鑾峰彇寰呮壒鍑嗛閬撶殑淇℃伅: {e_info}")
                                
                                # 鍦ㄨ繖绉嶆儏鍐典笅鎴戜滑璁や负"鎴愬姛"鍙戦€佷簡璇锋眰锛屼絾涓嶈涓哄凡鎴愬姛鍔犲叆
                                success = False
                            # 濡傛灉閾炬帴鏍煎紡鏄?寮€澶翠笖灏氭湭鎴愬姛锛屽皾璇曠浜岀鏂瑰紡
                            elif not success and '/+' in ch_id:
                                try:
                                    # 鏂瑰紡浜岋細鐩存帴浣跨敤鍘熷閾炬帴
                                    logger.info(f"灏濊瘯浣跨敤绗簩绉嶆柟寮忓姞鍏? 浣跨敤瀹屾暣閾炬帴鐩存帴鑾峰彇瀹炰綋")
                                    channel_entity = await client.get_entity(ch_id)
                                    if channel_entity:
                                        success = True
                                        channel_id = channel_entity.id
                                        logger.info(f"閫氳繃绗簩绉嶆柟寮忔垚鍔熻幏鍙栭閬撳疄浣? 銆寋channel_entity.title}銆?)
                                        join_results.append(f"鉁?宸查€氳繃绗簩绉嶆柟寮忓姞鍏? {channel_entity.title}")
                                        # 璁板綍棰戦亾閾炬帴
                                        newly_joined_channel_links.append(ch_id)
                                except Exception as e2:
                                    logger.error(f"绗簩绉嶆柟寮忎篃澶辫触浜? {e2}")
                                    
                                    # 妫€鏌ユ槸鍚︽槸鍥犱负宸茬粡鍙戦€佷簡鍔犲叆璇锋眰
                                    if "successfully requested to join" in str(e2).lower():
                                        logger.info(f"绗簩绉嶆柟寮忕‘璁ゅ凡鐢宠鍔犲叆棰戦亾锛岀瓑寰呮壒鍑? {ch_id}")
                                        if not any(f"鈴?宸茬敵璇峰姞鍏ワ紝绛夊緟鎵瑰噯: {ch_id}" in r for r in join_results):
                                            join_results.append(f"鈴?宸茬敵璇峰姞鍏ワ紝绛夊緟鎵瑰噯: {ch_id}")
                                        newly_joined_channel_links.append(ch_id)
                        
                        # 濡傛灉鎴愬姛鑾峰彇鍒伴閬撳疄浣擄紝娣诲姞鍒版簮棰戦亾鍒楄〃骞舵ā鎷熸祻瑙堣涓?                        if success and channel_entity:
                            raw_source_channels.append(channel_id)
                            # 浣跨敤鏇寸湡瀹炵殑浜虹被娴忚琛屼负
                            logger.info("寮€濮嬫ā鎷熶汉绫绘祻瑙堣涓?..")
                            await simulate_join_behavior(client, channel_entity)
                        elif not success:
                            logger.warning(f"鍔犲叆棰戦亾澶辫触锛屾墍鏈夊皾璇曟柟寮忓潎鏈垚鍔? {ch_id}")
                            join_results.append(f"鉂?鍔犲叆澶辫触锛岃鎵嬪姩鍔犲叆: {ch_id}")
                    except Exception as e:
                        logger.error(f"閫氳繃閭€璇烽摼鎺ュ姞鍏ュけ璐? {ch_id}, 閿欒: {e}")
                        join_results.append(f"鉂?閫氳繃閭€璇烽摼鎺ュ姞鍏ュけ璐? {ch_id}")
                elif isinstance(invite_hash, int):
                    # 杩欐槸/c/鏍煎紡鐨勭鏈夐閬揑D
                    try:
                        # 灏濊瘯鑾峰彇瀹炰綋
                        channel_entity = await client.get_entity(invite_hash)
                        logger.info(f"鎵惧埌绉佹湁棰戦亾: {channel_entity.title if hasattr(channel_entity, 'title') else invite_hash}")
                        join_results.append(f"鉁?宸插姞鍏ョ鏈夐閬? {channel_entity.title if hasattr(channel_entity, 'title') else invite_hash}")
                        raw_source_channels.append(invite_hash)
                        # 璁板綍棰戦亾閾炬帴
                        newly_joined_channel_links.append(ch_id)
                    except Exception as e:
                        logger.error(f"鏃犳硶璁块棶绉佹湁棰戦亾ID: {invite_hash}, 閿欒: {e}")
                        join_results.append(f"鉂?鏃犳硶璁块棶绉佹湁棰戦亾: {ch_id}")
                elif username:
                    # 閫氳繃鐢ㄦ埛鍚嶅姞鍏ュ叕寮€棰戦亾
                    logger.info(f"灏濊瘯鍔犲叆鍏紑棰戦亾: @{username}")
                    try:
                        # 棣栧厛灏濊瘯鑾峰彇瀹炰綋
                        channel_entity = await client.get_entity(username)
                        
                        # 妫€鏌ユ槸鍚﹀凡鏄垚鍛?                        try:
                            # 灏濊瘯鑾峰彇鏈€杩戞秷鎭紝濡傛灉鑳借幏鍙栧垯璇存槑宸叉槸鎴愬憳
                            test_message = await client.get_messages(channel_entity, limit=1)
                            if test_message:
                                logger.info(f"妫€娴嬪埌宸叉槸棰戦亾 @{username} 鎴愬憳锛屾棤闇€閲嶅鍔犲叆")
                                join_results.append(f"鉁?宸叉槸棰戦亾鎴愬憳: {channel_entity.title}")
                                raw_source_channels.append(channel_entity.id)
                                newly_joined_channel_links.append(ch_id)
                                
                                # 瀵瑰凡鍔犲叆鐨勯閬撹繘琛岃交搴︽祻瑙堟ā鎷?                                logger.info("瀵瑰凡鍔犲叆棰戦亾杩涜绠€鍗曟祻瑙?..")
                                await simulate_human_browsing(client, channel_entity, 'light')
                                continue  # 璺宠繃鍔犲叆姝ラ
                        except Exception as e_test:
                            logger.info(f"鍙兘杩樻湭鍔犲叆棰戦亾 @{username}: {e_test}")
                        
                        # 妯℃嫙浜虹被琛屼负锛氬厛鏌ョ湅棰戦亾淇℃伅锛屽啀鍔犲叆
                        await asyncio.sleep(random.uniform(2.0, 5.0))
                        
                        # 鐒跺悗灏濊瘯鍔犲叆
                        result = await client(functions.channels.JoinChannelRequest(
                            channel=channel_entity
                        ))
                        if result and result.chats:
                            channel_id = result.chats[0].id
                            logger.info(f"鎴愬姛鍔犲叆鍏紑棰戦亾: {result.chats[0].title} (ID: {channel_id})")
                            join_results.append(f"鉁?宸插姞鍏ュ叕寮€棰戦亾: {result.chats[0].title}")
                            raw_source_channels.append(channel_id)
                            # 璁板綍棰戦亾閾炬帴
                            newly_joined_channel_links.append(ch_id)
                            
                            # 浣跨敤鏇寸湡瀹炵殑浜虹被娴忚琛屼负浠ｆ浛绠€鍗曞欢杩?                            logger.info("寮€濮嬫ā鎷熶汉绫绘祻瑙堣涓?..")
                            await simulate_join_behavior(client, channel_entity)
                        else:
                            logger.warning(f"鍔犲叆棰戦亾澶辫触锛岃繑鍥炵粨鏋滀腑娌℃湁棰戦亾淇℃伅: {username}")
                            join_results.append(f"鉂?鍔犲叆澶辫触锛屾棤娉曡幏鍙栭閬撲俊鎭? {username}")
                    except Exception as e:
                        # 妫€鏌ラ敊璇俊鎭槸鍚﹁〃鏄庡凡鏄垚鍛?                        if "ALREADY_PARTICIPANT" in str(e) or "already in the channel" in str(e).lower():
                            logger.info(f"鐢ㄦ埛宸叉槸棰戦亾 @{username} 鎴愬憳锛屾棤闇€閲嶅鍔犲叆")
                            join_results.append(f"鉁?宸叉槸棰戦亾鎴愬憳: @{username}")
                            try:
                                # 鐩存帴鑾峰彇瀹炰綋
                                channel_entity = await client.get_entity(username)
                                raw_source_channels.append(channel_entity.id)
                                newly_joined_channel_links.append(ch_id)
                                
                                # 瀵瑰凡鍔犲叆鐨勯閬撹繘琛岃交搴︽祻瑙堟ā鎷?                                logger.info("瀵瑰凡鍔犲叆棰戦亾杩涜绠€鍗曟祻瑙?..")
                                await simulate_human_browsing(client, channel_entity, 'light')
                            except Exception as e_get:
                                logger.error(f"鑾峰彇宸插姞鍏ラ閬撳疄浣撳け璐? {e_get}")
                        else:
                            logger.error(f"閫氳繃鐢ㄦ埛鍚嶅姞鍏ラ閬撳け璐? @{username}, 閿欒: {e}")
                            join_results.append(f"鉂?閫氳繃鐢ㄦ埛鍚嶅姞鍏ラ閬撳け璐? @{username}")
                else:
                    logger.warning(f"鏃犳硶瑙ｆ瀽棰戦亾閾炬帴: {ch_id}")
                    join_results.append(f"鉂?鏃犳硶瑙ｆ瀽棰戦亾閾炬帴: {ch_id}")
            else:
                # 灏濊瘯灏嗛閬揑D杞崲涓烘暣鏁?                channel_id = int(ch_id)
                
                try:
                    # 灏濊瘯鑾峰彇棰戦亾瀹炰綋锛屽鏋滃凡鍔犲叆鍒欒兘鎴愬姛鑾峰彇
                    channel_entity = await client.get_entity(channel_id)
                    logger.info(f"宸茬粡鍔犲叆棰戦亾: {channel_entity.title if hasattr(channel_entity, 'title') else channel_id}")
                    join_results.append(f"鉁?宸插姞鍏? {channel_entity.title if hasattr(channel_entity, 'title') else channel_id}")
                    raw_source_channels.append(channel_id)
                    # 璁板綍棰戦亾閾炬帴/ID
                    newly_joined_channel_links.append(ch_id)
                    
                    # 瀵瑰凡鍔犲叆鐨勯閬撹繘琛岃交搴︽祻瑙堟ā鎷?                    logger.info("瀵瑰凡鍔犲叆棰戦亾杩涜绠€鍗曟祻瑙?..")
                    await simulate_human_browsing(client, channel_entity, 'light')
                except:
                    # 濡傛灉鑾峰彇瀹炰綋澶辫触锛屽皾璇曠洿鎺ュ姞鍏?                    try:
                        # 妯℃嫙浜虹被琛屼负锛氬皾璇曞嚑娆℃墠鎵惧埌姝ｇ‘棰戦亾
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                        
                        # 鏂规硶1: 灏濊瘯鐩存帴浣跨敤ID鍔犲叆
                        result = await client(functions.channels.JoinChannelRequest(
                            channel=channel_id
                        ))
                        if result and result.chats:
                            logger.info(f"鎴愬姛鍔犲叆棰戦亾: {result.chats[0].title} (ID: {channel_id})")
                            join_results.append(f"鉁?宸插姞鍏? {result.chats[0].title}")
                            raw_source_channels.append(channel_id)
                            # 璁板綍棰戦亾閾炬帴/ID
                            newly_joined_channel_links.append(ch_id)
                            
                            # 浣跨敤鏇寸湡瀹炵殑浜虹被娴忚琛屼负
                            logger.info("寮€濮嬫ā鎷熶汉绫绘祻瑙堣涓?..")
                            await simulate_join_behavior(client, result.chats[0])
                        else:
                            logger.warning(f"鍔犲叆棰戦亾澶辫触锛岃繑鍥炵粨鏋滀腑娌℃湁棰戦亾淇℃伅: {channel_id}")
                            join_results.append(f"鉂?鍔犲叆棰戦亾 {channel_id} 澶辫触: 鏃犳硶鑾峰彇棰戦亾淇℃伅")
                    except Exception as e:
                        logger.error(f"閫氳繃ID鐩存帴鍔犲叆棰戦亾澶辫触 {channel_id}: {e}")
                        join_results.append(f"鉂?鏃犳硶鍔犲叆棰戦亾 {channel_id}: {str(e)}")
        except ValueError:
            logger.error(f"鏃犳晥鐨勯閬揑D鏍煎紡: {ch_id}")
            join_results.append(f"鉂?鏃犳晥鐨勯閬揑D鏍煎紡: {ch_id}")
            # 鍗充娇鏍煎紡閿欒锛屼篃娣诲姞涓€浜涘欢杩燂紝鏇村儚浜虹被杈撳叆閿欒鍚庣殑鎬濊€?            await asyncio.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            logger.error(f"澶勭悊棰戦亾鏃跺嚭閿?{ch_id}: {e}")
            join_results.append(f"鉂?澶勭悊棰戦亾鍑洪敊 {ch_id}: {str(e)}")
            # 澶勭悊閿欒鍚庢坊鍔犲欢杩?            await asyncio.sleep(random.uniform(1.0, 2.0))
    
    # 鏇存柊骞朵繚瀛樺凡鍔犲叆棰戦亾鐨勮褰?    if newly_joined_channel_links:
        # 鍚堝苟鏃ц褰曞拰鏂板姞鍏ョ殑棰戦亾锛屼娇鐢ㄩ泦鍚堝幓閲?        updated_channel_links = list(set(joined_channel_links + newly_joined_channel_links))
        # 淇濆瓨鏇存柊鍚庣殑璁板綍
        save_joined_channels(updated_channel_links)
        logger.info(f"宸叉洿鏂伴閬撹褰曟枃浠讹紝鍏?{len(updated_channel_links)} 涓閬撻摼鎺?)

    # 杈撳嚭鍔犲叆缁撴灉鎽樿
    logger.info("棰戦亾鍔犲叆缁撴灉鎽樿:")
    for result in join_results:
        logger.info(result)
    
    # 濡傛灉鏈夋棤娉曡嚜鍔ㄥ姞鍏ョ殑棰戦亾锛屾彁绀虹敤鎴锋墜鍔ㄥ姞鍏?    if any("鉂? in r for r in join_results):
        logger.warning("鏈変簺棰戦亾鏃犳硶鑷姩鍔犲叆锛岃鎵嬪姩鍔犲叆杩欎簺棰戦亾鍚庡啀杩愯绋嬪簭")
        logger.warning("鎵嬪姩鍔犲叆鏂规硶: 鍦═elegram瀹㈡埛绔腑浣跨敤鎼滅储鍔熻兘鎴栭個璇烽摼鎺ュ姞鍏ヨ繖浜涢閬?)
    
    # 澶勭悊婧愰閬揑D鍒楄〃锛屽苟纭繚鑾峰彇鍒板搴斿疄浣?    processed_source_channels = []
    logger.info(f"鍘熷SOURCE_CHANNELS闀垮害: {len(raw_source_channels)}")
    
    for ch_id in raw_source_channels:
        try:
            # 妫€鏌D鏍煎紡鏄惁闇€瑕佷慨姝?            if isinstance(ch_id, int) and str(ch_id).isdigit() and len(str(ch_id)) > 6 and not str(ch_id).startswith('-100'):
                # 鍙兘鏄己灏戜簡 -100 鍓嶇紑鐨勯閬揑D
                corrected_id = int(f"-100{ch_id}")
                logger.info(f"灏濊瘯淇棰戦亾ID鏍煎紡: {ch_id} -> {corrected_id}")
                try:
                    channel_entity = await client.get_entity(corrected_id)
                    channel_peer = get_peer_id(channel_entity)
                    processed_source_channels.append(channel_entity)
                    logger.info(f"浣跨敤淇鍚庣殑ID鏍煎紡鎴愬姛杩炴帴棰戦亾: 銆寋channel_entity.title}銆?)
                    continue
                except Exception as e:
                    # 淇鏍煎紡鍚庝粛鐒跺け璐ワ紝缁х画灏濊瘯鍘熷ID
                    logger.info(f"浣跨敤淇鍚庣殑ID鏍煎紡浠嶇劧澶辫触: {e}")
            
            # 灏濊瘯鑾峰彇棰戦亾瀹炰綋
            channel_entity = await client.get_entity(ch_id)
            channel_peer = get_peer_id(channel_entity)
            processed_source_channels.append(channel_entity)
            logger.info(f"鎴愬姛瑙ｆ瀽棰戦亾: 銆寋channel_entity.title}銆?)
        except ValueError:
            logger.warning(f"鏃犳晥鐨勯閬揑D鏍煎紡: {ch_id} - 灏嗗皾璇曚綔涓哄師濮婭D浣跨敤")
            processed_source_channels.append(ch_id)
            logger.info(f"灏嗕娇鐢ㄥ師濮婭D: {ch_id}锛屼絾鍙兘鏃犳硶鎺ユ敹娑堟伅")
        except Exception as e:
            # 鍑忓皯鍐楅暱鐨勯敊璇秷鎭紝浣跨敤鏇寸畝娲佺殑鎻愮ず
            logger.warning(f"鏃犳硶鑾峰彇棰戦亾 {ch_id} 鐨勮缁嗕俊鎭? {e}")
            logger.info(f"灏嗕娇鐢ㄥ師濮婭D: {ch_id} 缁х画灏濊瘯锛岃嫢鏃犳硶鎺ユ敹娑堟伅璇锋鏌D鏍煎紡鎴栭閬撴潈闄?)
            
            # 灏界鍑洪敊锛屼粛鐒跺皾璇曟坊鍔犲師濮婭D
            processed_source_channels.append(ch_id)
    
    if not processed_source_channels:
        logger.error("娌℃湁鍙敤鐨勬簮棰戦亾锛岀▼搴忓皢閫€鍑?)
        return
    
    # 鑾峰彇鐩爣棰戦亾瀹炰綋
    try:
        # 鐩存帴浣跨敤閰嶇疆鐨勯閬揑D
        dest_id = int(DESTINATION_CHANNEL)
        logger.info(f"灏濊瘯杩炴帴鐩爣棰戦亾: {dest_id}")
        destination_channel = await client.get_entity(dest_id)
        logger.info(f"宸茶繛鎺ュ埌鐩爣棰戦亾: 銆寋destination_channel.title if hasattr(destination_channel, 'title') else destination_channel.id}銆?)
        
        # 鍙戦€佹祴璇曟秷鎭互楠岃瘉杩炴帴
        try:
            test_msg = await client.send_message(destination_channel, "鉁?杞彂鏈哄櫒浜哄凡鍚姩锛屾鍦ㄧ洃鎺ф簮棰戦亾...")
            logger.info("宸插彂閫佹祴璇曟秷鎭埌鐩爣棰戦亾锛岃繛鎺ユ甯?)
        except Exception as e:
            logger.error(f"鍙戦€佹祴璇曟秷鎭け璐ワ紝鍙兘娌℃湁鍙戦€佹秷鎭潈闄? {e}")
    except Exception as e:
        logger.error(f"鏃犳硶鑾峰彇鐩爣棰戦亾: {e}")
        logger.error("璇风‘淇?")
        logger.error("1. 鎮ㄥ凡缁忎娇鐢ㄥ綋鍓嶈处鍙峰姞鍏ヤ簡璇ラ閬?)
        logger.error("2. 棰戦亾ID姝ｇ‘")
        logger.error("3. 鎮ㄦ湁鏉冮檺鍦ㄨ棰戦亾鍙戦€佹秷鎭?)
        return

    # 鏄剧ず鐩戞帶鐨勯閬撳垪琛?    logger.info("=== 寮€濮嬬洃鎺т互涓嬮閬?===")
    channel_count = 0
    for channel in processed_source_channels:
        channel_count += 1
        try:
            if hasattr(channel, 'title'):
                logger.info(f"{channel_count}. 銆寋channel.title}銆?)
            else:
                logger.info(f"{channel_count}. ID: {channel}")
        except:
            logger.info(f"{channel_count}. 鏈煡棰戦亾")
    logger.info("========================")
    
    # 娣诲姞涓€涓鐞嗕腑鐨勬爣蹇楀彉閲?    processing_message = False

    # 娉ㄥ唽娑堟伅澶勭悊鍣?    @client.on(events.NewMessage(chats=processed_source_channels))
    async def forward_messages(event):
        try:
            global processing_message, last_forward_time
            
            # 鎵撳嵃璋冭瘯淇℃伅锛岀湅鐪?processing_message 鐨勫€?            logger.info(f"澶勭悊鏂版秷鎭紝褰撳墠澶勭悊鐘舵€? {'姝ｅ湪澶勭悊涓? if processing_message else '绌洪棽'}")
            
            # 濡傛灉宸茬粡鍦ㄥ鐞嗘秷鎭紝鍒欒烦杩囧綋鍓嶆秷鎭?            if processing_message:
                logger.info(f"宸叉湁娑堟伅姝ｅ湪澶勭悊涓紝璺宠繃姝ゆ秷鎭?(ID: {event.message.id})")
                return
                
            # 鏍囪涓烘鍦ㄥ鐞嗘秷鎭?            processing_message = True
                
            # 鑾峰彇棰戦亾鍚嶇О鑰岄潪浠呮樉绀篒D
            source_chat = await event.get_chat()
            chat_name = getattr(source_chat, 'title', f'鏈煡棰戦亾 {event.chat_id}')
            
            # 澧炲姞鏇磋缁嗙殑鏃ュ織锛屾樉绀洪閬撳悕绉?            logger.info(f"鏀跺埌鏉ヨ嚜棰戦亾銆寋chat_name}銆嶇殑鏂版秷鎭? {event.message.id}")
            
            # 鑾峰彇娑堟伅鍐呭
            message = event.message
            
            # 纭畾娑堟伅绫诲瀷锛岀敤浜庤绠楁洿鐪熷疄鐨勯槄璇绘椂闂?            message_type = None
            has_media = False
            
            if isinstance(message.media, MessageMediaPhoto):
                message_type = 'photo'
                has_media = True
            elif isinstance(message.media, MessageMediaDocument):
                if hasattr(message.media.document, 'mime_type'):
                    if 'video' in message.media.document.mime_type:
                        message_type = 'video'
                    elif 'audio' in message.media.document.mime_type:
                        message_type = 'audio'
                    else:
                        message_type = 'document'
                has_media = True
            
            # 璺宠繃绾枃鏈秷鎭?            if not has_media:
                logger.info(f"璺宠繃绾枃鏈秷鎭?(ID: {message.id}) - 鏍规嵁璁剧疆鍙浆鍙戝寘鍚獟浣撶殑娑堟伅")
                processing_message = False
                return
            
            # 鑾峰彇瀹屾暣鐨勬秷鎭枃鏈唴瀹?            full_message_text = get_full_message_text(message)
            logger.info(f"娑堟伅 (ID: {message.id}) 瀹屾暣鏂囨湰鍐呭: {full_message_text}")
            
            # 妫€鏌ユ秷鎭枃鏈槸鍚﹀寘鍚叧閿瘝
            if not contains_keywords(full_message_text):
                logger.info(f"璺宠繃娑堟伅 (ID: {message.id}) - 涓嶅寘鍚换浣曟寚瀹氬叧閿瘝锛屽叧閿瘝鍒楄〃: {TITLE_KEYWORDS}")
                processing_message = False
                return
            
            # 妫€鏌ユ瘡鏃ユ秷鎭檺棰?            global daily_message_count
            if daily_message_count >= MAX_DAILY_MESSAGES:
                logger.info(f"璺宠繃娑堟伅 (ID: {message.id}) - 宸茶揪鍒版瘡鏃ヨ浆鍙戦檺棰?({MAX_DAILY_MESSAGES})")
                processing_message = False
                return
                
            logger.info(f"娑堟伅 (ID: {message.id}) 鍖呭惈濯掍綋涓旀枃鏈寘鍚叧閿瘝锛屽皢杩涜杞彂")
            
            # 妫€鏌ュ喎鍗存椂闂?- 閬垮厤鍒濇鍚姩鏃朵篃鏈夊喎鍗?            if last_forward_time:
                current_time = datetime.now()
                time_since_last_forward = (current_time - last_forward_time).total_seconds() / 60
                if time_since_last_forward < COOLDOWN_MINUTES:
                    remaining_minutes = COOLDOWN_MINUTES - time_since_last_forward
                    logger.info(f"鍐峰嵈鏃堕棿鏈埌锛岃繕闇€绛夊緟 {remaining_minutes:.1f} 鍒嗛挓鍚庢墠鑳借浆鍙戞娑堟伅")
                    logger.info(f"娑堟伅 (ID: {message.id}) 灏嗗湪 {remaining_minutes:.1f} 鍒嗛挓鍚庡皾璇曡浆鍙?)
                    await asyncio.sleep(remaining_minutes * 60)  # 绛夊緟鍓╀綑鍐峰嵈鏃堕棿
                    
                    # 鍐嶆妫€鏌ユ槸鍚﹀彲浠ュ彂閫佹秷鎭紙鍙兘鍦ㄧ瓑寰呮湡闂磋揪鍒颁簡姣忔棩闄愰锛?                    if daily_message_count >= MAX_DAILY_MESSAGES:
                        logger.info(f"绛夊緟鍐峰嵈鏃堕棿鍚庢鏌ワ細璺宠繃娑堟伅 (ID: {message.id}) - 宸茶揪鍒版瘡鏃ヨ浆鍙戦檺棰?({MAX_DAILY_MESSAGES})")
                        processing_message = False
                        return
            else:
                logger.info("棣栨杞彂娑堟伅锛屾棤闇€绛夊緟鍐峰嵈鏃堕棿")
            
            # 璁＄畻鐪熷疄鐨勯槄璇诲欢杩燂紙鍩轰簬娑堟伅闀垮害鍜岀被鍨嬶級
            text_length = len(message.text) if message.text else 0
            reading_time = HumanLikeSettings.calculate_reading_time(text_length, has_media, message_type)
            
            # 搴旂敤鏃堕棿娈靛拰鏄熸湡鍥犵礌璋冩暣
            time_factor = HumanLikeSettings.adjust_delay_for_time_of_day()
            day_factor = HumanLikeSettings.adjust_delay_for_day_of_week()
            
            # 鏈€缁堥槄璇绘椂闂达紝缁撳悎涓€澶╀腑鐨勬椂闂村拰鏄熸湡鍑?            final_reading_time = reading_time * time_factor * day_factor
            
            # 闅忔満鍐冲畾鏄惁娣诲姞"鍒嗗績"寤惰繜
            if random.random() < HumanLikeSettings.ATTENTION_SHIFT_CHANCE:
                distraction_time = random.uniform(HumanLikeSettings.ATTENTION_SHIFT_MIN, HumanLikeSettings.ATTENTION_SHIFT_MAX)
                logger.info(f"妯℃嫙浜虹被鍒嗗績琛屼负锛屾殏鍋?{distraction_time:.1f} 绉?)
                final_reading_time += distraction_time
            
            logger.info(f"鏍规嵁娑堟伅绫诲瀷鍜岄暱搴︼紝妯℃嫙鐪熷疄闃呰寤惰繜: {final_reading_time:.1f}绉?)
            await asyncio.sleep(final_reading_time)
            
            # 妯℃嫙"鎵撳瓧"鍜屽鐞嗘椂闂?- 瀵逛簬杈冮暱娑堟伅锛屾坊鍔犻澶栧鐞嗘椂闂?            if text_length > 50 and has_media:
                typing_time = random.uniform(1.5, 4.0)
                logger.info(f"妯℃嫙杞彂鍓嶇殑鎬濊€?澶勭悊鏃堕棿: {typing_time:.1f}绉?)
                await asyncio.sleep(typing_time)
            
            # 璁板綍娑堟伅锛屽彲鑳介渶瑕佺敤浜庡悗缁紪杈戞洿鏂?            message_key = f"{event.chat_id}_{event.message.id}"
            
            # 鑾峰彇鏉ユ簮淇℃伅
            source_info = f"\n\n鏉ユ簮: {source_chat.title}" if INCLUDE_SOURCE and hasattr(source_chat, 'title') else ""
            
            # 鑾峰彇椤佃剼
            footer = f"\n\n{FOOTER_TEXT}" if ADD_FOOTER else ""
            
            # 涓嶅啀浣跨敤鐩存帴杞彂鏂瑰紡锛屽洜涓轰細鏄剧ず"Forwarded from"鏍囪
            # 鏀逛负鏍规嵁娑堟伅绫诲瀷閲嶆柊鍒涘缓娑堟伅
            
            # 妫€鏌ユ槸鍚︿负濯掍綋缁勭殑涓€閮ㄥ垎
            if message.grouped_id:
                logger.info(f"妫€娴嬪埌濯掍綋缁勬秷鎭紝缁処D: {message.grouped_id}")
                await handle_media_group(client, message, source_info, footer, destination_channel)
            else:
                # 澶勭悊濯掍綋娑堟伅
                logger.info(f"澶勭悊鏉ヨ嚜銆寋chat_name}銆嶇殑濯掍綋娑堟伅")
                caption = message.text if message.text else ""
                caption = caption + source_info + footer
                
                # 妯℃嫙涓婁紶鍑嗗鏃堕棿
                upload_prep_time = random.uniform(0.5, 2.0)
                logger.info(f"妯℃嫙濯掍綋涓婁紶鍑嗗鏃堕棿: {upload_prep_time:.1f}绉?)
                await asyncio.sleep(upload_prep_time)
                
                # 閲嶆柊鍙戦€佸獟浣擄紙涓嶆槸杞彂锛?                try:
                    sent_message = await client.send_file(
                        destination_channel,
                        message.media,
                        caption=caption,
                        parse_mode='html' if FORMAT_AS_HTML else None
                    )
                    logger.info(f"宸茶浆鍙戝獟浣撴秷鎭?(ID: {message.id}) 鍒扮洰鏍囬閬擄紝鏂版秷鎭疘D: {sent_message.id}")
                    
                    # 璁板綍娑堟伅鏄犲皠
                    messages_map[message_key] = sent_message.id
                    
                    # 澧炲姞娑堟伅璁℃暟骞舵洿鏂版渶鍚庤浆鍙戞椂闂?                    last_forward_time = datetime.now()  # 鏇存柊鏈€鍚庤浆鍙戞椂闂?                    increment_message_count()
                    
                    # 璁＄畻涓嬫鍙浆鍙戞椂闂?                    next_forward_time = last_forward_time + timedelta(minutes=COOLDOWN_MINUTES)
                    logger.info(f"涓嬫鍙浆鍙戞椂闂? {next_forward_time.strftime('%H:%M:%S')}")
                except Exception as e:
                    logger.error(f"杞彂濯掍綋娑堟伅 {message.id} 澶辫触: {e}")
            # 杞彂鎴愬姛鍚庢坊鍔犲皬寤惰繜锛屾ā鎷熶汉绫昏涓?            delay_after_send = random.uniform(0.8, 2.5)
            logger.info(f"娑堟伅澶勭悊瀹屾垚锛岀瓑寰?{delay_after_send:.1f} 绉?..")
            await asyncio.sleep(delay_after_send)
            
            # 澶勭悊瀹屾垚鍚庯紝灏嗘爣蹇楃疆涓?False
            processing_message = False
        except Exception as e:
            logger.error(f"澶勭悊娑堟伅鏃跺嚭閿? {e}")
            # 纭繚鍦ㄥ鐞嗗嚭閿欐椂涔熼噸缃爣蹇?            processing_message = False
    
    # 娉ㄥ唽缂栬緫娑堟伅澶勭悊鍣?    @client.on(events.MessageEdited(chats=processed_source_channels))
    async def forward_edited_messages(event):
        global processing_message, last_forward_time
        
        try:
            # 濡傛灉宸茬粡鍦ㄥ鐞嗘秷鎭紝鍒欒烦杩囧綋鍓嶆秷鎭?            if processing_message:
                logger.info(f"宸叉湁娑堟伅姝ｅ湪澶勭悊涓紝璺宠繃姝ょ紪杈戞秷鎭?(ID: {event.message.id})")
                return
                
            # 鏍囪涓烘鍦ㄥ鐞嗘秷鎭?            processing_message = True
            
            # 鑾峰彇娑堟伅ID
            message = event.message
            message_key = f"{event.chat_id}_{message.id}"
            
            # 鑾峰彇棰戦亾鍚嶇О
            source_chat = await event.get_chat()
            chat_name = getattr(source_chat, 'title', f'鏈煡棰戦亾 {event.chat_id}')
            
            # 妫€鏌ユ秷鎭槸鍚﹀寘鍚獟浣?            has_media = False
            if message.media:
                if isinstance(message.media, MessageMediaPhoto):
                    has_media = True
                    message_type = 'photo'
                elif isinstance(message.media, MessageMediaDocument):
                    has_media = True
                    if hasattr(message.media.document, 'mime_type'):
                        if 'video' in message.media.document.mime_type:
                            message_type = 'video'
                        elif 'audio' in message.media.document.mime_type:
                            message_type = 'audio'
                        else:
                            message_type = 'document'
            
            # 璺宠繃绾枃鏈秷鎭?            if not has_media:
                logger.info(f"璺宠繃缂栬緫鐨勭函鏂囨湰娑堟伅 (ID: {message.id}) - 鏍规嵁璁剧疆鍙浆鍙戝寘鍚獟浣撶殑娑堟伅")
                return
            
            # 鑾峰彇瀹屾暣鐨勬秷鎭枃鏈唴瀹?            full_message_text = get_full_message_text(message)
            logger.info(f"缂栬緫娑堟伅 (ID: {message.id}) 瀹屾暣鏂囨湰鍐呭: {full_message_text[:100]}...")
            
            # 妫€鏌ユ秷鎭枃鏈槸鍚﹀寘鍚叧閿瘝
            if not contains_keywords(full_message_text):
                logger.info(f"璺宠繃缂栬緫鐨勬秷鎭?(ID: {message.id}) - 涓嶅寘鍚换浣曟寚瀹氬叧閿瘝")
                return
            
            # 妫€鏌ユ瘡鏃ユ秷鎭檺棰?(鏂板)
            if not can_send_more_messages():
                logger.info(f"璺宠繃缂栬緫鐨勬秷鎭?(ID: {message.id}) - 宸茶揪鍒版瘡鏃ヨ浆鍙戦檺棰?({MAX_DAILY_MESSAGES})")
                return
                
            logger.info(f"缂栬緫鐨勬秷鎭?(ID: {message.id}) 鍖呭惈濯掍綋涓旀枃鏈寘鍚叧閿瘝锛屽皢杩涜杞彂")
            
            # 妫€鏌ユ槸鍚︿箣鍓嶅凡杞彂
            if message_key not in messages_map:
                logger.info(f"浠庛€寋chat_name}銆嶆帴鏀跺埌缂栬緫鐨勬秷鎭紝浣嗘湭鎵惧埌鍘熷杞彂璁板綍锛屽皢浣滀负鏂版秷鎭鐞?)
                # 杞彂涓烘柊娑堟伅
                await forward_messages(event)
                return
                
            # 鎵惧埌瀵瑰簲鐨勭洰鏍囨秷鎭疘D
            dest_message_id = messages_map[message_key]
            logger.info(f"浠庛€寋chat_name}銆嶆帴鏀跺埌缂栬緫鐨勬秷鎭?(ID: {message.id})锛屽搴旂洰鏍囨秷鎭疘D: {dest_message_id}")
            
            # 鑾峰彇鏉ユ簮淇℃伅
            source_info = f"\n\n鏉ユ簮: {source_chat.title}" if INCLUDE_SOURCE and hasattr(source_chat, 'title') else ""
            
            # 鑾峰彇椤佃剼
            footer = f"\n\n{FOOTER_TEXT}" if ADD_FOOTER else ""
            
            # 鑾峰彇娑堟伅鍐呭
            message_content = message.text if message.text else ""
            
            # 鍒涘缓鏂版秷鎭?            new_message = message_content + source_info + footer
            
            # 鍙戦€佸寘鍚師濮嬪獟浣撶殑缂栬緫娑堟伅
            try:
                await client.send_file(
                    destination_channel,
                    message.media,
                    caption=new_message,
                    parse_mode='html' if FORMAT_AS_HTML else None
                )
                logger.info(f"宸茶浆鍙戠紪杈戠殑濯掍綋娑堟伅 (ID: {message.id}) 鍒扮洰鏍囬閬?)
                
                # 澧炲姞娑堟伅璁℃暟 (鏂板)
                increment_message_count()
            except Exception as e:
                logger.error(f"杞彂缂栬緫鐨勫獟浣撴秷鎭け璐? {e}")
                
                # 灏濊瘯鍙戦€佹枃鏈鏄?                try:
                    await client.send_message(
                        destination_channel,
                        f"鈿狅笍 娑堟伅宸叉洿鏂帮紝浣嗗獟浣撴棤娉曡浆鍙?\n\n{new_message}",
                        parse_mode='html' if FORMAT_AS_HTML else None
                    )
                    logger.info(f"宸插彂閫佹秷鎭紪杈戦€氱煡")
                except Exception as e2:
                    logger.error(f"鍙戦€佺紪杈戦€氱煡涔熷け璐? {e2}")
        except Exception as e:
            logger.error(f"澶勭悊缂栬緫娑堟伅鏃跺嚭閿? {e}")
    
    # 鍚姩閫氱煡
    logger.info("楂樼骇杞彂鏈哄櫒浜哄凡鍚姩锛屾鍦ㄧ洃鎺ч閬?..")
    logger.info(f"鐩戞帶鐨勯閬? {processed_source_channels}")
    logger.info(f"鐩爣棰戦亾: {DESTINATION_CHANNEL}")
    logger.info(f"姣忔棩娑堟伅閰嶉: {MAX_DAILY_MESSAGES}鏉★紝浠婃棩宸插彂閫? {daily_message_count}鏉★紝鍓╀綑: {MAX_DAILY_MESSAGES - daily_message_count}鏉?)
    
    try:
        # 淇濇寔鏈哄櫒浜鸿繍琛?        await client.run_until_disconnected()
    finally:
        # 纭繚鍦ㄩ€€鍑烘椂淇濆瓨娑堟伅璁℃暟
        logger.info("淇濆瓨娑堟伅璁℃暟鏁版嵁骞堕€€鍑?..")
        save_message_count_data()

async def handle_media_group(client, message, source_info, footer, destination_channel):
    """澶勭悊濯掍綋缁勬秷鎭紙澶氬紶鍥剧墖/瑙嗛锛?""
    group_id = str(message.grouped_id)
    message_key = f"{message.chat_id}_{message.id}"
    
    # 鑾峰彇棰戦亾鍚嶇О
    chat = await client.get_entity(message.chat_id)
    chat_name = getattr(chat, 'title', f'鏈煡棰戦亾 {message.chat_id}')
    
    # 鏃ュ織璁板綍妫€娴嬪埌鐨勫獟浣撶粍
    logger.info(f"妫€娴嬪埌鏉ヨ嚜銆寋chat_name}銆嶇殑濯掍綋缁勬秷鎭紝缁処D: {group_id}")
    
    # 涓烘瘡涓獟浣撶粍ID鍒涘缓涓€涓垪琛?    if group_id not in media_groups:
        media_groups[group_id] = {
            'messages': [],
            'source_info': source_info,
            'footer': footer,
            'destination': destination_channel,
            'processing': False,
            'last_update': time.time(),
            'chat_name': chat_name
        }
    
    # 鏇存柊鏈€鍚庢椿鍔ㄦ椂闂?    media_groups[group_id]['last_update'] = time.time()
    
    # 灏嗗綋鍓嶆秷鎭坊鍔犲埌缁勪腑锛岄伩鍏嶉噸澶嶆坊鍔?    if not any(m.id == message.id for m in media_groups[group_id]['messages']):
        media_groups[group_id]['messages'].append(message)
        logger.info(f"濯掍綋缁?{group_id} 娣诲姞涓€鏉℃柊娑堟伅锛岀洰鍓嶆敹闆嗕簡 {len(media_groups[group_id]['messages'])} 鏉?)
    
    # 濡傛灉璇ョ粍宸茬粡鍦ㄥ鐞嗕腑锛岀洿鎺ヨ繑鍥烇紝閬垮厤閲嶅澶勭悊
    if media_groups[group_id]['processing']:
        logger.info(f"濯掍綋缁?{group_id} 宸茬粡鍦ㄥ鐞嗕腑锛岃烦杩?)
        return
    
    # 鏍囪涓哄鐞嗕腑锛岄伩鍏嶉噸澶嶅惎鍔ㄥ鐞嗕换鍔?    media_groups[group_id]['processing'] = True
    
    # 鍒涘缓涓€涓鐞嗕换鍔★紝浼氳嚜鍔ㄧ瓑寰呰冻澶熺殑鏃堕棿
    asyncio.create_task(process_media_group_with_timeout(client, group_id))

async def process_media_group_with_timeout(client, group_id):
    """澶勭悊濯掍綋缁勶紝浣跨敤鑷€傚簲绛夊緟鏃堕棿纭繚鏀堕泦瀹屾暣"""
    try:
        # 鍒濆绛夊緟鏃堕棿锛屽崟浣嶏細绉?        wait_time = 5
        
        # 杩炵画鍑犳娑堟伅鏁伴噺鐩稿悓鐨勮鏁?        stable_count = 0
        last_count = 0
        max_stable_count = 3  # 闇€瑕佽揪鍒扮殑绋冲畾娆℃暟
        
        # 鏈€澶氱瓑寰呮鏁?        max_wait_cycles = 10
        wait_cycles = 0
        
        while wait_cycles < max_wait_cycles:
            # 妫€鏌ョ粍鏄惁渚濈劧瀛樺湪
            if group_id not in media_groups:
                logger.warning(f"绛夊緟杩囩▼涓獟浣撶粍 {group_id} 娑堝け锛屽彲鑳藉凡琚鐞?)
                return
            
            # 璁板綍褰撳墠鐘舵€?            group_data = media_groups[group_id]
            current_count = len(group_data['messages'])
            chat_name = group_data['chat_name']
            
            # 鍒ゆ柇鏄惁绋冲畾锛堟病鏈夋柊娑堟伅杩涙潵锛?            if current_count == last_count:
                stable_count += 1
                logger.info(f"濯掍綋缁?{group_id} 浠庛€寋chat_name}銆嶆敹闆嗕簡 {current_count} 鏉℃秷鎭紝淇濇寔绋冲畾 ({stable_count}/{max_stable_count})")
            else:
                # 鏀跺埌鏂版秷鎭紝閲嶇疆绋冲畾璁℃暟
                stable_count = 0
                logger.info(f"濯掍綋缁?{group_id} 浠庛€寋chat_name}銆嶆敹闆嗕簡 {current_count} 鏉℃秷鎭紙鏈夋柊娑堟伅锛?)
            
            # 璁板綍褰撳墠鏁伴噺鐢ㄤ簬涓嬫姣旇緝
            last_count = current_count
            
            # 濡傛灉涓€娈垫椂闂村唴娑堟伅鏁伴噺绋冲畾锛屽垯璁や负鎵€鏈夋秷鎭凡鏀堕泦瀹屾垚
            if stable_count >= max_stable_count:
                logger.info(f"濯掍綋缁?{group_id} 鐨勬秷鎭暟閲忓凡绋冲畾鍦?{current_count} 鏉★紝寮€濮嬪鐞?)
                break
            
            # 妫€鏌ヨ嚜涓婃娑堟伅鍚庣粡杩囩殑鏃堕棿锛屽鏋滆秴杩?5绉掓棤鏂版秷鎭紝涔熻涓哄畬鎴?            elapsed = time.time() - group_data['last_update']
            if elapsed > 15:
                logger.info(f"濯掍綋缁?{group_id} 宸茶秴杩?5绉掓棤鏂版秷鎭紝瑙嗕负鏀堕泦瀹屾垚")
                break
            
            # 绛夊緟涓€娈垫椂闂?            logger.info(f"绛夊緟鏇村鍙兘鐨勫獟浣撶粍娑堟伅锛寋wait_time}绉?..")
            await asyncio.sleep(wait_time)
            wait_cycles += 1
            
            # 鍔ㄦ€佽皟鏁寸瓑寰呮椂闂达紙閫愭笎鍑忓皯锛?            wait_time = max(1, wait_time - 1)
        
        # 鏈€缁堝鐞嗗獟浣撶粍
        await process_media_group_final(client, group_id)
    except Exception as e:
        logger.error(f"澶勭悊濯掍綋缁?{group_id} 鏃跺嚭閿? {e}")
        if group_id in media_groups:
            # 鍑洪敊鏃朵篃娓呯悊锛岄伩鍏嶅唴瀛樻硠婕?            del media_groups[group_id]

async def process_media_group_final(client, group_id):
    """鏈€缁堝鐞嗗獟浣撶粍锛屽彂閫佹墍鏈夊獟浣?""
    try:
        global processing_message, daily_message_count, last_forward_time
        
        # 濡傛灉宸茬粡鍦ㄥ鐞嗘秷鎭紝鍒欒烦杩囧綋鍓嶅獟浣撶粍
        if processing_message:
            logger.info(f"宸叉湁娑堟伅姝ｅ湪澶勭悊涓紝璺宠繃濯掍綋缁?{group_id}")
            return
            
        # 鏍囪涓烘鍦ㄥ鐞嗘秷鎭?        processing_message = True
            
        # 妫€鏌ョ粍鏄惁瀛樺湪
        if group_id not in media_groups:
            logger.warning(f"澶勭悊鍓嶅獟浣撶粍 {group_id} 娑堝け锛屽彲鑳藉凡琚鐞?)
            processing_message = False
            return
            
        # 鑾峰彇缁勬暟鎹苟浠庤窡韪瓧鍏镐腑绉婚櫎
        group_data = media_groups.pop(group_id)
        group_messages = group_data['messages']
        source_info = group_data['source_info']
        footer = group_data['footer']
        destination_channel = group_data['destination']
        chat_name = group_data['chat_name']
        
        # 濡傛灉娌℃湁娑堟伅锛岀洿鎺ヨ繑鍥?        if not group_messages:
            logger.warning(f"濯掍綋缁?{group_id} 娌℃湁娑堟伅鍙鐞?)
            processing_message = False
            return
            
        # 鎸夌収ID鎺掑簭锛岀‘淇濋『搴忔纭?        group_messages.sort(key=lambda x: x.id)
        
        # 鏀堕泦鎵€鏈夋枃鏈唴瀹瑰苟鍚堝苟
        all_texts = []
        full_texts = []
        for msg in group_messages:
            if msg.text and msg.text.strip():
                all_texts.append(msg.text.strip())
            # 浣跨敤瀹屾暣鐨勬枃鏈彁鍙栧嚱鏁?            full_msg_text = get_full_message_text(msg)
            if full_msg_text.strip():
                full_texts.append(full_msg_text.strip())
        
        # 鍘婚噸骞跺悎骞舵枃鏈?        unique_texts = []
        for text in all_texts:
            if text not in unique_texts:
                unique_texts.append(text)
        
        # 鏋勫缓鏈€缁堟爣棰?        caption_text = "\n\n".join(unique_texts)
        
        # 妫€鏌ュ獟浣撶粍娑堟伅鏂囨湰鏄惁鍖呭惈鍏抽敭璇?        has_keywords = False
        # 鍏堟鏌ユ彁鍙栫殑甯歌鏂囨湰
        for text in unique_texts:
            if contains_keywords(text):
                has_keywords = True
                logger.info(f"濯掍綋缁?{group_id} 涓殑娑堟伅鏂囨湰鍖呭惈鍏抽敭璇?)
                break
        
        # 濡傛灉甯歌鏂囨湰娌℃湁鍏抽敭璇嶏紝鍐嶆鏌ュ畬鏁存彁鍙栫殑鏂囨湰
        if not has_keywords:
            for text in full_texts:
                if contains_keywords(text):
                    has_keywords = True
                    logger.info(f"濯掍綋缁?{group_id} 涓殑娑堟伅瀹屾暣鏂囨湰鍖呭惈鍏抽敭璇?)
                    break
        
        if not has_keywords:
            logger.info(f"璺宠繃濯掍綋缁?{group_id} - 涓嶅寘鍚换浣曟寚瀹氬叧閿瘝")
            processing_message = False
            return
        
        # 妫€鏌ユ瘡鏃ユ秷鎭檺棰?        global daily_message_count, last_forward_time
        if daily_message_count >= MAX_DAILY_MESSAGES:
            logger.info(f"璺宠繃濯掍綋缁?{group_id} - 宸茶揪鍒版瘡鏃ヨ浆鍙戦檺棰?({MAX_DAILY_MESSAGES})")
            processing_message = False
            return
        
        # 妫€鏌ュ喎鍗存椂闂?- 閬垮厤鍒濇鍚姩鏃朵篃鏈夊喎鍗?        if last_forward_time:
            current_time = datetime.now()
            time_since_last_forward = (current_time - last_forward_time).total_seconds() / 60
            if time_since_last_forward < COOLDOWN_MINUTES:
                remaining_minutes = COOLDOWN_MINUTES - time_since_last_forward
                logger.info(f"鍐峰嵈鏃堕棿鏈埌锛岃繕闇€绛夊緟 {remaining_minutes:.1f} 鍒嗛挓鍚庢墠鑳借浆鍙戝獟浣撶粍")
                logger.info(f"濯掍綋缁?{group_id} 灏嗗湪 {remaining_minutes:.1f} 鍒嗛挓鍚庡皾璇曡浆鍙?)
                await asyncio.sleep(remaining_minutes * 60)  # 绛夊緟鍓╀綑鍐峰嵈鏃堕棿
                
                # 鍐嶆妫€鏌ユ槸鍚﹀彲浠ュ彂閫佹秷鎭紙鍙兘鍦ㄧ瓑寰呮湡闂磋揪鍒颁簡姣忔棩闄愰锛?                if daily_message_count >= MAX_DAILY_MESSAGES:
                    logger.info(f"绛夊緟鍐峰嵈鏃堕棿鍚庢鏌ワ細璺宠繃濯掍綋缁?{group_id} - 宸茶揪鍒版瘡鏃ヨ浆鍙戦檺棰?({MAX_DAILY_MESSAGES})")
                    processing_message = False
                    return
        else:
            logger.info("棣栨杞彂濯掍綋缁勶紝鏃犻渶绛夊緟鍐峰嵈鏃堕棿")
            
        # 娣诲姞婧愪俊鎭拰椤佃剼
        if caption_text:
            caption_text += source_info + footer
        else:
            caption_text = source_info + footer if (source_info or footer) else ""
        
        # 鍑嗗鎵€鏈夊獟浣?        media_files = []
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 鐜版湁浠ｇ爜...
            # 灏嗗獟浣撴枃浠朵笅杞藉埌涓存椂鐩綍
            for i, message in enumerate(group_messages):
                if message.media:
                    # 涓嬭浇濯掍綋
                    file_extension = get_media_extension(message.media)
                    temp_file = os.path.join(temp_dir, f"media_{group_id}_{i}{file_extension}")
                    await client.download_media(message, temp_file)
                    media_files.append(temp_file)
            
            # 濡傛灉娌℃湁濯掍綋锛岀洿鎺ヨ繑鍥?            if not media_files:
                logger.warning(f"濯掍綋缁?{group_id} 娌℃湁鍙彁鍙栫殑濯掍綋鍐呭")
                processing_message = False
                return
            
            # 鍙戦€佹敹闆嗗埌鐨勫叏閮ㄥ獟浣?            media_group = []
            
            for file in media_files:
                mime_type = mimetypes.guess_type(file)[0]
                
                if mime_type and mime_type.startswith('image'):
                    # 鍥剧墖
                    media_group.append(InputMediaPhoto(file))
                elif mime_type and (mime_type.startswith('video') or mime_type.startswith('audio')):
                    # 瑙嗛鎴栭煶棰?                    media_group.append(InputMediaDocument(file))
                else:
                    # 鍏朵粬鏂囨。
                    media_group.append(InputMediaDocument(file))
            
            # 鏈€鍚庡鐞嗭細鍙戦€佸獟浣撶粍
            try:
                # 鏍囬搴旇娣诲姞鍒版渶鍚庝竴涓獟浣撻」锛屼笌鍘熶唬鐮佷繚鎸佷竴鑷?                if caption_text and media_group:
                    # 灏嗘爣棰樻坊鍔犲埌鏈€鍚庝竴涓獟浣撻」
                    last_media = media_group[-1]
                    last_media.caption = caption_text
                    last_media.parse_mode = 'html' if FORMAT_AS_HTML else None
                
                # 鍙戦€佸獟浣撶粍
                sent_messages = await client.send_file(
                    destination_channel,
                    media_group,
                    caption=caption_text if len(media_group) == 1 else None,  # 鍗曚釜濯掍綋鏃朵篃娣诲姞鏍囬
                    parse_mode='html' if FORMAT_AS_HTML else None
                )
                
                # 濡傛灉鏄崟鏉℃秷鎭垨鍒楄〃鐨勭涓€鏉★紝璁板綍鍏禝D
                first_sent_id = sent_messages[0].id if isinstance(sent_messages, list) else sent_messages.id
                logger.info(f"鎴愬姛鍙戦€佸獟浣撶粍 {group_id} 鍒扮洰鏍囬閬擄紝棣栨潯娑堟伅ID: {first_sent_id}")
                
                # 鏇存柊杞彂璁℃暟鍜屾椂闂?                last_forward_time = datetime.now()
                increment_message_count()
                
                # 閲嶆柊闅忔満鐢熸垚鍐峰嵈鏃堕棿
                COOLDOWN_MINUTES = get_random_cooldown()
                logger.info(f"闅忔満鐢熸垚鏂扮殑鍐峰嵈鏃堕棿: {COOLDOWN_MINUTES}鍒嗛挓")
                
                # 璁＄畻涓嬫鍙浆鍙戞椂闂?                next_forward_time = last_forward_time + timedelta(minutes=COOLDOWN_MINUTES)
                logger.info(f"涓嬫鍙浆鍙戞椂闂? {next_forward_time.strftime('%H:%M:%S')}")
                
            except Exception as e:
                logger.error(f"鍙戦€佸獟浣撶粍 {group_id} 鏃跺嚭閿? {e}")
                processing_message = False
                
        except Exception as e:
            logger.error(f"澶勭悊濯掍綋缁勬秷鎭椂鍑洪敊: {e}")
            processing_message = False
            
        finally:
            # 娓呯悊涓存椂鏂囦欢
            try:
                for file_path in media_files:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                logger.info("涓存椂濯掍綋鏂囦欢宸叉竻鐞?)
            except Exception as e:
                logger.error(f"娓呯悊涓存椂鏂囦欢鏃跺嚭閿? {e}")
            # 澶勭悊缁撴潫鍚庯紝鏃犺鎴愬姛澶辫触锛岄兘閲嶇疆鏍囧織
            processing_message = False
            
    except Exception as e:
        logger.error(f"澶勭悊濯掍綋缁?{group_id} 鏃跺嚭閿? {e}")
        # 纭繚閿欒鎯呭喌涓嬩篃閲嶇疆鏍囧織
        processing_message = False

# 娣诲姞涓€涓嚱鏁版潵鍒ゆ柇濯掍綋绫诲瀷骞惰繑鍥為€傚綋鐨勬枃浠舵墿灞曞悕
def get_media_extension(media):
    """鏍规嵁濯掍綋绫诲瀷杩斿洖閫傚綋鐨勬枃浠舵墿灞曞悕"""
    if isinstance(media, MessageMediaPhoto):
        return '.jpg'
    elif isinstance(media, MessageMediaDocument):
        for attribute in media.document.attributes:
            if isinstance(attribute, DocumentAttributeFilename):
                # 鑾峰彇鍘熷鏂囦欢鐨勬墿灞曞悕
                return os.path.splitext(attribute.file_name)[1]
        # 濡傛灉娌℃湁鎵惧埌鏂囦欢鍚嶏紝榛樿浣跨敤.mp4锛堥拡瀵硅棰戯級
        return '.mp4'
    return '.bin'  # 榛樿浜岃繘鍒舵枃浠舵墿灞曞悕

if __name__ == '__main__':
    asyncio.run(main()) 
