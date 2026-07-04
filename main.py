import asyncio
import random
import time
import os
import psycopg2
import psycopg2.extras
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from itertools import combinations

# =====================================================================
# НАСТРОЙКИ БОТА
# =====================================================================
BOT_TOKEN    = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_ID = 5908271287
WORK_COOLDOWN     = 150
WORK_ENERGY_COST  = 15
TRAIN_ENERGY_COST = 50

REFERRAL_BONUS_COINS_REFERRER = 500  # бонус тому, кто пригласил
REFERRAL_BONUS_EXP_REFERRER = 150
REFERRAL_BONUS_COINS_NEWBIE = 200  # бонус новому игроку за переход по ссылке
REFERRAL_BONUS_EXP_NEWBIE = 50

REBIRTH_MIN_LEVEL          = 100   # условие для перерождения
REBIRTH_START_COINS        = 500   # стартовый капитал при 1-м перерождении
REBIRTH_START_COINS_PER    = 250   # прирост стартового капитала за каждое ПРЕДЫДУЩЕЕ перерождение
REBIRTH_COIN_BONUS_PER     = 15    # % к монетам за каждое перерождение (постоянно)
REBIRTH_XP_BONUS_PER       = 15    # % к опыту за каждое перерождение (постоянно)

# req_rebirths -> job_key стартовой профессии, открываемой перерождением
REBIRTH_STARTER_JOBS = {
    1: "founder_1",
    2: "science_1",
    3: "media_1",
    4: "politics_1",
}

ASCENSION_CRYSTALS_BASE   = 50   # кристаллов за 1-е перерождение
ASCENSION_CRYSTALS_PER    = 100   # + за каждое следующее перерождение
ASCENSION_GACHA_PRICE     = 30   # кристаллов за 1 круть гачи

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ БОТА И ДИСПЕТЧЕРА
# =====================================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        if event.from_user and event.from_user.id != ADMIN_ID:
            user = get_user(event.from_user.id)
            if user and user.get("is_banned"):
                return  # молча игнорируем всё от забаненного игрока
        return await handler(event, data)


dp.message.middleware(BanCheckMiddleware())
# =====================================================================
# ПОДКЛЮЧЕНИЕ К PostgreSQL
# =====================================================================
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# =====================================================================
# ФОРМУЛА ОПЫТА
# =====================================================================
def xp_needed(level: int) -> int:
    return int(120 * (level ** 1.65))

def scale_xp(base_xp: int, level: int) -> int:
    return int(base_xp * (1 + level * 0.08))

def scale_coins(base_coins: int, level: int) -> int:
    return int(base_coins * (1 + level * 0.05))

# =====================================================================
# ВЕТКИ ПРОФЕССИЙ
# =====================================================================
JOBS = {
    # ══════════ ВЕТКА ИНТЕЛЛЕКТ (уклон в XP) ══════════
    "intel_1": {
        "name":        "Списывальщик на Сом-сынаве",
        "branch":      "intel",
        "grade":       1,
        "min_level":   1,
        "min_reward":  8,  "max_reward":  14,
        "min_exp":     30, "max_exp":     50,
        "description": "Ловко списываешь на экзаменах. Немного монет, зато море опыта.",
        "evolves_to":  "intel_2",
        "req_level":   5,
    },
    "intel_2": {
        "name":        "Активист Студпарламента, умоляющий не отчислять",
        "branch":      "intel",
        "grade":       2,
        "min_level":   5,
        "min_reward":  18, "max_reward":  30,
        "min_exp":     80, "max_exp":     120,
        "description": "Ходишь по деканатам с умоляющим взглядом. Опыт копится быстро.",
        "evolves_to":  "intel_3",
        "req_level":   10,
        "req_skill":   ("communication_level", 2),
    },
    "intel_3": {
        "name":        "Старшекурсник, пишущий дипломные за еду в Джал-Маркете",
        "branch":      "intel",
        "grade":       3,
        "min_level":   10,
        "min_reward":  40, "max_reward":  65,
        "min_exp":     180,"max_exp":     260,
        "description": "Пишешь чужие дипломы за шаурму. Знания растут.",
        "evolves_to":  "intel_4",
        "req_level":   20,
        "req_skill":   ("communication_level", 4),
        "req_item":    ("has_laptop", "💻 Ноутбук"),
    },
    "intel_4": {
        "name":        "Младший ассистент, который бегает за кофе для кафедры",
        "branch":      "intel",
        "grade":       4,
        "min_level":   20,
        "min_reward":  90, "max_reward":  140,
        "min_exp":     380,"max_exp":     520,
        "description": "Носишь кофе профессорам и тихо всё записываешь.",
        "evolves_to":  "intel_5",
        "req_level":   35,
        "req_skill":   ("communication_level", 5),
        "req_item":    ("has_laptop", "💻 Ноутбук"),
    },
    "intel_5": {
        "name":        "Строгий препод, который принципиально не ставит «А» автоматом",
        "branch":      "intel",
        "grade":       5,
        "min_level":   35,
        "min_reward":  200,"max_reward":  310,
        "min_exp":     800,"max_exp":     1100,
        "description": "Истязаешь студентов зачётными книжками. Много опыта.",
        "evolves_to":  "intel_6",
        "req_level":   50,
        "req_skill":   ("management_level", 3),
        "req_item":    ("has_professor_badge", "🎓 Профессорский значок"),
    },
    "intel_6": {
        "name":        "Завкафедрой, потерявший все ведомости",
        "branch":      "intel",
        "grade":       6,
        "min_level":   50,
        "min_reward":  400,"max_reward":  600,
        "min_exp":     1600,"max_exp":    2200,
        "description": "Управляешь кафедрой в перманентном хаосе. Огромный XP.",
        "evolves_to":  "intel_7",
        "req_level":   70,
        "req_skill":   ("management_level", 6),
        "req_item":    ("has_professor_badge", "🎓 Профессорский значок"),
    },
    "intel_7": {
        "name":        "Декан самого элитного факультета",
        "branch":      "intel",
        "grade":       7,
        "min_level":   70,
        "min_reward":  700,"max_reward":  1000,
        "min_exp":     3000,"max_exp":    4000,
        "description": "Элита элит. Студенты дрожат при виде тебя.",
        "evolves_to":  "intel_8",
        "req_level":   80,
        "req_skill":   ("management_level", 8),
        "req_item":    ("has_dean_seal", "🔏 Декановская печать"),
    },
    "intel_8": {
        "name":        "Официальный представитель Минобра в КТУ",
        "branch":      "intel",
        "grade":       8,
        "min_level":   80,
        "min_reward":  1200,"max_reward": 1700,
        "min_exp":     5500,"max_exp":    7500,
        "description": "Следишь за всеми и ни за что не отвечаешь.",
        "evolves_to":  "intel_9",
        "req_level":   100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_dean_seal", "🔏 Декановская печать"),
    },
    "intel_9": {
        "name":        "Всемогущий Ректор университета «Манас»",
        "branch":      "intel",
        "grade":       9,
        "min_level":   100,
        "min_reward":  2000,"max_reward": 3000,
        "min_exp":     8000,"max_exp":    12000,
        "description": "Ты — Ректор. Интеллект растёт с каждым уровнем +10.",
        "evolves_to":  None,
        "special":     "intellect_x10",
    },

    # ══════════ ВЕТКА БАЛАНС ══════════
    "balance_1": {
        "name":        "Бегун за пирожками в Джал-Маркет на перемене",
        "branch":      "balance",
        "grade":       1,
        "min_level":   1,
        "min_reward":  18, "max_reward":  28,
        "min_exp":     18, "max_exp":     28,
        "description": "Носишься за едой. Всё ровненько: и монеты, и опыт.",
        "evolves_to":  "balance_2",
        "req_level":   5,
    },
    "balance_2": {
        "name":        "Таксист на попутке (Джал — Турусбекова)",
        "branch":      "balance",
        "grade":       2,
        "min_level":   5,
        "min_reward":  45, "max_reward":  65,
        "min_exp":     45, "max_exp":     65,
        "description": "Подбираешь студентов по дороге. Баланс идеален.",
        "evolves_to":  "balance_3",
        "req_level":   10,
        "req_skill":   ("driving_level", 2),
    },
    "balance_3": {
        "name":        "Пеший курьер, доставляющий прямо в аудитории",
        "branch":      "balance",
        "grade":       3,
        "min_level":   10,
        "min_reward":  100,"max_reward":  150,
        "min_exp":     100,"max_exp":     150,
        "description": "Врываешься в пары с заказами. Преподы в шоке.",
        "evolves_to":  "balance_4",
        "req_level":   20,
        "req_skill":   ("driving_level", 3),
        "req_item":    ("has_scooter", "🛵 Скутер"),
    },
    "balance_4": {
        "name":        "Владелец точки ксерокопии у главного корпуса",
        "branch":      "balance",
        "grade":       4,
        "min_level":   20,
        "min_reward":  220,"max_reward":  320,
        "min_exp":     220,"max_exp":     320,
        "description": "Ксеришь зачётки и методички. Народу тьма.",
        "evolves_to":  "balance_5",
        "req_level":   35,
        "req_skill":   ("organization_level", 4),
        "req_item":    ("has_scooter", "🛵 Скутер"),
    },
    "balance_5": {
        "name":        "Организатор студенческих туров на Иссык-Куль",
        "branch":      "balance",
        "grade":       5,
        "min_level":   35,
        "min_reward":  480,"max_reward":  680,
        "min_exp":     480,"max_exp":     680,
        "description": "Вывозишь студентов отдыхать. Все довольны.",
        "evolves_to":  "balance_6",
        "req_level":   50,
        "req_skill":   ("organization_level", 6),
        "req_item":    ("has_logistics_license", "📋 Лицензия логиста"),
    },
    "balance_6": {
        "name":        "Глава крупной бишкекской службы доставки",
        "branch":      "balance",
        "grade":       6,
        "min_level":   50,
        "min_reward":  900,"max_reward":  1300,
        "min_exp":     900,"max_exp":     1300,
        "description": "Управляешь сотнями курьеров. Серьёзный уровень.",
        "evolves_to":  "balance_7",
        "req_level":   70,
        "req_skill":   ("organization_level", 8),
        "req_item":    ("has_logistics_license", "📋 Лицензия логиста"),
    },
    "balance_7": {
        "name":        "Владелец логистической сети по всему СНГ",
        "branch":      "balance",
        "grade":       7,
        "min_level":   70,
        "min_reward":  1600,"max_reward": 2200,
        "min_exp":     1600,"max_exp":    2200,
        "description": "Бизнес вышел за пределы Кыргызстана.",
        "evolves_to":  "balance_8",
        "req_level":   80,
        "req_skill":   ("management_level", 7),
        "req_item":    ("has_business_plan", "📊 Бизнес-план"),
    },
    "balance_8": {
        "name":        "Главный инвестор и спонсор новых корпусов КТУ",
        "branch":      "balance",
        "grade":       8,
        "min_level":   80,
        "min_reward":  2800,"max_reward": 3800,
        "min_exp":     2800,"max_exp":    3800,
        "description": "Строишь новые корпуса и вешаешь на них своё имя.",
        "evolves_to":  "balance_9",
        "req_level":   100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_business_plan", "📊 Бизнес-план"),
    },
    "balance_9": {
        "name":        "Магнат каршеринга и всей инфраструктуры Бишкека",
        "branch":      "balance",
        "grade":       9,
        "min_level":   100,
        "min_reward":  5000,"max_reward": 7000,
        "min_exp":     5000,"max_exp":    7000,
        "description": "Весь город работает на тебя.",
        "evolves_to":  None,
    },

    # ══════════ ВЕТКА ДЕНЬГИ ══════════
    "money_1": {
        "name":        "Помощник на раздаче Чорбо в столовой",
        "branch":      "money",
        "grade":       1,
        "min_level":   1,
        "min_reward":  30, "max_reward":  95,
        "min_exp":     8,  "max_exp":     14,
        "description": "Разливаешь суп. Монет много, опыта мало.",
        "evolves_to":  "money_2",
        "req_level":   5,
    },
    "money_2": {
        "name":        "Тайный дилер Турецкого Чая и Симитов в коридорах",
        "branch":      "money",
        "grade":       2,
        "min_level":   5,
        "min_reward":  70, "max_reward":  100,
        "min_exp":     20, "max_exp":     35,
        "description": "Продаёшь симиты из-под полы. Охрана в курсе.",
        "evolves_to":  "money_3",
        "req_level":   10,
        "req_skill": ("service_level", 2),
    },
    "money_3": {
        "name":        "Бариста в кофейне напротив ворот Манаса",
        "branch":      "money",
        "grade":       3,
        "min_level":   10,
        "min_reward":  160,"max_reward":  230,
        "min_exp":     45, "max_exp":     70,
        "description": "Льёшь латте студентам. Чаевые огонь.",
        "evolves_to":  "money_4",
        "req_level":   20,
        "req_skill":   ("service_level", 3),
        "req_item":    ("has_shaker", "🍹 Проф. шейкер"),
    },
    "money_4": {
        "name":        "Управляющий университетским буфетом",
        "branch":      "money",
        "grade":       4,
        "min_level":   20,
        "min_reward":  340,"max_reward":  480,
        "min_exp":     90, "max_exp":     130,
        "description": "Контролируешь все продажи в буфете. Касса звенит.",
        "evolves_to":  "money_5",
        "req_level":   35,
        "req_skill":   ("service_level", 5),
        "req_item":    ("has_shaker", "🍹 Проф. шейкер"),
    },
    "money_5": {
        "name":        "Поставщик турецких продуктов для всех кафе Джала",
        "branch":      "money",
        "grade":       5,
        "min_level":   35,
        "min_reward":  700,"max_reward":  1000,
        "min_exp":     175,"max_exp":     260,
        "description": "Возишь товар оптом. Маржа ощутимая.",
        "evolves_to":  "money_6",
        "req_level":   50,
        "req_skill":   ("management_level", 3),
        "req_item":    ("has_import_license", "🛃 Импортная лицензия"),
    },
    "money_6": {
        "name":        "Владелец сети донерных вокруг всех вузов Бишкека",
        "branch":      "money",
        "grade":       6,
        "min_level":   50,
        "min_reward":  1400,"max_reward": 2000,
        "min_exp":     350,"max_exp":     500,
        "description": "Донер везде. Ты — везде. Деньги — везде.",
        "evolves_to":  "money_7",
        "req_level":   70,
        "req_skill":   ("management_level", 6),
        "req_item":    ("has_import_license", "🛃 Импортная лицензия"),
    },
    "money_7": {
        "name":        "Главный арендатор и владелец франшиз столовых КТУ",
        "branch":      "money",
        "grade":       7,
        "min_level":   70,
        "min_reward":  2500,"max_reward": 3500,
        "min_exp":     600,"max_exp":     850,
        "description": "Все едальни КТУ платят тебе ренту.",
        "evolves_to":  "money_8",
        "req_level":   80,
        "req_skill":   ("management_level", 8),
        "req_item":    ("has_franchise_contract", "📜 Франшизный контракт"),
    },
    "money_8": {
        "name":        "Ресторатор-миллионер, открывший элитный ресторан в центре",
        "branch":      "money",
        "grade":       8,
        "min_level":   80,
        "min_reward":  4500,"max_reward": 6000,
        "min_exp":     1000,"max_exp":    1400,
        "description": "Твой ресторан — самый дорогой в Бишкеке.",
        "evolves_to":  "money_9",
        "req_level":   100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_franchise_contract", "📜 Франшизный контракт"),
    },
    "money_9": {
        "name":        "Теневой спонсор университета и король общепита Кыргызстана",
        "branch":      "money",
        "grade":       9,
        "min_level":   100,
        "min_reward":  9000,"max_reward": 15000,
        "min_exp":     1500,"max_exp":    2200,
        "description": "Заработок в 500+ раз выше первого уровня. Ты — легенда.",
        "evolves_to":  None,
        "special":     "money_king",
    },
# ══════════ ВЕТКА ОСНОВАТЕЛЯ (открывается перерождением) ══════════
    "founder_1": {
        "name":        "🌱 Стажёр Фонда выпускников КТУ",
        "branch":      "founder", "grade": 1, "min_level": 1,
        "min_reward":  30, "max_reward":  60,
        "min_exp":     30, "max_exp":     60,
        "description": "Ты вернулся с чистого листа, но с опытом за плечами.",
        "evolves_to":  "founder_2", "req_level": 5,
    },
    "founder_2": {
        "name":        "🎓 Куратор международных грантов",
        "branch":      "founder", "grade": 2, "min_level": 5,
        "min_reward":  90, "max_reward":  120,
        "min_exp":     90, "max_exp":     120,
        "description": "Раздаёшь гранты и завязываешь нужные связи.",
        "evolves_to":  "founder_3", "req_level": 10,
        "req_skill":   ("communication_level", 3),
    },
    "founder_3": {
        "name":        "📊 Советник ректора по стратегии",
        "branch":      "founder", "grade": 3, "min_level": 10,
        "min_reward":  190, "max_reward": 240,
        "min_exp":     190, "max_exp":    240,
        "description": "Твоё слово теперь имеет вес в кабинете ректора.",
        "evolves_to":  "founder_4", "req_level": 20,
        "req_skill":   ("management_level", 3),
        "req_item":    ("has_laptop", "💻 Ноутбук"),
    },
    "founder_4": {
        "name":        "🏛 Директор Фонда развития КТУ",
        "branch":      "founder", "grade": 4, "min_level": 20,
        "min_reward":  380, "max_reward": 490,
        "min_exp":     380, "max_exp":    490,
        "description": "Управляешь миллионами сомов на развитие университета.",
        "evolves_to":  "founder_5", "req_level": 35,
        "req_skill":   ("management_level", 5),
        "req_item":    ("has_business_plan", "📊 Бизнес-план"),
    },
    "founder_5": {
        "name":        "🕴 Член Попечительского совета",
        "branch":      "founder", "grade": 5, "min_level": 35,
        "min_reward":  800, "max_reward": 1080,
        "min_exp":     800, "max_exp":    1080,
        "description": "Решения, определяющие судьбу КТУ на десятилетия.",
        "evolves_to":  "founder_6", "req_level": 50,
        "req_skill":   ("management_level", 7),
        "req_item":    ("has_dean_seal", "🔏 Декановская печать"),
    },
    "founder_6": {
        "name":        "🕌 Посланник Турции при университете",
        "branch":      "founder", "grade": 6, "min_level": 50,
        "min_reward":  1600, "max_reward": 1900,
        "min_exp":     1600, "max_exp":    1900,
        "description": "Официальный дипломатический статус.",
        "evolves_to":  "founder_7", "req_level": 70,
        "req_skill":   ("management_level", 9),
        "req_item":    ("has_franchise_contract", "📜 Франшизный контракт"),
    },
    "founder_7": {
        "name":        "🌍 Почётный профессор трёх континентов",
        "branch":      "founder", "grade": 7, "min_level": 70,
        "min_reward":  3000, "max_reward": 3400,
        "min_exp":     3000, "max_exp":    3400,
        "description": "Твоё имя знают в университетах Азии, Европы и Америки.",
        "evolves_to":  "founder_8", "req_level": 80,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_logistics_license", "📋 Лицензия логиста"),
    },
    "founder_8": {
        "name":        "👔 Глава ассоциации университетов Центральной Азии",
        "branch":      "founder", "grade": 8, "min_level": 80,
        "min_reward":  4800, "max_reward": 5600,
        "min_exp":     4800, "max_exp":    5600,
        "description": "Под твоим началом десятки вузов региона.",
        "evolves_to":  "founder_9", "req_level": 100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_import_license", "🛃 Импортная лицензия"),
    },
    "founder_9": {
        "name":        "🏆 Легендарный Отец-Основатель нового кампуса",
        "branch":      "founder", "grade": 9, "min_level": 100,
        "min_reward":  8000, "max_reward": 12000,
        "min_exp":     8000, "max_exp":    12000,
        "description": "Ты заложил новый кампус КТУ своими руками.",
        "evolves_to":  None,
        "special":     "founder_king",
    },
# ══════════ ВЕТКА НАУКИ (2 перерождение) ══════════
    "science_1": {
        "name":        "🧪 Лаборант кафедры Химии",
        "branch":      "science", "grade": 1, "min_level": 1,
        "min_reward":  30, "max_reward":  60,
        "min_exp":     30, "max_exp":     60,
        "description": "Моешь пробирки, но втайне мечтаешь о Нобелевке.",
        "evolves_to":  "science_2", "req_level": 5,
    },
    "science_2": {
        "name":        "🔬 Ассистент профессора на грантовом проекте",
        "branch":      "science", "grade": 2, "min_level": 5,
        "min_reward":  90, "max_reward":  150,
        "min_exp":     90, "max_exp":    150,
        "description": "Пишешь отчёты по гранту, который никто не читает.",
        "evolves_to":  "science_3", "req_level": 10,
        "req_skill":   ("communication_level", 3),
    },
    "science_3": {
        "name":        "📄 Автор международных публикаций (Scopus)",
        "branch":      "science", "grade": 3, "min_level": 10,
        "min_reward":  220, "max_reward": 390,
        "min_exp":     220, "max_exp":    390,
        "description": "Твоё имя теперь можно нагуглить в научной базе.",
        "evolves_to":  "science_4", "req_level": 20,
        "req_skill":   ("management_level", 3),
        "req_item":    ("has_laptop", "💻 Ноутбук"),
    },
    "science_4": {
        "name":        "🧬 Руководитель лаборатории биотехнологий",
        "branch":      "science", "grade": 4, "min_level": 20,
        "min_reward":  480, "max_reward": 650,
        "min_exp":     480, "max_exp":    650,
        "description": "У тебя своя лаборатория и бюджет на реагенты.",
        "evolves_to":  "science_5", "req_level": 35,
        "req_skill":   ("management_level", 5),
        "req_item":    ("has_business_plan", "📊 Бизнес-план"),
    },
    "science_5": {
        "name":        "🏅 Обладатель гранта Erasmus+",
        "branch":      "science", "grade": 5, "min_level": 35,
        "min_reward":  920, "max_reward": 1550,
        "min_exp":     920, "max_exp":    1550,
        "description": "Летаешь между университетами Европы с докладами.",
        "evolves_to":  "science_6", "req_level": 50,
        "req_skill":   ("management_level", 7),
        "req_item":    ("has_dean_seal", "🔏 Декановская печать"),
    },
    "science_6": {
        "name":        "🛰 Учёный, сотрудничающий с NASA/ESA",
        "branch":      "science", "grade": 6, "min_level": 50,
        "min_reward":  1950, "max_reward": 2750,
        "min_exp":     1950, "max_exp":    2750,
        "description": "Твои расчёты используют в реальных космических миссиях.",
        "evolves_to":  "science_7", "req_level": 70,
        "req_skill":   ("management_level", 9),
        "req_item":    ("has_franchise_contract", "📜 Франшизный контракт"),
    },
    "science_7": {
        "name":        "🧠 Изобретатель революционной технологии",
        "branch":      "science", "grade": 7, "min_level": 70,
        "min_reward":  3000, "max_reward": 4000,
        "min_exp":     3000, "max_exp":    4000,
        "description": "О твоём открытии пишут мировые СМИ.",
        "evolves_to":  "science_8", "req_level": 80,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_logistics_license", "📋 Лицензия логиста"),
    },
    "science_8": {
        "name":        "🏛 Академик Национальной Академии Наук",
        "branch":      "science", "grade": 8, "min_level": 80,
        "min_reward":  4800, "max_reward": 6400,
        "min_exp":     4800, "max_exp":    6400,
        "description": "Твоё кресло в Академии наук зарезервировано навсегда.",
        "evolves_to":  "science_9", "req_level": 100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_import_license", "🛃 Импортная лицензия"),
    },
    "science_9": {
        "name":        "🏆 Нобелевский лауреат из КТУ «Манас»",
        "branch":      "science", "grade": 9, "min_level": 100,
        "min_reward":  9500, "max_reward": 14000,
        "min_exp":     9500, "max_exp":    14000,
        "description": "Первый нобелевский лауреат в истории университета.",
        "evolves_to":  None,
        "special":     "science_king",
    },
# ══════════ ВЕТКА МЕДИА (3 перерождение) ══════════
    "media_1": {
        "name":        "📱 Тиктокер с 100 подписчиками",
        "branch":      "media", "grade": 1, "min_level": 1,
        "min_reward":  35, "max_reward":  80,
        "min_exp":     35, "max_exp":     80,
        "description": "Снимаешь ролики в общаге на телефон мамы.",
        "evolves_to":  "media_2", "req_level": 5,
    },
    "media_2": {
        "name":        "🎥 Ведущий студенческого YouTube-канала",
        "branch":      "media", "grade": 2, "min_level": 5,
        "min_reward":  100, "max_reward":  130,
        "min_exp":     100, "max_exp":    130,
        "description": "У тебя уже есть штатив и кольцевая лампа.",
        "evolves_to":  "media_3", "req_level": 10,
        "req_skill":   ("communication_level", 4),
    },
    "media_3": {
        "name":        "📸 Инстаграм-блогер с рекламными интеграциями",
        "branch":      "media", "grade": 3, "min_level": 10,
        "min_reward":  200, "max_reward": 410,
        "min_exp":     200, "max_exp":    410,
        "description": "Рекламодатели пишут первыми.",
        "evolves_to":  "media_4", "req_level": 20,
        "req_skill":   ("management_level", 3),
        "req_item":    ("has_laptop", "💻 Ноутбук"),
    },
    "media_4": {
        "name":        "🎙 Подкастер с миллионной аудиторией",
        "branch":      "media", "grade": 4, "min_level": 20,
        "min_reward":  650, "max_reward": 850,
        "min_exp":     650, "max_exp":    850,
        "description": "У тебя студия звукозаписи прямо в квартире.",
        "evolves_to":  "media_5", "req_level": 35,
        "req_skill":   ("management_level", 5),
        "req_item":    ("has_business_plan", "📊 Бизнес-план"),
    },
    "media_5": {
        "name":        "📺 Ведущий национального телешоу",
        "branch":      "media", "grade": 5, "min_level": 35,
        "min_reward":  1080, "max_reward": 1550,
        "min_exp":     1080, "max_exp":    1550,
        "description": "Тебя узнают таксисты и продавцы на базаре.",
        "evolves_to":  "media_6", "req_level": 50,
        "req_skill":   ("management_level", 7),
        "req_item":    ("has_dean_seal", "🔏 Декановская печать"),
    },
    "media_6": {
        "name":        "🌐 Основатель медиахолдинга",
        "branch":      "media", "grade": 6, "min_level": 50,
        "min_reward":  2050, "max_reward": 2950,
        "min_exp":     2050, "max_exp":    2950,
        "description": "У тебя своя сеть каналов и редакция.",
        "evolves_to":  "media_7", "req_level": 70,
        "req_skill":   ("management_level", 9),
        "req_item":    ("has_franchise_contract", "📜 Франшизный контракт"),
    },
    "media_7": {
        "name":        "🎬 Продюсер международных проектов",
        "branch":      "media", "grade": 7, "min_level": 70,
        "min_reward":  3500, "max_reward": 5000,
        "min_exp":     3500, "max_exp":    5000,
        "description": "Твои проекты показывают за пределами Кыргызстана.",
        "evolves_to":  "media_8", "req_level": 80,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_logistics_license", "📋 Лицензия логиста"),
    },
    "media_8": {
        "name":        "🏆 Обладатель премии «Золотой микрофон»",
        "branch":      "media", "grade": 8, "min_level": 80,
        "min_reward":  6000, "max_reward": 8000,
        "min_exp":     6000, "max_exp":    8000,
        "description": "Награда за вклад в медиаиндустрию региона.",
        "evolves_to":  "media_9", "req_level": 100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_import_license", "🛃 Импортная лицензия"),
    },
    "media_9": {
        "name":        "👑 Медиамагнат, чьё лицо знает вся Центральная Азия",
        "branch":      "media", "grade": 9, "min_level": 100,
        "min_reward":  12000, "max_reward": 18000,
        "min_exp":     12000, "max_exp":    18000,
        "description": "Твоё имя — синоним слова «медиа» в регионе.",
        "evolves_to":  None,
        "special":     "media_king",
    },
# ══════════ ВЕТКА ПОЛИТИКИ (4 перерождение) ══════════
    "politics_1": {
        "name":        "🗳 Волонтёр на выборах в студсовет",
        "branch":      "politics", "grade": 1, "min_level": 1,
        "min_reward":  40, "max_reward":  90,
        "min_exp":     40, "max_exp":     90,
        "description": "Раздаёшь листовки у главного корпуса.",
        "evolves_to":  "politics_2", "req_level": 5,
    },
    "politics_2": {
        "name":        "📋 Депутат студенческого парламента",
        "branch":      "politics", "grade": 2, "min_level": 5,
        "min_reward":  150, "max_reward": 250,
        "min_exp":     150, "max_exp":    250,
        "description": "Первая должность на пути к большой политике.",
        "evolves_to":  "politics_3", "req_level": 10,
        "req_skill":   ("communication_level", 4),
    },
    "politics_3": {
        "name":        "🏢 Помощник депутата Жогорку Кенеша",
        "branch":      "politics", "grade": 3, "min_level": 10,
        "min_reward":  330, "max_reward": 450,
        "min_exp":     330, "max_exp":    450,
        "description": "Носишь папки и учишься закулисной игре.",
        "evolves_to":  "politics_4", "req_level": 20,
        "req_skill":   ("management_level", 3),
        "req_item":    ("has_laptop", "💻 Ноутбук"),
    },
    "politics_4": {
        "name":        "🎖 Депутат Жогорку Кенеша",
        "branch":      "politics", "grade": 4, "min_level": 20,
        "min_reward":  620, "max_reward": 950,
        "min_exp":     620, "max_exp":    950,
        "description": "У тебя своё кресло в парламенте.",
        "evolves_to":  "politics_5", "req_level": 35,
        "req_skill":   ("management_level", 5),
        "req_item":    ("has_business_plan", "📊 Бизнес-план"),
    },
    "politics_5": {
        "name":        "🏛 Министр образования",
        "branch":      "politics", "grade": 5, "min_level": 35,
        "min_reward":  1520, "max_reward": 2050,
        "min_exp":     1520, "max_exp":    2050,
        "description": "Наконец-то можешь изменить систему изнутри.",
        "evolves_to":  "politics_6", "req_level": 50,
        "req_skill":   ("management_level", 7),
        "req_item":    ("has_dean_seal", "🔏 Декановская печать"),
    },
    "politics_6": {
        "name":        "🕴 Вице-премьер-министр",
        "branch":      "politics", "grade": 6, "min_level": 50,
        "min_reward":  2550, "max_reward": 3250,
        "min_exp":     2550, "max_exp":    3250,
        "description": "Второй человек в правительстве страны.",
        "evolves_to":  "politics_7", "req_level": 70,
        "req_skill":   ("management_level", 9),
        "req_item":    ("has_franchise_contract", "📜 Франшизный контракт"),
    },
    "politics_7": {
        "name":        "🌍 Полномочный представитель в ООН",
        "branch":      "politics", "grade": 7, "min_level": 70,
        "min_reward":  5000, "max_reward": 6400,
        "min_exp":     5000, "max_exp":    6400,
        "description": "Твой голос звучит на мировой арене.",
        "evolves_to":  "politics_8", "req_level": 80,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_logistics_license", "📋 Лицензия логиста"),
    },
    "politics_8": {
        "name":        "🏆 Премьер-министр Кыргызской Республики",
        "branch":      "politics", "grade": 8, "min_level": 80,
        "min_reward":  6700, "max_reward": 9600,
        "min_exp":     6700, "max_exp":    9600,
        "description": "Управляешь всей страной.",
        "evolves_to":  "politics_9", "req_level": 100,
        "req_skill":   ("management_level", 10),
        "req_item":    ("has_import_license", "🛃 Импортная лицензия"),
    },
    "politics_9": {
        "name":        "👑 Президент Кыргызской Республики",
        "branch":      "politics", "grade": 9, "min_level": 100,
        "min_reward":  15000, "max_reward": 20000,
        "min_exp":     15000, "max_exp":    20000,
        "description": "Вершина пути. Ты — Президент.",
        "evolves_to":  None,
        "special":     "politics_king",
    },
}

STARTER_JOB_KEYS = ["intel_1", "balance_1", "money_1"]
JOB_NAME_TO_KEY = {data["name"]: key for key, data in JOBS.items()}

def get_available_starter_jobs(user: dict) -> list[str]:
    rebirths = user.get("rebirths", 0)
    keys = list(STARTER_JOB_KEYS)
    for req, job_key in REBIRTH_STARTER_JOBS.items():
        if rebirths >= req:
            keys.append(job_key)
    return keys

# =====================================================================
# СЛУЧАЙНЫЕ СОБЫТИЯ ПРИ РАБОТЕ
# =====================================================================
WORK_EVENTS = {
    "intel": {
        "positive": [
            "🔥 Министерский грант! Твои знания оценили по-настоящему!",
            "🔥 Студент сдал на «А»! Родители принесли торт и конверт!",
            "🔥 Научная статья принята! Гонорар прилетел мгновенно!",
        ],
        "negative": [
            "⚠️ Списал не ту шпаргалку. Препод поставил пересдачу.",
            "⚠️ Студенты пожаловались! Штраф от деканата.",
            "⚠️ Потерял зачётку — пришлось восстанавливать за свой счёт.",
        ],
    },
    "balance": {
        "positive": [
            "🔥 Двойной заказ! Клиент доволен и щедро отсыпал сверху!",
            "🔥 VIP-тур! Богатые студенты оплатили трёхдневный тур!",
            "🔥 Реклама сработала! Поток клиентов удвоился!",
        ],
        "negative": [
            "⚠️ Прокол колеса в Джале. Ремонт съел часть выручки.",
            "⚠️ Опоздал на сдачу заказа — штраф от клиента.",
            "⚠️ Навигатор завёл не туда. Бензин сгорел впустую.",
        ],
    },
    "money": {
        "positive": [
            "🔥 Банкет у ректора! Чаевые бешеные!",
            "🔥 Блогер снял сторис о твоей точке — наплыв клиентов!",
            "🔥 Крупная партия симитов разошлась мгновенно!",
        ],
        "negative": [
            "⚠️ Санинспектор нагрянул. Штраф и нервы.",
            "⚠️ Просрочка поставки — пришлось выбросить партию.",
            "⚠️ Кофемашина сломалась. Ремонт за свой счёт.",
        ],
    },
"science": {
        "positive": [
            "🔥 Статья принята в топовый журнал! Гонорар пришёл сразу.",
            "🔥 Открытие подтвердилось! Дополнительный грант.",
            "🔥 Коллаборация с зарубежным вузом принесла бонус.",
        ],
        "negative": [
            "⚠️ Эксперимент провалился. Реагенты испорчены.",
            "⚠️ Рецензент завернул статью. Придётся переписывать.",
            "⚠️ Оборудование сломалось посреди опыта.",
        ],
    },
    "media": {
        "positive": [
            "🔥 Видео завирусилось! Рекламодатели в очереди.",
            "🔥 Коллаборация со звездой подняла охваты!",
            "🔥 Алгоритмы продвинули твой контент в топ.",
        ],
        "negative": [
            "⚠️ Аккаунт временно заблокировали за спам-жалобы.",
            "⚠️ Скандал в комментариях испортил репутацию.",
            "⚠️ Рекламодатель отказался от сделки в последний момент.",
        ],
    },
    "politics": {
        "positive": [
            "🔥 Закон приняли! Тебя хвалят в новостях.",
            "🔥 Успешные переговоры принесли бонус к бюджету.",
            "🔥 Электорат в восторге от твоей речи.",
        ],
        "negative": [
            "⚠️ Оппозиция устроила скандал в парламенте.",
            "⚠️ Утечка компромата подпортила рейтинг.",
            "⚠️ Реформа провалилась, пришлось оправдываться.",
        ],
    },
}

# =====================================================================
# CALLBACK DATA
# =====================================================================
class JobCallback(CallbackData, prefix="job"):
    job_key: str

class ShopCallback(CallbackData, prefix="shop"):
    item_key: str

class TrainCallback(CallbackData, prefix="train"):
    stat: str
    amount: int = 1

class UpgradeJobCallback(CallbackData, prefix="upjob"):
    job_key: str

class GiftCallback(CallbackData, prefix="gift"):
    gift_key: str
    target_id: int

class BunkerModeCallback(CallbackData, prefix="bunker_mode"):
    mode: str

class BunkerJoinCallback(CallbackData, prefix="bunker_join"):
    chat_id: int

class BunkerVoteCallback(CallbackData, prefix="bunker_vote"):
    target_id: int
    chat_id: int

# =====================================================================
# МАГАЗИН
# =====================================================================
SHOP_ITEMS = {
    "scooter": {
        "name":        "🛵 Скутер",
        "price":       1200,
        "flag":        "has_scooter",
        "description": "Нужен для ветки Баланс (10+ лвл). Даёт +1 к Вождению.",
        "skill_bonus": ("driving_level", 1),
    },
    "shaker": {
        "name":        "🍹 Проф. шейкер",
        "price":       800,
        "flag":        "has_shaker",
        "description": "Нужен для ветки Деньги (10+ лвл). Даёт +1 к Харизме.",
        "skill_bonus": ("service_level", 1),
    },
    "laptop": {
        "name":        "💻 Ноутбук",
        "price":       3500,
        "flag":        "has_laptop",
        "description": "Нужен для ветки Интеллект (10+ лвл). Даёт +1 к Коммуникации.",
        "skill_bonus": ("communication_level", 1),
    },
    "professor_badge": {
        "name":        "🎓 Профессорский значок",
        "price":       15000,
        "flag":        "has_professor_badge",
        "description": "Нужен для ветки Интеллект (50+ лвл). Даёт +1 к Менеджменту.",
        "skill_bonus": ("management_level", 1),
    },
    "logistics_license": {
        "name":        "📋 Лицензия логиста",
        "price":       18000,
        "flag":        "has_logistics_license",
        "description": "Нужна для ветки Баланс (50+ лвл). Даёт +1 к Организованности.",
        "skill_bonus": ("organization_level", 1),
    },
    "import_license": {
        "name":        "🛃 Импортная лицензия",
        "price":       20000,
        "flag":        "has_import_license",
        "description": "Нужна для ветки Деньги (50+ лвл). Даёт +1 к Менеджменту.",
        "skill_bonus": ("management_level", 1),
    },
    "dean_seal": {
        "name":        "🔏 Декановская печать",
        "price":       80000,
        "flag":        "has_dean_seal",
        "description": "Нужна для ветки Интеллект (70+ лвл). Даёт +2 к Менеджменту.",
        "skill_bonus": ("management_level", 2),
    },
    "business_plan": {
        "name":        "📊 Бизнес-план",
        "price":       90000,
        "flag":        "has_business_plan",
        "description": "Нужен для ветки Баланс (80+ лвл). Даёт +2 к Менеджменту.",
        "skill_bonus": ("management_level", 2),
    },
    "franchise_contract": {
        "name":        "📜 Франшизный контракт",
        "price":       100000,
        "flag":        "has_franchise_contract",
        "description": "Нужен для ветки Деньги (80+ лвл). Даёт +2 к Менеджменту.",
        "skill_bonus": ("management_level", 2),
    },
}

ASCENSION_UPGRADES = {
    "coin_boost": {
        "name": "💰 Печать Вознесения (монеты)",
        "label": "монеты",
        "base_cost": 12, "cost_growth": 9,
        "max_level": 30,
        "per_level_bonus": 5,   # +5% к монетам за уровень → максимум +150%
        "description": "Перманентный бонус к заработку. Не сбрасывается перерождением.",
    },
    "xp_boost": {
        "name": "✨ Печать Вознесения (опыт)",
        "label": "опыт",
        "base_cost": 12, "cost_growth": 9,
        "max_level": 30,
        "per_level_bonus": 5,   # максимум +150%
        "description": "Перманентный бонус к опыту. Не сбрасывается перерождением.",
    },
    "luck_boost": {
        "name": "🍀 Печать Вознесения (удача)",
        "label": "удача",
        "base_cost": 18, "cost_growth": 12,
        "max_level": 20,
        "per_level_bonus": 3,   # максимум +60 удачи
        "description": "Перманентная удача. Не сбрасывается перерождением.",
    },
    "energy_cap": {
        "name": "🔋 Ядро выносливости",
        "label": "макс. энергия",
        "base_cost": 22, "cost_growth": 14,
        "max_level": 15,
        "per_level_bonus": 50,  # максимум +750 к максимуму энергии
        "description": "Увеличивает максимум энергии перманентно.",
    },
    "hp_cap": {
        "name": "❤️ Ядро жизни",
        "label": "макс. HP",
        "base_cost": 22, "cost_growth": 14,
        "max_level": 15,
        "per_level_bonus": 50,  # максимум +750 к максимуму HP
        "description": "Увеличивает максимум здоровья перманентно.",
    },
    "start_capital": {
        "name": "🏦 Наследный капитал",
        "label": "стартовый баланс",
        "base_cost": 28, "cost_growth": 16,
        "max_level": 15,
        "per_level_bonus": 500,  # максимум +7500 к стартовым монетам при перерождении
        "description": "Увеличивает стартовый капитал при каждом перерождении.",
    },
}


def get_ascension_upgrades(user: dict) -> dict:
    import json
    raw = user.get("ascension_upgrades", "") or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def save_ascension_upgrades(user_id: int, upgrades: dict):
    import json
    update_user(user_id, ascension_upgrades=json.dumps(upgrades))


def get_ascension_upgrade_cost(cfg: dict, level: int) -> int:
    return cfg["base_cost"] + level * cfg["cost_growth"]


def do_buy_ascension_upgrade(user: dict, key: str) -> tuple[bool, str]:
    cfg = ASCENSION_UPGRADES.get(key)
    if not cfg:
        return False, "❌ Неизвестное улучшение."
    upgrades = get_ascension_upgrades(user)
    level = upgrades.get(key, 0)
    if level >= cfg["max_level"]:
        return False, f"✅ <b>{cfg['name']}</b> уже прокачано до максимума ({cfg['max_level']} ур.)."

    cost = get_ascension_upgrade_cost(cfg, level)
    if user.get("ascension_crystals", 0) < cost:
        return False, f"❌ Нужно <b>{cost}</b> 🌌 кристаллов, есть <b>{user.get('ascension_crystals', 0)}</b>."

    upgrades[key] = level + 1
    save_ascension_upgrades(user["user_id"], upgrades)
    update_user(user["user_id"], ascension_crystals=user.get("ascension_crystals", 0) - cost)
    return True, (
        f"✅ <b>{cfg['name']}</b> улучшено до уровня <b>{level + 1}</b>!\n"
        f"🌌 Потрачено: {cost} кристаллов."
    )


def get_ascension_upgrade_bonus(user: dict, key: str) -> int:
    cfg = ASCENSION_UPGRADES.get(key)
    if not cfg:
        return 0
    level = get_ascension_upgrades(user).get(key, 0)
    return level * cfg["per_level_bonus"]


def build_ascension_shop_text(user: dict) -> str:
    upgrades = get_ascension_upgrades(user)
    lines = [
        "🌌 <b>Алтарь Вознесения</b>\n",
        f"🌌 Кристаллов: <b>{user.get('ascension_crystals', 0)}</b>\n",
        "<i>Все улучшения здесь перманентны и НЕ сбрасываются перерождением!</i>\n",
    ]
    for key, cfg in ASCENSION_UPGRADES.items():
        level = upgrades.get(key, 0)
        if level >= cfg["max_level"]:
            cost_line = "МАКСИМУМ"
        else:
            cost_line = f"{get_ascension_upgrade_cost(cfg, level)} 🌌"
        current_bonus = level * cfg["per_level_bonus"]
        lines.append(
            f"<b>{cfg['name']}</b> — ур. {level}/{cfg['max_level']}\n"
            f"  <i>{cfg['description']}</i>\n"
            f"  Текущий бонус: +{current_bonus} к {cfg['label']}\n"
            f"  Следующий уровень: {cost_line}"
        )
    return "\n\n".join(lines)


def get_ascension_shop_keyboard(user: dict) -> InlineKeyboardMarkup:
    upgrades = get_ascension_upgrades(user)
    builder = InlineKeyboardBuilder()
    for key, cfg in ASCENSION_UPGRADES.items():
        level = upgrades.get(key, 0)
        if level >= cfg["max_level"]:
            continue
        cost = get_ascension_upgrade_cost(cfg, level)
        builder.button(text=f"⬆️ {cfg['name']} ({cost} 🌌)", callback_data=f"asc_upgrade:{key}")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("ascension"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in
                                  ("вознесение", "алтарь", "ascension")))
async def cmd_ascension_shop(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_ascension_shop_text(user), reply_markup=get_ascension_shop_keyboard(user))


@dp.callback_query(F.data.startswith("asc_upgrade:"))
async def cb_ascension_upgrade(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_buy_ascension_upgrade(user, key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_ascension_shop_text(updated), reply_markup=get_ascension_shop_keyboard(updated))

CONSUMABLES = {
    "water": {
        "name": "💧 Вода",
        "price": 20,
        "hp": 0, "energy": 10,
        "description": "Небольшой глоток сил.",
    },
    "plaster": {
        "name": "🩹 Пластырь",
        "price": 25,
        "hp": 15, "energy": 0,
        "description": "Заклеивает мелкие порезы.",
    },
    "bar": {
        "name": "🍫 Батончик",
        "price": 60,
        "hp": 0, "energy": 25,
        "description": "Быстрый перекус, даёт энергии.",
    },
    "energy_drink": {
        "name": "⚡ Энергетик",
        "price": 120,
        "hp": 0, "energy": 50,
        "description": "Хороший буст энергии.",
    },
    "bandage": {
        "name": "🩻 Бинт",
        "price": 100,
        "hp": 40, "energy": 0,
        "description": "Перевязывает средние раны.",
    },
    "lunch": {
        "name": "🍱 Сытный обед",
        "price": 200,
        "hp": 40, "energy": 40,
        "description": "Восстанавливает и силы, и здоровье.",
    },
    "first_aid_kit": {
        "name": "🚑 Автомобильная аптечка",
        "price": 350,
        "hp": 80, "energy": 0,
        "description": "Серьёзное лечение.",
    },
    "shawarma": {
        "name": "🌯 Шаурма из Джала",
        "price": 80,
        "hp": 20, "energy": 20,
        "description": "Классика КТУ. Восстанавливает и HP и энергию.",
    },
    "plov": {
        "name": "🍚 Плов",
        "price": 150,
        "hp": 50, "energy": 30,
        "description": "Настоящий кыргызский плов. Сытно и вкусно.",
    },
    "simit": {
        "name": "🥨 Симит",
        "price": 30,
        "hp": 10, "energy": 10,
        "description": "Турецкий бублик из коридора Манаса.",
    },
    "chorbo": {
        "name": "🍲 Чорбо",
        "price": 120,
        "hp": 60, "energy": 0,
        "description": "Наваристый суп из столовой. Лечит хорошо.",
    },
    "tea": {
        "name": "🍵 Турецкий чай",
        "price": 25,
        "hp": 0, "energy": 15,
        "description": "Маленький стакан, большая энергия.",
    },
    "lagman": {
        "name": "🍜 Лагман",
        "price": 180,
        "hp": 40, "energy": 60,
        "description": "Густая лапша. Надолго заряжает.",
    },
    "caffeine": {
        "name": "💊 Кофеин в таблетках",
        "price": 400,
        "hp": 0, "energy": 100,
        "description": "Мощный энергетический заряд.",
    },
    "ration": {
        "name": "🪖 Армейский сухпаёк",
        "price": 700,
        "hp": 100, "energy": 100,
        "description": "Полноценное восстановление в полевых условиях.",
    },
    "elixir": {
        "name": "✨ Эликсир бодрости",
        "price": 1500,
        "hp": 9999, "energy": 9999,
        "description": "Полностью восстанавливает HP и Энергию.",
    },
}

BOSSES = {
    "shaurma_ghost": {
        "name": "🌯 Дух прокисшей шаурмы из Джала",
        "min_level": 3,
        "cooldown_hours": 2,
        "energy_cost": 20,
        "power_threshold": 25,
        "reward_shards_min": 10, "reward_shards_max": 20,
        "description": "Легендарная шаурма 2019 года так и не была доедена. Теперь её дух бродит по коридорам, ищет второго едока.",
        "win_text": "Ты выдержал запах и не поморщился. Дух шаурмы уважительно растворился в паре специй.",
        "lose_text": "Тебя стошнило прямо у входа в столовую. Позорное отступление под смех однокурсников.",
    },
    "dorm_ghost": {
        "name": "🏚 Дух общаги на Джале",
        "min_level": 5,
        "cooldown_hours": 4,
        "energy_cost": 25,
        "power_threshold": 40,
        "reward_shards_min": 15, "reward_shards_max": 30,
        "description": "По ночам в общаге кто-то двигает тапочки и включает чайник. Студенты боятся идти на кухню в одиночку.",
        "win_text": "Дух признал в тебе своего и растворился, оставив горсть блестящих осколков.",
        "lose_text": "Дух напугал тебя так, что ты забыл, зачем вообще пришёл. Отступление.",
    },
    "dekanat_phantom": {
        "name": "📋 Призрак деканата с ведомостями",
        "min_level": 15,
        "cooldown_hours": 8,
        "energy_cost": 30,
        "power_threshold": 100,
        "reward_shards_min": 30, "reward_shards_max": 55,
        "description": "Бумажный дух бродит по коридорам в поисках должников по пересдачам. Ведомость в его руках никогда не заканчивается.",
        "win_text": "Ты вырвал ведомость и сжёг её у фонтана. Призрак развеялся с воплем 'ну ладно, зачёт автоматом!'",
        "lose_text": "Призрак вписал тебя в список на отчисление. К счастью, понарошку. Пока что.",
    },
    "biblioteka_silence": {
        "name": "📚 Библиотечный Молчун",
        "min_level": 22,
        "cooldown_hours": 10,
        "energy_cost": 32,
        "power_threshold": 160,
        "reward_shards_min": 40, "reward_shards_max": 70,
        "description": "Существо из читального зала. Шипит «тс-с-с» громче любого шума и штрафует за скрип стула.",
        "win_text": "Ты сдал книгу без единого шороха. Молчун одобрительно кивнул и исчез между стеллажами.",
        "lose_text": "Ты чихнул в самый неподходящий момент. Молчун выгнал тебя из читального зала на неделю.",
    },
    "somsynav_proctor": {
        "name": "🕴 Проктор Сом-сынава",
        "min_level": 30,
        "cooldown_hours": 12,
        "energy_cost": 35,
        "power_threshold": 220,
        "reward_shards_min": 55, "reward_shards_max": 90,
        "description": "Легендарный надзиратель экзаменов, видящий шпаргалки сквозь стены. Ходят слухи, что он не моргает уже 12 лет.",
        "win_text": "Ты выдержал его взгляд, не моргнув. Проктор молча кивнул и исчез в облаке мела.",
        "lose_text": "Проктор заметил твою шпаргалку раньше, чем ты её достал. Позорное изгнание из аудитории.",
    },
    "stipendiya_demon": {
        "name": "💸 Демон невыплаченной стипендии",
        "min_level": 40,
        "cooldown_hours": 16,
        "energy_cost": 37,
        "power_threshold": 330,
        "reward_shards_min": 140, "reward_shards_max": 220,
        "description": "Обитает в бухгалтерии. Держит стипендии всего курса заложниками уже третий месяц подряд под предлогом «завтра будет».",
        "win_text": "Ты добыл справку с тремя подписями и печатью. Демон нехотя подписал перевод — стипендия пошла!",
        "lose_text": "Демон отправил тебя за четвёртой подписью в другой корпус. Круг бюрократии замкнулся.",
    },
    "minobr_commission": {
        "name": "🏛 Комиссия Минобра",
        "min_level": 50,
        "cooldown_hours": 24,
        "energy_cost": 40,
        "power_threshold": 420,
        "reward_shards_min": 100, "reward_shards_max": 160,
        "description": "Внезапная проверка из столицы. Три человека в костюмах, ни один не улыбнулся с 2019 года.",
        "win_text": "Комиссия не нашла нарушений. Более того — один из них тайком спросил, где тут столовая с чорбо.",
        "lose_text": "Комиссия составила акт на 40 страниц. Читать его придётся весь семестр.",
    },
    "rektorat_dracon": {
        "name": "🐲 Дракон приёмной ректора",
        "min_level": 65,
        "cooldown_hours": 30,
        "energy_cost": 45,
        "power_threshold": 580,
        "reward_shards_min": 260, "reward_shards_max": 400,
        "description": "Охраняет вход в кабинет ректора. Дышит не огнём, а бюрократическими отписками — обжигает не хуже пламени.",
        "win_text": "Ты прошёл мимо дракона с папкой из 12 согласований. Он молча посторонился — редчайшая честь.",
        "lose_text": "Дракон завернул тебя обратно с формулировкой «зайдите после обеда». Обед так и не наступил.",
    },
    "manas_spirit": {
        "name": "🐎 Дух великого эпоса Манас",
        "min_level": 80,
        "cooldown_hours": 48,
        "energy_cost": 50,
        "power_threshold": 750,
        "reward_shards_min": 200, "reward_shards_max": 320,
        "description": "Финальное испытание. Дух самого эпоса является лишь тем, кто прошёл путь от новичка до легенды КТУ.",
        "win_text": "Дух Манаса склонил голову. 'Ты достоин носить имя батыра университета.' Осколки эпоса теперь твои.",
        "lose_text": "Дух эпоса лишь усмехнулся твоей самонадеянности. Возвращайся, когда станешь сильнее.",
    },
    "gak_commission": {
        "name": "👁 Тайная комиссия ГАК",
        "min_level": 100,
        "cooldown_hours": 60,
        "energy_cost": 55,
        "power_threshold": 950,
        "reward_shards_min": 380, "reward_shards_max": 550,
        "description": "Секретная государственная аттестационная комиссия, о которой ходят только легенды. Видит насквозь любую дипломную работу и любую судьбу.",
        "win_text": "Комиссия встала и молча зааплодировала. Такого защиты диплома здесь не видели никогда.",
        "lose_text": "Председатель комиссии произнёс лишь одно слово: 'Пересдача'. Зал погрузился в тишину.",
    },
}
BOSS_ITEMS = {
    # ── Обычные ──
    "old_conspectus": {
        "name": "📓 Конспект прошлого курса", "rarity": "common", "rarity_label": "⚪ Обычный",
        "bonus_type": "xp", "base_bonus": 4,
        "description": "Мятые записи неизвестного отличника. Помогают учиться быстрее.",
        "weight": 45, "upgrade_cost_base": 150,
    },
    "ktu_scarf": {
        "name": "🧣 Шарф КТУ «Манас»", "rarity": "common", "rarity_label": "⚪ Обычный",
        "bonus_type": "coins", "base_bonus": 4,
        "description": "Официальный мерч. Почему-то придаёт уверенности на подработках.",
        "weight": 45, "upgrade_cost_base": 150,
    },
    # ── Редкие ──
    "starosta_watch": {
        "name": "⌚ Часы старосты группы", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "xp", "base_bonus": 8,
        "description": "Всегда показывают, сколько осталось до конца пары. И до конца твоего терпения.",
        "weight": 22, "upgrade_cost_base": 300,
    },
    "dean_beads": {
        "name": "📿 Чётки декана", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "luck", "base_bonus": 6,
        "description": "Помогают декану сохранять спокойствие. Тебе — тоже.",
        "weight": 20, "upgrade_cost_base": 300,
    },
    # ── Эпические ──
    "kementai_cloak": {
        "name": "🥋 Кементай — войлочный плащ кочевника", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "luck", "base_bonus": 12,
        "description": "Традиционный плащ пастухов Тянь-Шаня. Защищает от невзгод и плохих оценок.",
        "weight": 9, "upgrade_cost_base": 700,
    },
    "akinak_sword": {
        "name": "🗡 Акинак — меч древних кочевников", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "coins", "base_bonus": 14,
        "description": "Найден в степи под Бишкеком. Работодатели почему-то боятся торговаться при виде него.",
        "weight": 8, "upgrade_cost_base": 700,
    },
    # ── Легендарные ──
    "manas_bow": {
        "name": "🏹 Лук Манаса", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "base_bonus": 20,
        "description": "Оружие самого батыра из эпоса. Монеты и опыт текут рекой.",
        "weight": 2, "upgrade_cost_base": 1500,
    },
    "rector_crown": {
        "name": "👑 Корона Ректора", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "base_bonus": 22,
        "description": "Символ абсолютной власти в стенах КТУ. Все двери открыты.",
        "weight": 1, "upgrade_cost_base": 1500,
    },
# ── Эксклюзивные трофеи новых боссов ──
    "shaurma_amulet": {
        "name": "🥙 Амулет прокисшей шаурмы", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "luck", "base_bonus": 7,
        "description": "Выпадает только с 🌯 Духа прокисшей шаурмы. Странно пахнет, но приносит удачу.",
        "weight": 15, "upgrade_cost_base": 300,
        "boss_only": "shaurma_ghost",
    },
    "tishina_bloknot": {
        "name": "📓 Блокнот абсолютной тишины", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "xp", "base_bonus": 13,
        "description": "Выпадает только с 📚 Библиотечного Молчуна. Записи в нём появляются сами по себе.",
        "weight": 7, "upgrade_cost_base": 700,
        "boss_only": "biblioteka_silence",
    },
    "spravka_pechati": {
        "name": "📑 Справка с тремя печатями", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "coins", "base_bonus": 15,
        "description": "Выпадает только с 💸 Демона невыплаченной стипендии. Открывает любую кассу бухгалтерии.",
        "weight": 7, "upgrade_cost_base": 700,
        "boss_only": "stipendiya_demon",
    },
    "draconya_cheshuya": {
        "name": "🐲 Чешуя дракона приёмной", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "base_bonus": 24,
        "description": "Выпадает только с 🐲 Дракона приёмной ректора. Секретари теперь боятся тебя, а не наоборот.",
        "weight": 1, "upgrade_cost_base": 1800,
        "boss_only": "rektorat_dracon",
    },
    "pechat_gak": {
        "name": "👁 Печать ГАК", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "base_bonus": 30,
        "description": "Выпадает только с 👁 Тайной комиссии ГАК. Сильнейший артефакт университета «Манас».",
        "weight": 1, "upgrade_cost_base": 2200,
        "boss_only": "gak_commission",
    },
}

BOSS_ITEM_BONUS_LABELS = {
    "coins": "💰 монеты с работы",
    "xp":    "✨ опыт с работы",
    "luck":  "🍀 удача",
    "both":  "💰 монеты И ✨ опыт с работы",
}

def get_boss_item_bonus_text(item_key: str, level: int = 1) -> str:
    """Возвращает понятную строку бонуса предмета с учётом уровня улучшения."""
    item = BOSS_ITEMS.get(item_key)
    if not item:
        return ""
    bonus = item["base_bonus"] + (level - 1) * max(1, item["base_bonus"] // 4)
    label = BOSS_ITEM_BONUS_LABELS.get(item["bonus_type"], "бонус")
    return f"+{bonus}% к {label}"

RARITY_ORDER = ["common", "rare", "epic", "legendary"]

# =====================================================================
# МИРОВЫЕ БОССЫ
# =====================================================================
import json as _json_wb

WORLD_BOSSES = {
    "khan_specter": {
        "name": "👻 Дух Хана Степи", "emoji": "👻",
        "max_hp": 500000, "min_level": 15,
        "attack_energy_cost": 25, "attack_cooldown": 1800, "duration_hours": 12,
        "description": "Древний дух пробудился в степях под Бишкеком. Собери всех студентов, чтобы одолеть его!",
        "win_text": "Общими усилиями студенты КТУ изгнали дух хана обратно в степь!",
        "escape_text": "Дух хана слишком силён — он растворился в степи.",
        "reward_coin_mult": 3.0, "reward_exp_mult": 3.0, "top_bonus_pct": 50,
    },
    "manas_avatar": {
        "name": "🐎 Аватар Манаса", "emoji": "🐎",
        "max_hp": 2000000, "min_level": 40,
        "attack_energy_cost": 35, "attack_cooldown": 2400, "duration_hours": 18,
        "description": "Дух великого эпоса воплотился, чтобы испытать новое поколение.",
        "win_text": "Аватар Манаса склонил голову перед объединённой мощью студентов!",
        "escape_text": "Аватар Манаса счёл вас недостойными и растворился в свете.",
        "reward_coin_mult": 5.0, "reward_exp_mult": 5.0, "top_bonus_pct": 75,
    },
    "gak_overlord": {
        "name": "👁 Верховная Комиссия ГАК", "emoji": "👁",
        "max_hp": 5000000, "min_level": 70,
        "attack_energy_cost": 45, "attack_cooldown": 3000, "duration_hours": 24,
        "description": "Финальный экзамен для всего университета сразу.",
        "win_text": "Комиссия единогласно поставила всем «отлично». Легендарная победа!",
        "escape_text": "Комиссия перенесла защиту на следующий семестр...",
        "reward_coin_mult": 8.0, "reward_exp_mult": 8.0, "top_bonus_pct": 100,
    },
    "boss_kyraata": {
        "name": "🐻 Босс Кыраата", "emoji": "🐻",
        "max_hp": 1000000, "min_level": 20,
        "attack_energy_cost": 30, "attack_cooldown": 2000, "duration_hours": 14,
        "description": "Босс Кыраата захватил весь кыраат, спаси кыраат от него!",
        "win_text": "Общими усилиями студенты КТУ изгнали Босса Кыраата обратно в кладовку Кыраата!",
        "escape_text": "Босс Кыраата слишком силён — он ушел... но он вернеться.",
        "reward_coin_mult": 4.0, "reward_exp_mult": 4.0, "top_bonus_pct": 60,
    },
}


def get_active_world_boss() -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM world_boss WHERE status = 'active' ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
    return dict(row) if row else None


def get_world_boss_by_id(boss_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM world_boss WHERE id = %s", (boss_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def save_world_boss(boss_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = %s" for k in kwargs)
    values = list(kwargs.values()) + [boss_id]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE world_boss SET {fields} WHERE id = %s", values)
            conn.commit()


def spawn_world_boss(boss_key: str) -> dict | None:
    cfg = WORLD_BOSSES.get(boss_key)
    if not cfg:
        return None
    existing = get_active_world_boss()
    if existing and existing["current_hp"] > 0 and int(time.time()) <= existing["ends_at"]:
        return None
    now = int(time.time())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO world_boss (boss_key, max_hp, current_hp, started_at, ends_at, participants, status)
                   VALUES (%s, %s, %s, %s, %s, '{}', 'active') RETURNING id""",
                (boss_key, cfg["max_hp"], cfg["max_hp"], now, now + cfg["duration_hours"] * 3600)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return get_world_boss_by_id(new_id)


def get_wb_participants(boss: dict) -> dict:
    try:
        return _json_wb.loads(boss.get("participants", "") or "{}")
    except Exception:
        return {}


def calc_world_boss_damage(user: dict) -> int:
    base = (user.get("agility", 1) + user.get("endurance", 1) +
            user.get("charisma", 1) + user.get("intellect", 1)) * 3
    luck_bonus = get_total_luck(user) * 3
    level_bonus = user["level"] * 2
    roll = random.randint(1, 100)
    return base + luck_bonus + level_bonus + roll


async def resolve_world_boss(boss: dict, defeated: bool):
    cfg = WORLD_BOSSES.get(boss["boss_key"])
    save_world_boss(boss["id"], status="defeated" if defeated else "escaped")
    if not cfg:
        return
    participants = get_wb_participants(boss)
    if not participants:
        text = f"⏰ <b>{cfg['name']}</b> исчез — никто не успел вступить в бой."
        for chat_id in list(registered_chats):
            try:
                await bot.send_message(chat_id, text)
            except Exception:
                pass
        return

    total_damage = sum(p.get("damage", 0) for p in participants.values())
    top_uid, top_data = max(participants.items(), key=lambda x: x[1].get("damage", 0))
    result_mult = 1.0 if defeated else 0.3

    for uid_str, pdata in participants.items():
        uid = int(uid_str)
        dmg = pdata.get("damage", 0)
        if total_damage <= 0 or dmg <= 0:
            continue
        share = dmg / total_damage
        base_coins = max(20, int(cfg["max_hp"] * cfg["reward_coin_mult"] * share * 0.01 * result_mult))
        base_exp = max(10, int(cfg["max_hp"] * cfg["reward_exp_mult"] * share * 0.01 * result_mult))

        u = get_user(uid)
        if not u:
            continue
        is_top = (uid_str == top_uid)
        if is_top:
            base_coins = int(base_coins * (1 + cfg["top_bonus_pct"] / 100))
            base_exp = int(base_exp * (1 + cfg["top_bonus_pct"] / 100))

        coins = apply_full_coin_bonus(u, base_coins)
        exp = apply_combined_xp_bonus(u, base_exp)
        update_user(uid, balance=u["balance"] + coins, exp=u["exp"] + exp)
        contribute_faculty_points(uid, max(5, dmg // 1000))
        fresh = get_user(uid)
        if fresh:
            auto_level_up(fresh)
            check_and_grant_achievements(fresh)

        try:
            crown = " 👑 (лучший урон!)" if is_top else ""
            await bot.send_message(
                uid,
                f"{'🏆' if defeated else '💨'} <b>{cfg['name']} {'повержен' if defeated else 'сбежал'}!</b>{crown}\n\n"
                f"⚔️ Твой урон: <b>{dmg}</b> ({share*100:.1f}%)\n"
                f"💰 Награда: +{coins} монет\n✨ Опыт: +{exp}"
            )
        except Exception:
            pass

    top_name = (get_user(int(top_uid)) or {}).get("username") or top_uid
    summary = (
        f"{'🏆 <b>МИРОВОЙ БОСС ПОВЕРЖЕН!</b>' if defeated else '💨 <b>Мировой босс сбежал...</b>'}\n\n"
        f"{cfg['name']}\n<i>{cfg['win_text'] if defeated else cfg['escape_text']}</i>\n\n"
        f"👥 Участников: <b>{len(participants)}</b>\n"
        f"💥 Общий урон: <b>{total_damage}</b> / {cfg['max_hp']}\n"
        f"👑 Лучший урон: <b>{top_name}</b> ({top_data.get('damage', 0)})\n\n"
        f"🎁 Награды разосланы всем участникам в личные сообщения!"
    )
    for chat_id in list(registered_chats):
        try:
            await bot.send_message(chat_id, summary)
        except Exception:
            pass


def do_attack_world_boss_sync(user: dict, boss: dict) -> tuple[bool, str, bool]:
    cfg = WORLD_BOSSES.get(boss["boss_key"])
    if not cfg:
        return False, "❌ Ошибка данных босса.", False
    if user["level"] < cfg["min_level"]:
        return False, f"❌ Нужен уровень <b>{cfg['min_level']}</b>.", False
    if is_incapacitated(user):
        return False, get_incapacitated_message(user), False

    participants = get_wb_participants(boss)
    uid_str = str(user["user_id"])
    pdata = participants.get(uid_str, {"damage": 0, "last_attack": 0})
    now = int(time.time())
    elapsed = now - pdata.get("last_attack", 0)
    if elapsed < cfg["attack_cooldown"]:
        remaining = cfg["attack_cooldown"] - elapsed
        return False, f"⏳ Атаковать снова можно через <b>{remaining // 60}</b> мин.", False

    energy_cost = apply_energy_discount(cfg["attack_energy_cost"])
    if user["energy"] < energy_cost:
        return False, f"😴 Недостаточно энергии! Нужно {energy_cost} ⚡.", False

    new_energy = max(0, user["energy"] - energy_cost)
    update_user(user["user_id"], energy=new_energy)

    damage = calc_world_boss_damage(user)
    pdata["damage"] = pdata.get("damage", 0) + damage
    pdata["last_attack"] = now
    participants[uid_str] = pdata

    new_hp = max(0, boss["current_hp"] - damage)
    save_world_boss(boss["id"], current_hp=new_hp, participants=_json_wb.dumps(participants))
    change_reputation(user["user_id"], +1)

    defeated_now = new_hp <= 0
    hp_pct = int(new_hp / cfg["max_hp"] * 100)
    text = (
        f"⚔️ Ты атаковал <b>{cfg['name']}</b>!\n\n"
        f"💥 Урон: <b>{damage}</b>\n"
        f"❤️ HP босса: <b>{new_hp}</b> / {cfg['max_hp']} ({hp_pct}%)\n"
        f"⚡ Энергия: <b>{new_energy}</b> (-{energy_cost})"
    )
    return True, text, defeated_now


def build_world_boss_text(boss: dict | None) -> str:
    if not boss:
        return "😴 Сейчас нет активного мирового босса. Ожидайте появления!"
    cfg = WORLD_BOSSES.get(boss["boss_key"])
    if not cfg:
        return "⚠️ Ошибка данных босса."
    participants = get_wb_participants(boss)
    hp_pct = max(0, int(boss["current_hp"] / cfg["max_hp"] * 100))
    bar = "█" * (hp_pct // 5) + "░" * (20 - hp_pct // 5)
    remaining = max(0, boss["ends_at"] - int(time.time()))
    h, m = remaining // 3600, (remaining % 3600) // 60
    return (
        f"{cfg['emoji']} <b>{cfg['name']}</b>\n\n<i>{cfg['description']}</i>\n\n"
        f"❤️ HP: [{bar}] {hp_pct}%\n   {boss['current_hp']} / {cfg['max_hp']}\n\n"
        f"👥 Атаковало: <b>{len(participants)}</b> игроков\n"
        f"⏳ Осталось: <b>{h}ч {m}мин</b>\n\n"
        f"🔒 Мин. уровень: {cfg['min_level']} | ⚡ {cfg['attack_energy_cost']} за атаку"
    )


@dp.message(Command("world_boss"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("мировой босс", "мб", "world boss")))
async def cmd_world_boss(message: Message):
    boss = get_active_world_boss()
    if boss and (int(time.time()) > boss["ends_at"] or boss["current_hp"] <= 0):
        await resolve_world_boss(boss, defeated=boss["current_hp"] <= 0)
        boss = None
    builder = InlineKeyboardBuilder()
    if boss:
        builder.button(text="⚔️ Атаковать!", callback_data=f"wb_attack:{boss['id']}")
    await message.answer(build_world_boss_text(boss), reply_markup=builder.as_markup() if boss else None)


@dp.callback_query(F.data.startswith("wb_attack:"))
async def cb_world_boss_attack(callback: CallbackQuery):
    boss_id = int(callback.data.split(":")[1])
    boss = get_world_boss_by_id(boss_id)
    if not boss or boss["status"] != "active":
        await callback.answer("Этот босс уже недоступен.", show_alert=True)
        return
    if int(time.time()) > boss["ends_at"] or boss["current_hp"] <= 0:
        await callback.answer()
        await resolve_world_boss(boss, defeated=boss["current_hp"] <= 0)
        await callback.message.edit_text(build_world_boss_text(None))
        return

    user = get_user_safe(callback.from_user.id)
    success, text, defeated_now = do_attack_world_boss_sync(user, boss)
    await callback.answer()
    await callback.message.answer(text)

    if success and defeated_now:
        fresh_boss = get_world_boss_by_id(boss_id)
        await resolve_world_boss(fresh_boss, defeated=True)
        await callback.message.edit_text(build_world_boss_text(None))
    elif success:
        updated_boss = get_world_boss_by_id(boss_id)
        builder = InlineKeyboardBuilder()
        builder.button(text="⚔️ Атаковать!", callback_data=f"wb_attack:{boss_id}")
        try:
            await callback.message.edit_text(build_world_boss_text(updated_boss), reply_markup=builder.as_markup())
        except Exception:
            pass


@dp.message(Command("spawn_world_boss"))
async def cmd_spawn_world_boss(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    if len(parts) != 2 or parts[1] not in WORLD_BOSSES:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in WORLD_BOSSES.items())
        await message.answer(f"❌ Формат: <code>/spawn_world_boss ключ</code>\n\n{keys}")
        return
    boss = spawn_world_boss(parts[1])
    if not boss:
        await message.answer("⚠️ Уже есть активный мировой босс!")
        return
    cfg = WORLD_BOSSES[parts[1]]
    text = (
        f"🚨 <b>ПОЯВИЛСЯ МИРОВОЙ БОСС!</b>\n\n{cfg['emoji']} <b>{cfg['name']}</b>\n<i>{cfg['description']}</i>\n\n"
        f"❤️ HP: <b>{cfg['max_hp']}</b>\n⏳ Время на бой: <b>{cfg['duration_hours']}ч</b>\n\n"
        f"Пишите <b>мировой босс</b>, чтобы атаковать!"
    )
    for chat_id in list(registered_chats):
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            pass
    await message.answer(f"✅ Босс {cfg['name']} заспавнен и разослан по чатам.")


@dp.message(Command("end_world_boss"))
async def cmd_end_world_boss(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    boss = get_active_world_boss()
    if not boss:
        await message.answer("❌ Нет активного мирового босса.")
        return
    await resolve_world_boss(boss, defeated=boss["current_hp"] <= 0)
    await message.answer("✅ Мировой босс завершён вручную.")


async def auto_world_boss_scheduler():
    await asyncio.sleep(30)
    while True:
        boss = get_active_world_boss()
        if boss and (int(time.time()) > boss["ends_at"] or boss["current_hp"] <= 0):
            await resolve_world_boss(boss, defeated=boss["current_hp"] <= 0)
            boss = None
        if not boss and random.random() < 0.10:
            key = random.choice(list(WORLD_BOSSES.keys()))
            new_boss = spawn_world_boss(key)
            if new_boss:
                cfg = WORLD_BOSSES[key]
                text = (
                    f"🚨 <b>ПОЯВИЛСЯ МИРОВОЙ БОСС!</b>\n\n{cfg['emoji']} <b>{cfg['name']}</b>\n<i>{cfg['description']}</i>\n\n"
                    f"❤️ HP: <b>{cfg['max_hp']}</b>\n⏳ Время на бой: <b>{cfg['duration_hours']}ч</b>\n\n"
                    f"Пишите <b>мировой босс</b>, чтобы атаковать!"
                )
                for chat_id in list(registered_chats):
                    try:
                        await bot.send_message(chat_id, text)
                    except Exception:
                        pass
        await asyncio.sleep(1800)

VEHICLES = {
    "bicycle": {
        "name": "🚲 Велосипед активиста",
        "price": 8000, "xp_per_hour": 300, "min_level": 40,
        "description": "Катаешься между корпусами и незаметно набираешься опыта.",
    },
    "moped": {
        "name": "🛵 Мопед курьера",
        "price": 20000, "xp_per_hour": 700, "min_level": 45,
        "description": "Развозишь заказы и попутно учишься на ходу.",
    },
    "sedan": {
        "name": "🚗 Подержанный седан",
        "price": 45000, "xp_per_hour": 1500, "min_level": 55,
        "description": "Слушаешь аудиокниги по дороге на пары.",
    },
    "suv": {
        "name": "🚙 Внедорожник",
        "price": 90000, "xp_per_hour": 3000, "min_level": 65,
        "description": "Возишь профессоров на конференции — знания сами липнут.",
    },
    "sportscar": {
        "name": "🏎 Спорткар",
        "price": 200000, "xp_per_hour": 6000, "min_level": 80,
        "description": "Статус привлекает нужных людей и нужные знания.",
    },
    "private_jet": {
        "name": "✈️ Личный самолёт",
        "price": 500000, "xp_per_hour": 15000, "min_level": 100,
        "description": "Летаешь на конференции по всему миру.",
    },
}
VEHICLE_XP_CAP_HOURS = 12

def get_user_vehicles(user: dict) -> dict:
    import json
    raw = user.get("vehicles", "") or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}

def save_user_vehicles(user_id: int, vehicles: dict):
    import json
    update_user(user_id, vehicles=json.dumps(vehicles))

def get_total_xp_per_hour(user: dict) -> int:
    v = get_user_vehicles(user)
    return sum(VEHICLES[k]["xp_per_hour"] for k in v if k in VEHICLES)

def build_vehicles_text(user: dict) -> str:
    v = get_user_vehicles(user)
    total = get_total_xp_per_hour(user)
    now = int(time.time())
    last = user.get("last_xp_collect", 0) or now
    elapsed_h = min((now - last) / 3600, VEHICLE_XP_CAP_HOURS)
    pending = apply_combined_xp_bonus(user, int(total * elapsed_h))

    lines = [
        "🚗 <b>Гараж — пассивный опыт (40+ ур.)</b>\n",
        f"✨ Опыта в час: <b>{total}</b>",
        f"📦 Накоплено к сбору: <b>{pending}</b> (макс. {VEHICLE_XP_CAP_HOURS}ч)\n",
    ]
    if not v:
        lines.append("Транспорта пока нет.\n")
    else:
        lines.append("<b>Твой транспорт:</b>")
        for k in v:
            if k in VEHICLES:
                lines.append(f"  • {VEHICLES[k]['name']} — {VEHICLES[k]['xp_per_hour']} XP/ч")
        lines.append("")

    lines.append("<b>Доступно для покупки:</b>")
    for k, veh in VEHICLES.items():
        if k in v:
            continue
        lock = "" if user["level"] >= veh["min_level"] else f" 🔒 (нужен {veh['min_level']} ур.)"
        lines.append(
            f"  • {veh['name']} — {veh['price']} мон., {veh['xp_per_hour']} XP/ч{lock}\n"
            f"    <i>{veh['description']}</i>"
        )
    return "\n".join(lines)

def get_vehicles_keyboard(user: dict) -> InlineKeyboardMarkup:
    v = get_user_vehicles(user)
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ Собрать опыт", callback_data="xp_collect")
    for k, veh in VEHICLES.items():
        if k in v or user["level"] < veh["min_level"]:
            continue
        builder.button(text=f"🛒 {veh['name']} — {veh['price']} мон.", callback_data=f"vehicle_buy:{k}")
    builder.adjust(1)
    return builder.as_markup()

def do_buy_vehicle(user: dict, key: str) -> tuple[bool, str]:
    veh = VEHICLES.get(key)
    if not veh:
        return False, "❌ Такого транспорта нет."
    v = get_user_vehicles(user)
    if key in v:
        return False, "У тебя уже есть этот транспорт!"
    if user["level"] < veh["min_level"]:
        return False, f"❌ Нужен уровень <b>{veh['min_level']}</b>."
    _, _, _, ev_discount = get_event_multipliers()
    price = int(veh["price"] * (1 - ev_discount / 100))
    if user["balance"] < price:
        return False, f"❌ Недостаточно монет. Нужно {price}."
    v[key] = int(time.time())
    save_user_vehicles(user["user_id"], v)
    last = user.get("last_xp_collect", 0) or int(time.time())
    update_user(user["user_id"], balance=user["balance"] - price, last_xp_collect=last or int(time.time()))
    return True, f"✅ Куплено: {veh['name']}!\n💰 Потрачено: {price} монет."

def do_collect_vehicle_xp(user: dict) -> tuple[bool, str]:
    total = get_total_xp_per_hour(user)
    if total == 0:
        return False, "❌ У тебя нет транспорта, дающего опыт."
    now = int(time.time())
    last = user.get("last_xp_collect", 0) or now
    elapsed_h = min((now - last) / 3600, VEHICLE_XP_CAP_HOURS)
    pending = apply_combined_xp_bonus(user, int(total * elapsed_h))
    if pending <= 0:
        return False, "⏳ Пока нечего собирать."
    new_exp = user["exp"] + pending
    update_user(user["user_id"], exp=new_exp, last_xp_collect=now)
    user = {**user, "exp": new_exp}
    user, level_msgs = auto_level_up(user)
    level_block = "".join(level_msgs)
    return True, f"✨ Собрано опыта: <b>+{pending}</b>!{level_block}"

@dp.message(Command("vehicles"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("транспорт","авто", "гараж", "vehicles")))
async def cmd_vehicles(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    if user["level"] < 40:
        await message.answer("🔒 Гараж открывается с <b>40</b> уровня.")
        return
    await message.answer(build_vehicles_text(user), reply_markup=get_vehicles_keyboard(user))

@dp.callback_query(F.data == "xp_collect")
async def cb_xp_collect(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    success, text = do_collect_vehicle_xp(user)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_vehicles_text(updated), reply_markup=get_vehicles_keyboard(updated))

@dp.callback_query(F.data.startswith("vehicle_buy:"))
async def cb_vehicle_buy(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_buy_vehicle(user, key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_vehicles_text(updated), reply_markup=get_vehicles_keyboard(updated))

# =====================================================================
# НЕДВИЖИМОСТЬ / ПАССИВНЫЙ ДОХОД
# =====================================================================
PROPERTIES = {
    "kiosk": {
        "name": "🏪 Киоск у Джал-Маркета",
        "price": 5000,
        "income_per_hour": 50,
        "min_level": 5,
        "description": "Маленький ларёк, приносит стабильный доход.",
    },
    "cafe": {
        "name": "☕ Кофейня у ворот Манаса",
        "price": 15000,
        "income_per_hour": 150,
        "min_level": 15,
        "description": "Студенты любят кофе. Доход побольше.",
    },
    "dorm_laundry": {
        "name": "🧺 Прачечная в общаге",
        "price": 30000,
        "income_per_hour": 300,
        "min_level": 25,
        "description": "Монотонный, но надёжный доход.",
    },
    "print_shop": {
        "name": "🖨 Типография методичек",
        "price": 60000,
        "income_per_hour": 600,
        "min_level": 35,
        "description": "Печатает конспекты и шпаргалки 24/7.",
    },
    "donerhouse": {
        "name": "🌯 Донерная у главного корпуса",
        "price": 120000,
        "income_per_hour": 1200,
        "min_level": 50,
        "description": "Очередь не заканчивается никогда.",
    },
    "apartments": {
        "name": "🏢 Сдаваемые квартиры у Джала",
        "price": 250000,
        "income_per_hour": 2500,
        "min_level": 70,
        "description": "Студенты платят за жильё каждый месяц.",
    },
    "mall": {
        "name": "🏬 Торговый центр «Манас Plaza»",
        "price": 500000,
        "income_per_hour": 5000,
        "min_level": 90,
        "description": "Целый ТЦ, набитый арендаторами.",
    },
}

PASSIVE_INCOME_CAP_HOURS = 12  # доход копится максимум 12 часов


def get_user_properties(user: dict) -> dict:
    import json
    raw = user.get("properties", "") or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def save_user_properties(user_id: int, props: dict):
    import json
    update_user(user_id, properties=json.dumps(props))


def get_total_income_per_hour(user: dict) -> int:
    props = get_user_properties(user)
    return sum(PROPERTIES[key]["income_per_hour"] for key in props if key in PROPERTIES)


def build_properties_text(user: dict) -> str:
    props = get_user_properties(user)
    total_income = get_total_income_per_hour(user)

    now = int(time.time())
    last = user.get("last_income_collect", 0) or now
    elapsed_h = min((now - last) / 3600, PASSIVE_INCOME_CAP_HOURS)
    pending = apply_full_coin_bonus(user, int(total_income * elapsed_h))

    lines = [
        "🏠 <b>Недвижимость и бизнесы</b>\n",
        f"💵 Доход в час: <b>{total_income}</b> монет",
        f"💰 Накоплено к сбору: <b>{pending}</b> монет "
        f"(макс. {PASSIVE_INCOME_CAP_HOURS}ч накопления)\n",
    ]

    if not props:
        lines.append("У тебя пока нет бизнесов.\n")
    else:
        lines.append("<b>Твои объекты:</b>")
        for key in props:
            p = PROPERTIES.get(key)
            if p:
                lines.append(f"  • {p['name']} — {p['income_per_hour']}/ч")
        lines.append("")

    lines.append("<b>Доступно для покупки:</b>")
    for key, p in PROPERTIES.items():
        if key in props:
            continue
        lock = "" if user["level"] >= p["min_level"] else f" 🔒 (нужен {p['min_level']} ур.)"
        lines.append(
            f"  • {p['name']} — {p['price']} монет, {p['income_per_hour']}/ч{lock}\n"
            f"    <i>{p['description']}</i>"
        )

    return "\n".join(lines)


def get_properties_keyboard(user: dict) -> InlineKeyboardMarkup:
    props = get_user_properties(user)
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Собрать доход", callback_data="income_collect")
    for key, p in PROPERTIES.items():
        if key in props:
            continue
        if user["level"] < p["min_level"]:
            continue
        builder.button(
            text=f"🛒 {p['name']} — {p['price']} мон.",
            callback_data=f"property_buy:{key}"
        )
    builder.adjust(1)
    return builder.as_markup()

def do_buy_property(user: dict, prop_key: str) -> tuple[bool, str]:
    prop = PROPERTIES.get(prop_key)
    if not prop:
        return False, "❌ Такого объекта нет."
    props = get_user_properties(user)
    if prop_key in props:
        return False, "У тебя уже есть этот объект!"
    if user["level"] < prop["min_level"]:
        return False, f"❌ Нужен уровень <b>{prop['min_level']}</b>."

    _, _, _, ev_discount = get_event_multipliers()
    actual_price = int(prop["price"] * (1 - ev_discount / 100))

    if user["balance"] < actual_price:
        return False, f"❌ Недостаточно монет. Нужно {actual_price}."

    props[prop_key] = int(time.time())
    save_user_properties(user["user_id"], props)
    new_balance = user["balance"] - actual_price
    last_collect = user.get("last_income_collect", 0) or int(time.time())
    update_user(
        user["user_id"],
        balance=new_balance,
        last_income_collect=last_collect or int(time.time()),
    )
    change_reputation(user["user_id"], +1)

    updated = get_user(user["user_id"])
    ach_msgs = check_and_grant_achievements(updated) if updated else []
    ach_block = ("\n\n" + "\n".join(ach_msgs)) if ach_msgs else ""

    return True, f"✅ Куплено: {prop['name']}!\n💰 Потрачено: {actual_price} монет.{ach_block}"

def do_collect_income(user: dict) -> tuple[bool, str]:
    total_income = get_total_income_per_hour(user)
    if total_income == 0:
        return False, "❌ У тебя пока нет приносящей доход недвижимости."

    now = int(time.time())
    last = user.get("last_income_collect", 0) or now
    elapsed_h = min((now - last) / 3600, PASSIVE_INCOME_CAP_HOURS)
    pending = apply_full_coin_bonus(user, int(total_income * elapsed_h))

    if pending <= 0:
        return False, "⏳ Пока нечего собирать, доход ещё капает."

    new_balance = user["balance"] + pending
    update_user(user["user_id"], balance=new_balance, last_income_collect=now)
    updated = get_user(user["user_id"])
    if updated:
        check_and_grant_achievements(updated)
    return True, (
        f"💰 Собран пассивный доход: <b>+{pending}</b> монет!\n"
        f"📊 Баланс: <b>{new_balance}</b> монет"
    )
# =====================================================================
# НАВЫКИ
# =====================================================================
SKILL_CONFIG = {
    "communication_level": {
        "label":       "🗣 Коммуникация",
        "cost_base":   400,
        "description": "Нужна для ветки Интеллект.",
        "unlock_item": None,
    },
    "driving_level": {
        "label":       "🚗 Вождение",
        "cost_base":   600,
        "description": "Нужно для ветки Баланс. Требует 🛵 Скутер.",
        "unlock_item": "has_scooter",
    },
    "service_level": {
        "label":       "🛎 Сервис",
        "cost_base":   500,
        "description": "Нужен для ветки Деньги. Требует 🍹 Шейкер.",
        "unlock_item": "has_shaker",
    },
    "organization_level": {
        "label":       "📋 Организованность",
        "cost_base":   700,
        "description": "Нужна для ветки Баланс (средние грейды). Требует 🛵 Скутер.",
        "unlock_item": "has_scooter",
    },
    "management_level": {
        "label":       "🏢 Менеджмент",
        "cost_base":   900,
        "description": "Нужен для всех веток на высоких уровнях. Требует предмет ветки.",
        "unlock_item": None,
    },
}

GATHER_SKILL_CONFIG = {
    "hunting_level": {
        "label": "🏹 Охотничье мастерство",
        "cost_base": 350,
        "description": "Больше добычи и шанс редких трофеев на охоте.",
    },
    "fishing_level": {
        "label": "🎣 Рыболовное мастерство",
        "cost_base": 300,
        "description": "Больше улова и шанс редкой рыбы.",
    },
    "mining_level": {
        "label": "⛏ Горное дело",
        "cost_base": 400,
        "description": "Больше руды и шанс редких минералов в шахте.",
    },
}
# =====================================================================
# ДОСТИЖЕНИЯ
# =====================================================================
ACHIEVEMENTS = {
    "first_step": {
        "name":        "🐣 Первый шаг",
        "description": "Зарегистрируйся в игре",
        "reward_coins": 50,
        "reward_exp":   20,
    },
    "first_work": {
        "name":        "👷 Первая смена",
        "description": "Отработай первую смену",
        "reward_coins": 100,
        "reward_exp":   30,
    },
    "level_5": {
        "name":        "📈 Новичок",
        "description": "Достигни 5 уровня",
        "reward_coins": 200,
        "reward_exp":   50,
    },
    "level_10": {
        "name":        "🎓 Студент",
        "description": "Достигни 10 уровня",
        "reward_coins": 500,
        "reward_exp":   100,
    },
    "level_25": {
        "name":        "🏅 Опытный",
        "description": "Достигни 25 уровня",
        "reward_coins": 1000,
        "reward_exp":   300,
    },
    "level_50": {
        "name":        "🌟 Ветеран",
        "description": "Достигни 50 уровня",
        "reward_coins": 3000,
        "reward_exp":   1000,
    },
    "level_100": {
        "name":        "👑 Легенда",
        "description": "Достигни 100 уровня",
        "reward_coins": 10000,
        "reward_exp":   5000,
    },
    "balance_1000": {
        "name":        "💰 Первая тысяча",
        "description": "Накопи 1 000 монет",
        "reward_coins": 100,
        "reward_exp":   50,
    },
    "balance_10000": {
        "name":        "💵 Десятка",
        "description": "Накопи 10 000 монет",
        "reward_coins": 500,
        "reward_exp":   200,
    },
    "balance_100000": {
        "name":        "🏦 Богач",
        "description": "Накопи 100 000 монет",
        "reward_coins": 2000,
        "reward_exp":   1000,
    },
    "balance_1000000": {
        "name":        "💎 Миллионер",
        "description": "Накопи 1 000 000 монет",
        "reward_coins": 50000,
        "reward_exp":   10000,
    },
    "grade_3": {
        "name":        "🔼 Карьерист",
        "description": "Достигни 3 грейда профессии",
        "reward_coins": 500,
        "reward_exp":   150,
    },
    "grade_6": {
        "name":        "🚀 Профессионал",
        "description": "Достигни 6 грейда профессии",
        "reward_coins": 2000,
        "reward_exp":   500,
    },
    "grade_9": {
        "name":        "🏆 Мастер",
        "description": "Достигни максимального 9 грейда",
        "reward_coins": 10000,
        "reward_exp":   3000,
    },
    "train_10": {
        "name":        "🏋️ Качок",
        "description": "Проведи 10 тренировок (суммарный интеллект+выносливость ≥ 20)",
        "reward_coins": 300,
        "reward_exp":   100,
    },
    "all_items": {
        "name":        "🎒 Коллекционер",
        "description": "Купи все предметы снаряжения в магазине",
        "reward_coins": 5000,
        "reward_exp":   1500,
    },
    "luck_event": {
        "name":        "🍀 Везунчик",
        "description": "Получи положительное случайное событие на работе",
        "reward_coins": 150,
        "reward_exp":   50,
    },
    "stock_win": {
        "name":        "📈 Трейдер",
        "description": "Выиграй на бирже хотя бы раз",
        "reward_coins": 200,
        "reward_exp":   80,
    },
    "skill_max": {
        "name":        "🧠 Эрудит",
        "description": "Прокачай любой навык до уровня 10",
        "reward_coins": 3000,
        "reward_exp":   1000,
    },
    "poker_win": {
        "name":        "🃏 Покерфейс",
        "description": "Выиграй партию в покер",
        "reward_coins": 500,
        "reward_exp":   200,
    },
    "married": {
        "name":        "💍 Молодожён",
        "description": "Вступи в брак",
        "reward_coins": 500,
        "reward_exp":   200,
    },
    "first_property": {
        "name":        "🏠 Первая инвестиция",
        "description": "Купи свою первую недвижимость",
        "reward_coins": 300,
        "reward_exp":   100,
    },
    "real_estate_king": {
        "name":        "🏙 Король недвижимости",
        "description": "Купи всю недвижимость",
        "reward_coins": 8000,
        "reward_exp":   2500,
    },
    "first_boss_kill": {
        "name": "⚔️ Охотник на духов", "description": "Победи первого босса",
        "reward_coins": 300, "reward_exp": 100,
    },
    "boss_legend": {
        "name": "🌟 Легендарная добыча", "description": "Получи легендарный предмет с босса",
        "reward_coins": 3000, "reward_exp": 1000,
    },
    "all_bosses": {
        "name": "🐎 Батыр КТУ", "description": "Победи всех 5 боссов хотя бы раз",
        "reward_coins": 10000, "reward_exp": 3000,
    },
    "first_hunt":  {
        "name": "🏹 Первая добыча", "description": "Сходи на охоту в первый раз",
        "reward_coins": 80, "reward_exp": 30
    },
    "first_fish":  {
        "name": "🎣 Первый улов",   "description": "Сходи на рыбалку в первый раз",
        "reward_coins": 80, "reward_exp": 30
    },
    "first_ore":   {
        "name": "⛏ Первая руда",   "description": "Сходи в шахту в первый раз",
        "reward_coins": 80, "reward_exp": 30
    },
    "gather_100":  {
        "name": "🎒 Собиратель",    "description": "Собери суммарно 100 ресурсов",
        "reward_coins": 400, "reward_exp": 150
    },
    "gather_1000": {
        "name": "🏔 Добытчик",      "description": "Собери суммарно 1000 ресурсов",
        "reward_coins": 3000, "reward_exp": 1000
    },
    "craft_first": {
        "name": "🛠 Первый крафт",   "description": "Скрафти любой инструмент",
        "reward_coins": 150, "reward_exp": 60
    },
    "craft_all_t1": {
        "name": "🧰 Ремесленник",  "description": "Скрафти инструменты 1 тира во всех трёх ветках",
        "reward_coins": 600, "reward_exp": 250
    },
    "craft_all_t3": {
        "name": "👑 Мастер снаряжения", "description": "Скрафти инструменты 3 тира во всех трёх ветках",
        "reward_coins": 6000, "reward_exp": 2000
    },
    "gskill_max":  {
        "name": "🧭 Знаток промысла", "description": "Прокачай любой навык сбора до 10 уровня",
        "reward_coins": 2500, "reward_exp": 800
    },
    "loc_boss_first": {
        "name": "🗡 Охотник на легенд", "description": "Победи первого босса локации",
        "reward_coins": 300, "reward_exp": 120
    },
    "loc_boss_all": {
        "name": "🏆 Покоритель диких земель", "description": "Победи всех боссов локаций хотя бы раз",
        "reward_coins": 8000, "reward_exp": 2500
    },
    "legendary_resource": {
        "name": "✨ Редчайшая находка", "description": "Добудь легендарный ресурс (алмаз, золотая рыбка или шкура барса)",
        "reward_coins": 1500, "reward_exp": 500
    },
    "first_rebirth": {
        "name": "🔄 Новый цикл", "description": "Соверши первое перерождение",
        "reward_coins": 1000, "reward_exp": 500,
    },
    "rebirth_5": {
        "name": "🌀 Ветеран перерождений", "description": "Переродись 5 раз",
        "reward_coins": 10000, "reward_exp": 3000,
    },
    "gather_collection_hunting": {
        "name": "🏹 Полная коллекция охоты", "description": "Собери хотя бы по 1 каждому ресурсу охоты",
        "reward_coins": 1500, "reward_exp": 500,
    },
    "gather_collection_fishing": {
        "name": "🎣 Полная коллекция рыбалки", "description": "Собери хотя бы по 1 каждому ресурсу рыбалки",
        "reward_coins": 1500, "reward_exp": 500,
    },
    "gather_collection_mining": {
        "name": "⛏ Полная коллекция шахты", "description": "Собери хотя бы по 1 каждому ресурсу шахты",
        "reward_coins": 1500, "reward_exp": 500,
    },
    "craft_all_max": {
        "name": "🌌 Оружейник легенд", "description": "Прокачай все инструменты до максимального уровня",
        "reward_coins": 15000, "reward_exp": 5000,
    },
}

RELATIONSHIP_LEVELS = [
    (0, "🤝 Знакомые"),
    (100, "😊 Приятели"),
    (300, "🙂 Друзья"),
    (700, "💛 Близкие друзья"),
    (1500, "💞 Родственные души"),
    (3000, "💘 Неразлучники"),
    (6000, "👑 Легендарная пара"),
]

HUG_COOLDOWN_SECONDS = 3600  # обнять — раз в час на пару

GIFTS = {
    "tea": {
        "name": "🍵 Турецкий чай", "price": 30, "rel_xp": 10,
        "description": "Маленький, но тёплый жест внимания.",
    },
    "simit": {
        "name": "🥨 Симит", "price": 40, "rel_xp": 12,
        "description": "Свежий бублик из коридоров Манаса.",
    },
    "flower": {
        "name": "🌷 Тюльпан", "price": 60, "rel_xp": 15,
        "description": "Один цветок, но от души.",
    },
    "chocolate": {
        "name": "🍫 Шоколадка", "price": 90, "rel_xp": 20,
        "description": "Классика, которая работает всегда.",
    },
    "shawarma": {
        "name": "🌯 Шаурма из Джала", "price": 100, "rel_xp": 22,
        "description": "Пропитание — тоже проявление любви.",
    },
    "teddy_bear": {
        "name": "🧸 Плюшевый мишка", "price": 250, "rel_xp": 40,
        "description": "Мягкий и очень милый подарок.",
    },
    "bouquet": {
        "name": "💐 Букет роз", "price": 400, "rel_xp": 65,
        "description": "Настоящий романтический жест.",
    },
    "perfume": {
        "name": "🌸 Духи", "price": 600, "rel_xp": 90,
        "description": "Приятный аромат надолго запомнится.",
    },
    "watch": {
        "name": "⌚ Наручные часы", "price": 1500, "rel_xp": 180,
        "description": "Стильный и дорогой подарок.",
    },
    "phone": {
        "name": "📱 Новый телефон", "price": 8000, "rel_xp": 700,
        "description": "Максимальный жест щедрости.",
    },
    "ring": {
        "name": "💍 Кольцо", "price": 15000, "rel_xp": 1200,
        "description": "Символ серьёзных намерений.",
    },
}

hug_cooldowns: dict[tuple[int, int], int] = {}  # (min_id, max_id) -> timestamp

def _pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def get_relationship_level_name(xp: int) -> str:
    name = RELATIONSHIP_LEVELS[0][1]
    for threshold, lvl_name in RELATIONSHIP_LEVELS:
        if xp >= threshold:
            name = lvl_name
        else:
            break
    return name


def get_relationship_progress_text(xp: int) -> str:
    for i, (threshold, name) in enumerate(RELATIONSHIP_LEVELS):
        if i + 1 < len(RELATIONSHIP_LEVELS):
            next_threshold, next_name = RELATIONSHIP_LEVELS[i + 1]
            if xp < next_threshold:
                return f"📈 До уровня «{next_name}»: ещё {next_threshold - xp} XP"
        elif xp >= threshold:
            return "🏆 Максимальный уровень отношений достигнут!"
    return ""


def get_relationship(a: int, b: int) -> dict | None:
    u1, u2 = _pair_key(a, b)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM relationships WHERE user1_id = %s AND user2_id = %s",
                (u1, u2)
            )
            row = cur.fetchone()
    return dict(row) if row else None


def add_relationship_xp(a: int, b: int, amount: int) -> dict:
    u1, u2 = _pair_key(a, b)
    now = int(time.time())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO relationships (user1_id, user2_id, xp, last_interaction)
                VALUES (%s, %s, %s, %s) ON CONFLICT (user1_id, user2_id) DO
                UPDATE SET
                    xp = relationships.xp + EXCLUDED.xp,
                    last_interaction = EXCLUDED.last_interaction
                """,
                (u1, u2, amount, now)
            )
            conn.commit()
    return get_relationship(a, b)


async def resolve_mention(message: Message) -> tuple[int | None, str | None]:
    """Возвращает (user_id, full_name) из reply или @mention/text_mention."""
    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        return ru.id, ru.full_name

    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention" and ent.user:
                return ent.user.id, ent.user.full_name
            elif ent.type == "mention":
                uname = message.text[ent.offset:ent.offset + ent.length]
                try:
                    chat_info = await bot.get_chat(uname)
                    name = (
                        chat_info.full_name
                        if getattr(chat_info, "full_name", None)
                        else (chat_info.first_name or uname)
                    )
                    return chat_info.id, name
                except Exception:
                    pass

    return None, None


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("обнять"))
)
async def cmd_hug(message: Message):
    uid = message.from_user.id
    get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    target_id, target_name = await resolve_mention(message)
    if not target_id:
        await message.answer(
            "❌ Укажи кого обнять: <code>обнять @username</code> или ответом на сообщение."
        )
        return
    if target_id == uid:
        await message.answer("❌ Нельзя обнять самого себя 😄")
        return

    register_user(target_id)

    key = _pair_key(uid, target_id)
    now = int(time.time())
    last = hug_cooldowns.get(key, 0)
    if now - last < HUG_COOLDOWN_SECONDS:
        remaining_min = (HUG_COOLDOWN_SECONDS - (now - last)) // 60
        await message.answer(f"⏳ Вы уже обнимались недавно! Подожди ещё ~{remaining_min} мин.")
        return
    hug_cooldowns[key] = now

    xp_gain = random.randint(10, 20)
    rel = add_relationship_xp(uid, target_id, xp_gain)
    level_name = get_relationship_level_name(rel["xp"])

    mention_u = message.from_user.mention_html()
    mention_t = f"<a href='tg://user?id={target_id}'>{target_name}</a>"
    await message.answer(
        f"🤗 {mention_u} обнимает {mention_t}!\n\n"
        f"💞 +{xp_gain} XP отношений\n"
        f"📊 Уровень: <b>{level_name}</b> ({rel['xp']} XP)"
    )

def build_gift_menu_text(sender: dict, target_name: str) -> str:
    lines = [f"🎁 <b>Выбери подарок для {target_name}</b>\n"]
    for g in GIFTS.values():
        lines.append(
            f"{g['name']} — <b>{g['price']}</b> мон. (+{g['rel_xp']} XP)\n"
            f"  <i>{g['description']}</i>"
        )
    lines.append(f"\n💰 Твой баланс: <b>{sender['balance']}</b> монет")
    return "\n\n".join(lines)


def get_gift_keyboard(target_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, g in GIFTS.items():
        builder.button(
            text=f"{g['name']} — {g['price']} мон.",
            callback_data=GiftCallback(gift_key=key, target_id=target_id).pack()
        )
    builder.button(text="❌ Отмена", callback_data="gift_cancel")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("подарок"))
)
async def cmd_gift(message: Message):
    uid = message.from_user.id
    sender = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    target_id, target_name = await resolve_mention(message)

    if not target_id:
        await message.answer(
            "❌ Укажи, кому дарить подарок:\n"
            "<code>подарок @username</code>\n"
            "или ответом на сообщение: <code>подарок</code>"
        )
        return
    if target_id == uid:
        await message.answer("❌ Нельзя подарить подарок самому себе.")
        return

    register_user(target_id)

    await message.answer(
        build_gift_menu_text(sender, target_name),
        reply_markup=get_gift_keyboard(target_id)
    )


@dp.callback_query(GiftCallback.filter())
async def callback_send_gift(callback: CallbackQuery, callback_data: GiftCallback):
    sender_id = callback.from_user.id
    target_id = callback_data.target_id
    gift = GIFTS.get(callback_data.gift_key)

    if not gift:
        await callback.answer("❌ Такого подарка нет.", show_alert=True)
        return
    if sender_id == target_id:
        await callback.answer("❌ Нельзя дарить подарок самому себе.", show_alert=True)
        return

    sender = get_user_safe(sender_id)
    if sender["balance"] < gift["price"]:
        await callback.answer(
            f"❌ Недостаточно монет! Нужно {gift['price']}, есть {sender['balance']}.",
            show_alert=True
        )
        return

    register_user(target_id)

    update_user(sender_id, balance=sender["balance"] - gift["price"])
    change_reputation(sender_id, +1)

    rel = add_relationship_xp(sender_id, target_id, gift["rel_xp"])
    level_name = get_relationship_level_name(rel["xp"])

    target_data = get_user(target_id)
    target_name = (target_data.get("username") if target_data else None) or f"#{target_id}"
    mention_s = callback.from_user.mention_html()
    mention_t = f"<a href='tg://user?id={target_id}'>{target_name}</a>"

    await callback.answer("🎁 Подарок отправлен!", show_alert=True)
    await callback.message.edit_text(
        f"🎁 {mention_s} дарит {mention_t} {gift['name']}!\n\n"
        f"<i>{gift['description']}</i>\n\n"
        f"💞 +{gift['rel_xp']} XP отношений\n"
        f"📊 Уровень: <b>{level_name}</b> ({rel['xp']} XP)"
    )

    updated_sender = get_user(sender_id)
    if updated_sender:
        check_and_grant_achievements(updated_sender)


@dp.callback_query(F.data == "gift_cancel")
async def callback_gift_cancel(callback: CallbackQuery):
    await callback.answer("Отменено.")
    await callback.message.edit_text("🎁 Дарение подарка отменено.")

async def _send_my_relationships(message: Message, uid: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM relationships
                WHERE user1_id = %s
                   OR user2_id = %s
                ORDER BY xp DESC LIMIT 15
                """,
                (uid, uid)
            )
            rows = cur.fetchall()

    if not rows:
        await message.answer(
            "💞 У тебя пока нет отношений ни с кем.\n"
            "Напиши <code>обнять @username</code> (или ответом на сообщение), чтобы начать!"
        )
        return

    lines = ["💞 <b>Твои отношения</b>\n"]
    for row in rows:
        other_id = row["user2_id"] if row["user1_id"] == uid else row["user1_id"]
        other = get_user(other_id)
        name = (other.get("username") if other else None) or f"#{other_id}"
        level_name = get_relationship_level_name(row["xp"])
        lines.append(f"• <b>{name}</b> — {level_name} ({row['xp']} XP)")

    await message.answer("\n".join(lines))


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and (
        t.strip().lower() == "отношения" or
        t.strip().lower().startswith("отношения ")
    ))
)

async def cmd_relationships_group(message: Message):
    uid = message.from_user.id
    get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    target_id, target_name = await resolve_mention(message)

    if not target_id:
        # без указания цели -> показываем свой список
        await _send_my_relationships(message, uid)
        return

    if target_id == uid:
        await message.answer("❌ Нельзя иметь отношения с самим собой 😄")
        return

    register_user(target_id)
    rel = get_relationship(uid, target_id)
    xp = rel["xp"] if rel else 0
    level_name = get_relationship_level_name(xp)
    progress = get_relationship_progress_text(xp)

    await message.answer(
        f"💞 <b>Отношения с {target_name}</b>\n\n"
        f"Уровень: <b>{level_name}</b>\n"
        f"XP: <b>{xp}</b>\n\n"
        f"{progress}\n\n"
        f"<i>Качайте отношения через <code>обнять</code> и <code>подарок</code>!</i>"
    )


@dp.message(Command("relationships"), F.chat.type == "private")
@dp.message(F.text == "💞 Отношения", F.chat.type == "private")
async def cmd_relationships_private(message: Message):
    await _send_my_relationships(message, message.from_user.id)


async def _build_top_users_text(field: str, label: str, emoji: str = "🏆", limit: int = 10) -> str:
    """field должен быть одним из строго заданных имён колонок — не подставляй сюда пользовательский ввод."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT user_id, username, {field} AS val FROM users ORDER BY {field} DESC LIMIT %s",
                (limit,)
            )
            rows = cur.fetchall()

    if not rows:
        return f"Рейтинг «{label}» пока пуст."

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{emoji} <b>Топ-{limit}: {label}</b>\n"]
    for i, row in enumerate(rows, 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        name = row["username"] or f"#{row['user_id']}"
        lines.append(f"{medal} <b>{name}</b> — {row['val']}")
    return "\n".join(lines)


@dp.message(Command("top_level"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("топ уровней", "топ уровень")))
async def cmd_top_level(message: Message):
    await message.answer(await _build_top_users_text("level", "Уровень", "⭐"))


@dp.message(Command("top_rep"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("топ репутации", "топ реп")))
async def cmd_top_rep(message: Message):
    await message.answer(await _build_top_users_text("reputation", "Репутация", "🌟"))


@dp.message(Command("top_ref"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("топ рефералов", "топ рефералы")))
async def cmd_top_ref(message: Message):
    await message.answer(await _build_top_users_text("referral_count", "Рефералы", "🔗"))
    # ^ работает, только если ты уже добавил реферальную систему (referral_count в БД)


@dp.message(Command("top_relationships"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("топ отношений", "топ пар")))
async def cmd_top_relationships(message: Message):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT r.user1_id,
                       r.user2_id,
                       r.xp,
                       u1.username AS name1,
                       u2.username AS name2
                FROM relationships r
                         LEFT JOIN users u1 ON u1.user_id = r.user1_id
                         LEFT JOIN users u2 ON u2.user_id = r.user2_id
                ORDER BY r.xp DESC LIMIT 10
                """
            )
            rows = cur.fetchall()

    if not rows:
        await message.answer("💞 Пока никто не качал отношения. Начни первым: <code>обнять @username</code>")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["💞 <b>Топ-10 отношений</b>\n"]
    for i, row in enumerate(rows, 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        n1 = row["name1"] or f"#{row['user1_id']}"
        n2 = row["name2"] or f"#{row['user2_id']}"
        level_name = get_relationship_level_name(row["xp"])
        lines.append(f"{medal} <b>{n1}</b> 💞 <b>{n2}</b> — {level_name} ({row['xp']} XP)")

    await message.answer("\n".join(lines))


@dp.message(Command("marriages"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("список браков", "браки", "все браки")))
async def cmd_marriage_list(message: Message):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id, username, spouse_id, married_at
                FROM users
                WHERE spouse_id IS NOT NULL
                ORDER BY married_at ASC
                """
            )
            rows = cur.fetchall()

    if not rows:
        await message.answer("💍 Пока никто не женился.")
        return

    seen = set()
    now = int(time.time())
    lines = ["💍 <b>Список браков</b>\n"]
    for row in rows:
        pair = _pair_key(row["user_id"], row["spouse_id"])
        if pair in seen:
            continue
        seen.add(pair)
        spouse = get_user(row["spouse_id"])
        name1 = row["username"] or f"#{row['user_id']}"
        name2 = (spouse.get("username") if spouse else None) or f"#{row['spouse_id']}"
        days = max(0, (now - (row["married_at"] or now)) // 86400)
        lines.append(f"👰🤵 <b>{name1}</b> & <b>{name2}</b> — {days} дн. в браке")

    await message.answer("\n".join(lines))

def _is_top1(field: str, user_id: int) -> bool:
    """field должен быть жёстко заданной колонкой — не пользовательский ввод."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT user_id FROM users ORDER BY {field} DESC LIMIT 1")
            row = cur.fetchone()
    return bool(row and row[0] == user_id)

def _count_relationships_above(user_id: int, min_xp: int) -> int:
    """Считает, с каким количеством разных людей у user_id отношения >= min_xp."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM relationships
                WHERE (user1_id = %s OR user2_id = %s)
                  AND xp >= %s
                """,
                (user_id, user_id, min_xp)
            )
            row = cur.fetchone()
    return row[0] if row else 0
# =====================================================================
# ТИТУЛЫ
# =====================================================================
TITLES = {
    # ── авто-титулы (выдаются за уникальные достижения) ──
    "millionaire": {
        "name": "💎 Миллионер", "admin_only": False,
        "bonus_coins": 5, "bonus_xp": 0, "bonus_luck": 0,
        "description": "Накопи 1 000 000 монет.",
        "condition": lambda u: u["balance"] >= 1000000,
    },
    "rector": {
        "name": "👑 Ректор", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 10, "bonus_luck": 0,
        "description": "Достигни 9 грейда ветки Интеллект.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "intel" and get_job(u)["grade"] == 9,
    },
    "mogul": {
        "name": "🏙 Магнат", "admin_only": False,
        "bonus_coins": 10, "bonus_xp": 0, "bonus_luck": 0,
        "description": "Достигни 9 грейда ветки Баланс.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "balance" and get_job(u)["grade"] == 9,
    },
    "food_king": {
        "name": "🍔 Король общепита", "admin_only": False,
        "bonus_coins": 10, "bonus_xp": 0, "bonus_luck": 0,
        "description": "Достигни 9 грейда ветки Деньги.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "money" and get_job(u)["grade"] == 9,
    },
    "legend": {
        "name": "🌟 Легенда КТУ", "admin_only": False,
        "bonus_coins": 5, "bonus_xp": 5, "bonus_luck": 5,
        "description": "Достигни 100 уровня.",
        "condition": lambda u: u["level"] >= 100,
    },
    "gambler": {
        "name": "🎰 Картёжник", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 0, "bonus_luck": 10,
        "description": "Выиграй в покер и блекджек хотя бы раз.",
        "condition": lambda u: "poker_win" in get_user_achievements(u) and "stock_win" in get_user_achievements(u),
    },
    "collector": {
        "name": "🎒 Снаряженец", "admin_only": False,
        "bonus_coins": 3, "bonus_xp": 3, "bonus_luck": 3,
        "description": "Купи всё снаряжение в магазине.",
        "condition": lambda u: all(u.get(item["flag"]) for item in SHOP_ITEMS.values()),
    },

    # ── админ-титулы (условие отсутствует — выдаются только командой) ──
    "tester": {
        "name": "🧪 Тестировщик", "admin_only": True,
        "bonus_coins": 15, "bonus_xp": 15, "bonus_luck": 15,
        "description": "Выдаётся вручную администратором.",
        "condition": None,
    },
    "developer": {
        "name": "🛠 Разработчик", "admin_only": True,
        "bonus_coins": 20, "bonus_xp": 20, "bonus_luck": 20,
        "description": "Выдаётся вручную администратором.",
        "condition": None,
    },
    "vip": {
        "name": "🎖 VIP", "admin_only": True,
        "bonus_coins": 10, "bonus_xp": 10, "bonus_luck": 10,
        "description": "Особый статус от администрации.",
        "condition": None,
    },
    "family": {
        "name": "💑 Семьянин", "admin_only": False,
        "bonus_coins": 3, "bonus_xp": 3, "bonus_luck": 0,
        "description": "Состой в браке.",
        "condition": lambda u: u.get("spouse_id") is not None,
    },
    "batyr": {
        "name": "🐎 Батыр", "admin_only": False,
        "bonus_coins": 8, "bonus_xp": 8, "bonus_luck": 5,
        "description": "Победи всех боссов КТУ.",
        "condition": lambda u: all(k in get_boss_cooldowns(u) for k in BOSSES),
    },
# ── Донатерские (только вручную от админа) ──
    "Main_doter": {
        "name": "💎 Главный Дотер", "admin_only": True,
        "bonus_coins": 25, "bonus_xp": 25, "bonus_luck": 25,
        "description": "Высшая награда для главного донатера проекта. Выдаётся только администрацией.",
        "condition": None,
    },
    "doter": {
        "name": "🎗 Дотер", "admin_only": True,
        "bonus_coins": 12, "bonus_xp": 12, "bonus_luck": 12,
        "description": "Награда для донатера проекта. Выдаётся только администрацией.",
        "condition": None,
    },

    # ── За 1 место в лидербордах (проверяются автоматически) ──
    "king_of_coins": {
        "name": "💰 Король монет", "admin_only": False,
        "bonus_coins": 8, "bonus_xp": 0, "bonus_luck": 0,
        "description": "Займи 1 место в топе по балансу.",
        "condition": lambda u: _is_top1("balance", u["user_id"]),
    },
    "king_of_levels": {
        "name": "⭐ Король уровней", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 8, "bonus_luck": 0,
        "description": "Займи 1 место в топе по уровню.",
        "condition": lambda u: _is_top1("level", u["user_id"]),
    },
    "king_of_reputation": {
        "name": "🌟 Король репутации", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 0, "bonus_luck": 8,
        "description": "Займи 1 место в топе по репутации.",
        "condition": lambda u: _is_top1("reputation", u["user_id"]),
    },
    "king_of_referrals": {
        "name": "🔗 Король рефералов", "admin_only": False,
        "bonus_coins": 5, "bonus_xp": 5, "bonus_luck": 0,
        "description": "Займи 1 место в топе по рефералам.",
        "condition": lambda u: _is_top1("referral_count", u["user_id"]),
    },
    "auctioneer": {
        "name": "📊 Аукционер", "admin_only": False,
        "bonus_coins": 6, "bonus_xp": 0, "bonus_luck": 4,
        "description": "Выиграй 25 раз на бирже.",
        "condition": lambda u: u.get("stat_stock_wins", 0) >= 25,
    },
    "playboy": {
        "name": "😎 Бабник", "admin_only": False,
        "bonus_coins": 5, "bonus_xp": 5, "bonus_luck": 5,
        "description": "Прокачай отношения до 3000 XP («Неразлучники») сразу с 2+ людьми.",
        "condition": lambda u: _count_relationships_above(u["user_id"], 3000) >= 2,
    },
"master_hunter": {
        "name": "🏹 Мастер-охотник", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 0, "bonus_luck": 6,
        "description": "Прокачай Охотничье мастерство до 10 уровня.",
        "condition": lambda u: u.get("hunting_level", 0) >= 10,
    },
    "master_fisher": {
        "name": "🎣 Мастер-рыболов", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 0, "bonus_luck": 6,
        "description": "Прокачай Рыболовное мастерство до 10 уровня.",
        "condition": lambda u: u.get("fishing_level", 0) >= 10,
    },
    "master_miner": {
        "name": "⛏ Мастер-рудокоп", "admin_only": False,
        "bonus_coins": 0, "bonus_xp": 0, "bonus_luck": 6,
        "description": "Прокачай Горное дело до 10 уровня.",
        "condition": lambda u: u.get("mining_level", 0) >= 10,
    },
    "triple_gatherer": {
        "name": "🌲 Повелитель промыслов", "admin_only": False,
        "bonus_coins": 4, "bonus_xp": 4, "bonus_luck": 10,
        "description": "Прокачай все три навыка сбора до 10 уровня.",
        "condition": lambda u: min(u.get("hunting_level", 0), u.get("fishing_level", 0), u.get("mining_level", 0)) >= 10,
    },
    "wild_slayer": {
        "name": "🐉 Победитель диких земель", "admin_only": False,
        "bonus_coins": 6, "bonus_xp": 6, "bonus_luck": 10,
        "description": "Победи всех боссов локаций.",
        "condition": lambda u: all(k in get_location_boss_cooldowns(u) for k in LOCATION_BOSSES),
    },
    "founder_legend": {
        "name": "🏛 Отец-Основатель", "admin_only": False,
        "bonus_coins": 10, "bonus_xp": 10, "bonus_luck": 5,
        "description": "Достигни 9 грейда ветки Основателя.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "founder" and get_job(u)["grade"] == 9,
    },
    "science_legend": {
        "name": "🧠 Нобелевский лауреат", "admin_only": False,
        "bonus_coins": 8, "bonus_xp": 15, "bonus_luck": 5,
        "description": "Достигни 9 грейда ветки Науки.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "science" and get_job(u)["grade"] == 9,
    },
    "media_legend": {
        "name": "📺 Медиамагнат", "admin_only": False,
        "bonus_coins": 15, "bonus_xp": 8, "bonus_luck": 5,
        "description": "Достигни 9 грейда ветки Медиа.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "media" and get_job(u)["grade"] == 9,
    },
    "politics_legend": {
        "name": "👑 Президент", "admin_only": False,
        "bonus_coins": 12, "bonus_xp": 12, "bonus_luck": 10,
        "description": "Достигни 9 грейда ветки Политики.",
        "condition": lambda u: get_job(u) is not None and get_job(u)["branch"] == "politics" and get_job(u)["grade"] == 9,
    },
}


def get_user_titles(user: dict) -> set:
    raw = user.get("titles", "") or ""
    return set(x for x in raw.split(",") if x)


def save_titles(user_id: int, titles_set: set):
    update_user(user_id, titles=",".join(titles_set))


def check_and_grant_titles(user: dict) -> list[str]:
    """Проверяет авто-условия титулов и выдаёт новые."""
    owned = get_user_titles(user)
    new_titles = []
    for key, cfg in TITLES.items():
        if cfg["admin_only"] or cfg["condition"] is None:
            continue
        if key in owned:
            continue
        try:
            if cfg["condition"](user):
                owned.add(key)
                new_titles.append(key)
        except Exception:
            pass

    if new_titles:
        save_titles(user["user_id"], owned)
        # если активного титула нет — ставим первый полученный
        if not user.get("active_title"):
            update_user(user["user_id"], active_title=new_titles[0])

    messages = []
    for key in new_titles:
        t = TITLES[key]
        messages.append(
            f"🎖 <b>Новый титул!</b> {t['name']}\n<i>{t['description']}</i>"
        )
    return messages


def get_title_bonus(user: dict) -> tuple[int, int, int]:
    """Возвращает (bonus_coins_pct, bonus_xp_pct, bonus_luck) от активного титула."""
    active = user.get("active_title", "")
    if not active or active not in TITLES:
        return 0, 0, 0
    t = TITLES[active]
    return t["bonus_coins"], t["bonus_xp"], t["bonus_luck"]

def get_user_achievements(user: dict) -> set:
    raw = user.get("achievements", "") or ""
    return set(x for x in raw.split(",") if x)


def save_achievements(user_id: int, ach_set: set):
    update_user(user_id, achievements=",".join(ach_set))


def check_and_grant_achievements(user: dict) -> list[str]:
    """Проверяет условия достижений и выдаёт новые. Возвращает список сообщений о новых ачивках."""
    owned    = get_user_achievements(user)
    new_achs = []

    def _try(key: str, condition: bool):
        if condition and key not in owned:
            owned.add(key)
            new_achs.append(key)

    job  = get_job(user)
    grade = job["grade"] if job else 0

    _try("first_step",    True)
    _try("first_work",    user.get("last_work_time", 0) > 0)
    _try("level_5",       user["level"] >= 5)
    _try("level_10",      user["level"] >= 10)
    _try("level_25",      user["level"] >= 25)
    _try("level_50",      user["level"] >= 50)
    _try("level_100",     user["level"] >= 100)
    _try("balance_1000",  user["balance"] >= 1000)
    _try("balance_10000", user["balance"] >= 10000)
    _try("balance_100000",user["balance"] >= 100000)
    _try("balance_1000000", user["balance"] >= 1000000)
    _try("grade_3",       grade >= 3)
    _try("grade_6",       grade >= 6)
    _try("grade_9",       grade >= 9)
    _try("train_10",      (user["intellect"] + user["endurance"]) >= 20)
    _try("all_items",     all(user.get(item["flag"]) for item in SHOP_ITEMS.values()))
    _try("skill_max",     any(user.get(sk, 0) >= 10 for sk in SKILL_CONFIG))
    props = get_user_properties(user)
    _try("first_property", len(props) >= 1)
    _try("real_estate_king", all(k in props for k in PROPERTIES))
    _try("married", bool(user.get("spouse_id")))
    _try("first_boss_kill", user.get("stat_boss_kills", 0) >= 1)
    boss_items_owned = get_boss_items(user)
    _try("boss_legend", any(BOSS_ITEMS[k]["rarity"] == "legendary" for k in boss_items_owned if k in BOSS_ITEMS))
    cds = get_boss_cooldowns(user)
    _try("all_bosses", all(k in cds for k in BOSSES))

    gather_total = _sum_resources(user)
    loc_cds = get_location_boss_cooldowns(user)

    _try("first_rebirth", user.get("rebirths", 0) >= 1)
    _try("rebirth_5", user.get("rebirths", 0) >= 5)

    _try("first_hunt", user.get("stat_hunt_count", 0) >= 1)
    _try("first_fish", user.get("stat_fish_count", 0) >= 1)
    _try("first_ore", user.get("stat_mine_count", 0) >= 1)
    _try("gather_100", gather_total >= 100)
    _try("gather_1000", gather_total >= 1000)
    _try("craft_first", any(get_tool_level(user, t) >= 1 for t in TOOL_TIERS))
    _try("craft_all_t1", all(get_tool_level(user, t) >= 1 for t in TOOL_TIERS))
    _try("craft_all_t3", all(get_tool_level(user, t) >= 3 for t in TOOL_TIERS))
    _try("gskill_max", any(user.get(sk, 0) >= 10 for sk in GATHER_SKILL_CONFIG))
    _try("loc_boss_first", user.get("stat_location_boss_kills", 0) >= 1)
    _try("loc_boss_all", all(k in loc_cds for k in LOCATION_BOSSES))
    legendary_res_keys = {"diamond", "golden_fish", "snow_pelt"}
    _try("legendary_resource", any(get_resources(user).get(k, 0) > 0 for k in legendary_res_keys))
    _try("gather_collection_hunting", _gather_full_collection(user, "hunting"))
    _try("gather_collection_fishing", _gather_full_collection(user, "fishing"))
    _try("gather_collection_mining", _gather_full_collection(user, "mining"))
    _try("craft_all_max", all(get_tool_level(user, t) >= len(TOOL_TIERS[t]) for t in TOOL_TIERS))
    if new_achs:
        save_achievements(user["user_id"], owned)
        total_coins = 0
        total_exp   = 0
        for key in new_achs:
            a = ACHIEVEMENTS[key]
            total_coins += a["reward_coins"]
            total_exp   += a["reward_exp"]
        new_balance = user["balance"] + total_coins
        new_exp     = user["exp"]     + total_exp
        update_user(user["user_id"], balance=new_balance, exp=new_exp)
        user["balance"] = new_balance
        user["exp"]     = new_exp

    messages = []
    for key in new_achs:
        a = ACHIEVEMENTS[key]
        messages.append(
            f"🏅 <b>Новое достижение!</b> {a['name']}\n"
            f"<i>{a['description']}</i>\n"
            f"🎁 Награда: +{a['reward_coins']} монет, +{a['reward_exp']} XP"
        )
    return messages
# =====================================================================
# БАЗА ДАННЫХ — PostgreSQL
# =====================================================================
def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                                                     user_id BIGINT PRIMARY KEY,
                                                     username TEXT DEFAULT '',
                                                     balance INTEGER DEFAULT 0,
                                                     level INTEGER DEFAULT 1,
                                                     exp INTEGER DEFAULT 0,
                                                     job TEXT DEFAULT 'Безработный',
                                                     last_work_time INTEGER DEFAULT 0,

                                                     agility INTEGER DEFAULT 1,
                                                     endurance INTEGER DEFAULT 1,
                                                     charisma INTEGER DEFAULT 1,
                                                     intellect INTEGER DEFAULT 1,
                                                     luck INTEGER DEFAULT 1,

                                                     communication_level INTEGER DEFAULT 1,
                                                     driving_level INTEGER DEFAULT 0,
                                                     service_level INTEGER DEFAULT 0,
                                                     organization_level INTEGER DEFAULT 0,
                                                     management_level INTEGER DEFAULT 0,

                                                     job_rank INTEGER DEFAULT 1,

                                                     has_scooter INTEGER DEFAULT 0,
                                                     has_shaker INTEGER DEFAULT 0,
                                                     has_laptop INTEGER DEFAULT 0,
                                                     has_professor_badge INTEGER DEFAULT 0,
                                                     has_logistics_license INTEGER DEFAULT 0,
                                                     has_import_license INTEGER DEFAULT 0,
                                                     has_dean_seal INTEGER DEFAULT 0,
                                                     has_business_plan INTEGER DEFAULT 0,
                                                     has_franchise_contract INTEGER DEFAULT 0,

                                                     hp INTEGER DEFAULT 100,
                                                     energy INTEGER DEFAULT 100,

                                                     has_psychology_book INTEGER DEFAULT 0,
                                                     has_driving_license INTEGER DEFAULT 0,
                                                     last_regen_time INTEGER DEFAULT 0,
                                                     has_suit INTEGER DEFAULT 0,

                                                     achievements TEXT DEFAULT ''
                )
            """)
            # миграция: переименование старого скилла charisma_level -> service_level
            try:
                with get_conn() as conn2:
                    with conn2.cursor() as cur2:
                        cur2.execute("""
                                     SELECT column_name
                                     FROM information_schema.columns
                                     WHERE table_name = 'users'
                                       AND column_name = 'charisma_level'
                                     """)
                        if cur2.fetchone():
                            cur2.execute("ALTER TABLE users RENAME COLUMN charisma_level TO service_level")
                    conn2.commit()
            except Exception:
                pass
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS event_chats
                        (
                            chat_id
                            BIGINT
                            PRIMARY
                            KEY
                        )
                        """)
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS active_event
                        (
                            id
                            SERIAL
                            PRIMARY
                            KEY,
                            event_key
                            TEXT
                            NOT
                            NULL,
                            started_at
                            INTEGER
                            NOT
                            NULL,
                            ends_at
                            INTEGER
                            NOT
                            NULL
                        )
                        """)
            cur.execute('''
                        CREATE TABLE IF NOT EXISTS relationships
                        (
                            id
                            SERIAL
                            PRIMARY
                            KEY,
                            user1_id
                            BIGINT
                            NOT
                            NULL,
                            user2_id
                            BIGINT
                            NOT
                            NULL,
                            xp
                            INTEGER
                            DEFAULT
                            0,
                            last_interaction
                            INTEGER
                            DEFAULT
                            0,
                            UNIQUE
                        (
                            user1_id,
                            user2_id
                        )
                            )
                        ''')
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS faculties
                        (
                            faculty_key
                            TEXT
                            PRIMARY
                            KEY,
                            points
                            BIGINT
                            DEFAULT
                            0
                        )
                        """)
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS world_boss
                        (
                            id
                            SERIAL
                            PRIMARY
                            KEY,
                            boss_key
                            TEXT
                            NOT
                            NULL,
                            max_hp
                            BIGINT
                            NOT
                            NULL,
                            current_hp
                            BIGINT
                            NOT
                            NULL,
                            started_at
                            INTEGER
                            NOT
                            NULL,
                            ends_at
                            INTEGER
                            NOT
                            NULL,
                            participants
                            TEXT
                            DEFAULT
                            '{}',
                            status
                            TEXT
                            DEFAULT
                            'active'
                        )
                        """)

            for col, definition in [
                ("username", "TEXT DEFAULT ''"),
                ("achievements", "TEXT DEFAULT ''"),
                ("pet_id", "TEXT DEFAULT ''"),
                ("pet_bonus", "INTEGER DEFAULT 0"),
                ("reputation", "INTEGER DEFAULT 0"),
                ("active_event", "TEXT DEFAULT ''"),
                ("event_ends_at", "INTEGER DEFAULT 0"),
                ("pet_collection", "TEXT DEFAULT ''"),
                ("active_pet", "TEXT DEFAULT ''"),
                ("titles", "TEXT DEFAULT ''"),
                ("active_title", "TEXT DEFAULT ''"),
                ("properties", "TEXT DEFAULT '{}'"),
                ("last_income_collect", "INTEGER DEFAULT 0"),
                ("last_daily_claim", "INTEGER DEFAULT 0"),
                ("daily_streak", "INTEGER DEFAULT 0"),
                ("stat_work_count", "INTEGER DEFAULT 0"),
                ("stat_duel_wins", "INTEGER DEFAULT 0"),
                ("stat_duel_losses", "INTEGER DEFAULT 0"),
                ("stat_dice_wins", "INTEGER DEFAULT 0"),
                ("stat_dice_losses", "INTEGER DEFAULT 0"),
                ("stat_poker_wins", "INTEGER DEFAULT 0"),
                ("stat_blackjack_wins", "INTEGER DEFAULT 0"),
                ("stat_blackjack_losses", "INTEGER DEFAULT 0"),
                ("stat_slots_played", "INTEGER DEFAULT 0"),
                ("stat_stock_wins", "INTEGER DEFAULT 0"),
                ("stat_stock_losses", "INTEGER DEFAULT 0"),
                ("spouse_id", "BIGINT DEFAULT NULL"),
                ("married_at", "INTEGER DEFAULT 0"),
                ("shards", "INTEGER DEFAULT 0"),
                ("boss_items", "TEXT DEFAULT '{}'"),
                ("equipped_boss_item", "TEXT DEFAULT ''"),
                ("boss_cooldowns", "TEXT DEFAULT '{}'"),
                ("stat_boss_kills", "INTEGER DEFAULT 0"),
                ("referred_by", "BIGINT DEFAULT NULL"),
                ("referral_count", "INTEGER DEFAULT 0"),
                ("referral_earned", "INTEGER DEFAULT 0"),
                ("is_banned", "INTEGER DEFAULT 0"),
                ("hunting_level", "INTEGER DEFAULT 0"),
                ("fishing_level", "INTEGER DEFAULT 0"),
                ("mining_level", "INTEGER DEFAULT 0"),

                ("last_hunt_time", "INTEGER DEFAULT 0"),
                ("last_fish_time", "INTEGER DEFAULT 0"),
                ("last_mine_time", "INTEGER DEFAULT 0"),

                ("resources", "TEXT DEFAULT '{}'"),  # {"fur": 5, "iron_ore": 2, ...}
                ("tool_level_hunting", "INTEGER DEFAULT 0"),
                ("tool_level_fishing", "INTEGER DEFAULT 0"),
                ("tool_level_mining", "INTEGER DEFAULT 0"),

                ("location_items", "TEXT DEFAULT '{}'"),  # трофеи с локационных боссов {key: level}
                ("equipped_location_item", "TEXT DEFAULT ''"),
                ("location_boss_cooldowns", "TEXT DEFAULT '{}'"),

                ("stat_hunt_count", "INTEGER DEFAULT 0"),
                ("stat_fish_count", "INTEGER DEFAULT 0"),
                ("stat_mine_count", "INTEGER DEFAULT 0"),
                ("stat_location_boss_kills", "INTEGER DEFAULT 0"),
                ("rebirths", "INTEGER DEFAULT 0"),
                ("ascension_crystals", "INTEGER DEFAULT 0"),
                ("ascension_upgrades", "TEXT DEFAULT '{}'"),
                ("ascension_items", "TEXT DEFAULT '{}'"),
                ("equipped_ascension_item", "TEXT DEFAULT ''"),
                ("vehicles", "TEXT DEFAULT '{}'"),
                ("last_xp_collect", "INTEGER DEFAULT 0"),
                ("active_zone_hunting", "TEXT DEFAULT ''"),
                ("active_zone_fishing", "TEXT DEFAULT ''"),
                ("active_zone_mining", "TEXT DEFAULT ''"),
                ("gather_collection", "TEXT DEFAULT '{}'"),
                ("mastery_claimed", "TEXT DEFAULT '{}'"),
                ("faculty", "TEXT DEFAULT ''"),
            ]:
                try:
                    with get_conn() as conn:  # <-- отдельное соединение на каждый ALTER
                        with conn.cursor() as cur:
                            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                        conn.commit()
                except Exception:
                    pass  # колонка уже существует — ок
            conn.commit()

def register_user(user_id: int, username: str = ""):
    luck = random.randint(1, 10)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (user_id, luck, username)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username""",
                (user_id, luck, username)
                # luck не трогается при конфликте — только username обновляется
            )
            conn.commit()

def get_user(user_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = %s" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {fields} WHERE user_id = %s", values)
            conn.commit()

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================
def get_max_hp(user: dict) -> int:
    return 100 + user["endurance"] * 10 + get_ascension_upgrade_bonus(user, "hp_cap")

def get_max_energy(user: dict) -> int:
    return 100 + user["intellect"] * 10 + get_ascension_upgrade_bonus(user, "energy_cap")

# === Система "слабости" при низком HP ===
INCAPACITATED_HP_PCT = 5  # если HP < 5% от макс. — действия недоступны

def is_incapacitated(user: dict) -> bool:
    max_hp = get_max_hp(user)
    return user.get("hp", max_hp) < max_hp * INCAPACITATED_HP_PCT / 100

def get_incapacitated_message(user: dict) -> str:
    max_hp = get_max_hp(user)
    return (
        f"🤕 <b>Ты слишком слаб, чтобы действовать!</b>\n\n"
        f"❤️ HP: <b>{user.get('hp', 0)}</b> / {max_hp} "
        f"(меньше {INCAPACITATED_HP_PCT}%)\n\n"
        f"Вылечись расходниками в 🛒 Магазине (🩹 Пластырь, 🚑 Аптечка и т.д.), "
        f"прежде чем работать, тренироваться, драться или добывать ресурсы."
    )

def apply_hp_damage(user_id: int, user: dict, pct_min: float, pct_max: float) -> tuple[int, int]:
    """Отнимает случайный % от максимального HP. Возвращает (new_hp, lost_amount)."""
    max_hp = get_max_hp(user)
    pct  = random.uniform(pct_min, pct_max)
    lost = max(1, int(max_hp * pct / 100))
    new_hp = max(0, user.get("hp", max_hp) - lost)
    update_user(user_id, hp=new_hp)
    return new_hp, lost

def get_job_key(user: dict) -> str | None:
    return JOB_NAME_TO_KEY.get(user["job"])

def get_job(user: dict) -> dict | None:
    key = get_job_key(user)
    return JOBS.get(key) if key else None

def get_branch(user: dict) -> str | None:
    j = get_job(user)
    return j["branch"] if j else None

def get_grade(user: dict) -> int:
    j = get_job(user)
    return j["grade"] if j else 0

def get_user_safe(user_id: int, username: str = "") -> dict | None:
    register_user(user_id, username)
    return get_user(user_id)

# =====================================================================
# ПРИРОСТ ХАРАКТЕРИСТИК ПРИ LEVEL-UP
# =====================================================================
def get_stat_gains(branch: str, new_level: int) -> dict:
    if branch == "intel":
        intel_bonus = 10 if new_level >= 100 else (3 if new_level >= 70 else 2)
        return {"agility": 1, "endurance": 1, "charisma": 1, "intellect": intel_bonus}
    elif branch == "balance":
        return {"agility": 2, "endurance": 2, "charisma": 2, "intellect": 2}
    elif branch == "money":
        return {"agility": 1, "endurance": 1, "charisma": 3, "intellect": 1}
    else:
        return {"agility": 1, "endurance": 1, "charisma": 1, "intellect": 1}

# =====================================================================
# АВТОМАТИЧЕСКОЕ ПОВЫШЕНИЕ УРОВНЯ
# =====================================================================
def auto_level_up(user: dict) -> tuple[dict, list[str]]:
    messages = []
    branch = get_branch(user) or ""

    while user["exp"] >= xp_needed(user["level"]):
        cost      = xp_needed(user["level"])
        new_level = user["level"] + 1
        new_exp   = user["exp"] - cost

        gains = get_stat_gains(branch, new_level)

        new_agi  = user["agility"]   + gains["agility"]
        new_end  = user["endurance"] + gains["endurance"]
        new_cha  = user["charisma"]  + gains["charisma"]
        new_int  = user["intellect"] + gains["intellect"]

        new_max_hp = 100 + new_end * 10
        new_max_energy = 100 + new_int * 10
        new_hp = min(user.get("hp", 100) + (new_end - user["endurance"]) * 10, new_max_hp)
        new_energy = min(user.get("energy", 100) + (new_int - user["intellect"]) * 10, new_max_energy)

        update_user(
            user["user_id"],
            level=new_level, exp=new_exp,
            agility=new_agi, endurance=new_end,
            charisma=new_cha, intellect=new_int,
            hp=new_hp, energy=new_energy,
        )
        user = {**user, "hp": new_hp, "energy": new_energy}
        user = {
            **user,
            "level": new_level, "exp": new_exp,
            "agility": new_agi, "endurance": new_end,
            "charisma": new_cha, "intellect": new_int,
        }

        gains_str = (
            f"  🏃 Ловкость:     +{gains['agility']} → {new_agi}\n"
            f"  💪 Выносливость: +{gains['endurance']} → {new_end} "
            f"(макс. HP: {get_max_hp(user)})\n"
            f"  ✨ Харизма:      +{gains['charisma']} → {new_cha}\n"
            f"  🧠 Интеллект:    +{gains['intellect']} → {new_int} "
            f"(макс. ⚡: {get_max_energy(user)})"
        )
        msg = f"\n\n🎉 <b>НОВЫЙ УРОВЕНЬ — {new_level}!</b>\n📊 <b>Прирост:</b>\n{gains_str}"

        job = get_job(user)
        if job:
            next_key = job.get("evolves_to")
            if next_key:
                next_job = JOBS[next_key]
                if new_level >= next_job["min_level"]:
                    msg += (
                        f"\n\n🌟 <b>Новый грейд доступен!</b>\n"
                        f"Открой <b>💼 Профессии</b> для повышения до "
                        f"«{next_job['name']}»"
                    )
        messages.append(msg)

    return user, messages

# =====================================================================
# ПРОВЕРКА УСЛОВИЙ ПЕРЕХОДА НА СЛЕДУЮЩИЙ ГРЕЙД
# =====================================================================
def check_upgrade_conditions(user: dict) -> tuple[bool, str]:
    job_key = get_job_key(user)
    if not job_key or job_key not in JOBS:
        return False, "❌ Сначала выбери профессию."

    job = JOBS[job_key]
    next_key = job.get("evolves_to")
    if not next_key:
        return False, "✅ Ты уже на максимальном грейде!"

    next_job = JOBS[next_key]

    req_level = next_job["min_level"]
    if user["level"] < req_level:
        return False, f"❌ Нужен <b>{req_level}</b> уровень (у тебя {user['level']})."

    if "req_skill" in next_job:
        skill_key, skill_min = next_job["req_skill"]
        cfg = SKILL_CONFIG.get(skill_key, {})
        label = cfg.get("label", skill_key)
        val = user.get(skill_key, 0)
        if val < skill_min:
            return False, f"❌ Нужен навык {label} уровня <b>{skill_min}</b> (у тебя {val})."

    if "req_item" in next_job:
        item_flag, item_label = next_job["req_item"]
        if not user.get(item_flag):
            return False, f"❌ Нужен предмет: {item_label} (купи в Магазине)."

    return True, "✅ Все условия выполнены!"

# =====================================================================
# ТЕКСТ И КЛАВИАТУРА МЕНЮ ПРОФЕССИЙ
# =====================================================================
def build_jobs_text(user: dict) -> str:
    if user["job"] == "Безработный":
        lines = ["💼 <b>Выбор профессии</b>\n",
                 "Выбери ветку — сменить нельзя!\n"]
        for key in get_available_starter_jobs(user):
            d = JOBS[key]
            lines.append(
                f"🔹 <b>{d['name']}</b>\n"
                f"   💰 {d['min_reward']}–{d['max_reward']} мон. | "
                f"✨ {d['min_exp']}–{d['max_exp']} XP\n"
                f"   <i>{d['description']}</i>"
            )
        rebirths = user.get("rebirths", 0)
        for req, job_key in sorted(REBIRTH_STARTER_JOBS.items()):
            if req > rebirths:
                lines.append(f"🔒 «???» — открывается после {req} перерождения(ий)")
        return "\n".join(lines)

    job_key = get_job_key(user)
    if not job_key:
        update_user(user["user_id"], job="Безработный")
        lines = ["⚠️ <b>Профессия сброшена</b> из-за обновления игры. Выбери заново:\n"]
        for key in get_available_starter_jobs(user):
            d = JOBS[key]
            lines.append(
                f"🔹 <b>{d['name']}</b>\n"
                f"   💰 {d['min_reward']}–{d['max_reward']} мон. | "
                f"✨ {d['min_exp']}–{d['max_exp']} XP\n"
                f"   <i>{d['description']}</i>"
            )
        return "\n".join(lines)

    job     = JOBS[job_key]
    rank    = user.get("job_rank", 1)
    bonus   = (rank - 1) * 10
    next_key = job.get("evolves_to")
    can, why = check_upgrade_conditions(user)

    lines = [
        f"💼 <b>{user['job']}</b>  |  Грейд: {job['grade']}/9  |  Ранг: {rank}\n",
        f"<i>{job['description']}</i>\n",
        f"💰 Заработок: {job['min_reward']}–{job['max_reward']} мон."
        + (f" (+{bonus}% ранг)" if bonus > 0 else "") + "\n",
        f"✨ Опыт за смену: {job['min_exp']}–{job['max_exp']}\n",
        f"⭐ Уровень: <b>{user['level']}</b> | XP: <b>{user['exp']}</b> / {xp_needed(user['level'])}\n",
    ]

    if next_key:
        next_job = JOBS[next_key]
        lines.append(f"\n━━━ 🔓 Следующий грейд ━━━")
        lines.append(f"<b>{next_job['name']}</b>")
        lines.append(f"Требования:")
        lines.append(f"  • Уровень: <b>{next_job['min_level']}</b>  "
                     f"({'✅' if user['level'] >= next_job['min_level'] else '❌'})")
        if "req_skill" in next_job:
            sk, sv = next_job["req_skill"]
            lbl = SKILL_CONFIG.get(sk, {}).get("label", sk)
            lines.append(f"  • {lbl}: <b>{sv}</b>  "
                         f"({'✅' if user.get(sk, 0) >= sv else '❌'}, "
                         f"у тебя {user.get(sk, 0)})")
        if "req_item" in next_job:
            iflag, ilabel = next_job["req_item"]
            lines.append(f"  • {ilabel}: {'✅' if user.get(iflag) else '❌'}")
        if not can:
            lines.append(f"\n{why}")
    else:
        lines.append("\n🏆 <b>Максимальный грейд достигнут!</b>")

    return "\n".join(lines)


def get_jobs_keyboard(user: dict) -> InlineKeyboardMarkup | None:
    builder = InlineKeyboardBuilder()

    if user["job"] == "Безработный":
        for key in get_available_starter_jobs(user):
            builder.button(
                text=JOBS[key]["name"][:50],
                callback_data=JobCallback(job_key=key).pack()
            )
        builder.adjust(1)
        return builder.as_markup()

    job_key = get_job_key(user)
    if not job_key:
        update_user(user["user_id"], job="Безработный")
        for key in get_available_starter_jobs(user):
            builder.button(
                text=JOBS[key]["name"][:50],
                callback_data=JobCallback(job_key=key).pack()
            )
        builder.adjust(1)
        return builder.as_markup()

    job = JOBS[job_key]
    next_key = job.get("evolves_to")
    if next_key:
        can, _ = check_upgrade_conditions(user)
        if can:
            builder.button(
                text="🚀 Повысить грейд",
                callback_data=UpgradeJobCallback(job_key=next_key).pack()
            )
            builder.adjust(1)
            return builder.as_markup()

    return None

# =====================================================================
# ЛОГИКА: РАБОТА
# =====================================================================
def do_work(user: dict) -> tuple[bool, str]:
    if is_incapacitated(user):
        return False, get_incapacitated_message(user)

    if user["job"] == "Безработный":
        return False, "❌ Сначала выбери профессию через <b>💼 Профессии</b>!"

    now = int(time.time())
    cooldown = get_work_cooldown(user)
    elapsed = now - user["last_work_time"]
    if elapsed < cooldown:
        remaining = cooldown - elapsed
        return False, f"⏳ Подожди ещё <b>{remaining}</b> сек. (кулдаун {cooldown}с — 🏃 Ловкость сокращает)"

    energy_cost = apply_energy_discount(WORK_ENERGY_COST)
    if user["energy"] < energy_cost:
        max_e = get_max_energy(user)
        return False, (
            f"😴 Недостаточно энергии!\n"
            f"Нужно: <b>{energy_cost} ⚡</b>, есть: <b>{user['energy']} ⚡</b> / {max_e}.\n"
            f"Купи расходники в 🛒 Магазине."
        )
    job = get_job(user)
    lvl = user["level"]

    if job is None:
        earned_coins = scale_coins(10, lvl)
        earned_exp   = scale_xp(5, lvl)
        branch       = None
    else:
        base_coins = random.randint(job["min_reward"], job["max_reward"])
        base_exp = random.randint(job["min_exp"], job["max_exp"])
        earned_coins = scale_coins(base_coins, lvl)
        earned_exp = scale_xp(base_exp, lvl)
        earned_coins, earned_exp = apply_pet_bonus(user, earned_coins, earned_exp)
        title_coin_pct, title_xp_pct, _ = get_title_bonus(user)
        earned_coins = int(earned_coins * (1 + title_coin_pct / 100))
        earned_exp = int(earned_exp * (1 + title_xp_pct / 100))
        branch = job["branch"]

        # Ивент-множители
        ev_coins_mult, ev_xp_mult, ev_lucky, _ = get_event_multipliers()
        earned_coins = int(earned_coins * ev_coins_mult)
        earned_exp = int(earned_exp * ev_xp_mult)

    rank = user.get("job_rank", 1)
    if rank > 1:
        mult         = 1 + (rank - 1) * 0.10
        earned_coins = int(earned_coins * mult)
        earned_exp   = int(earned_exp   * mult)

    event_line = ""
    event_prefix = ""
    if random.random() < 0.20:
        _, _, pet_luck = get_pet_bonus(user)
        _, _, title_luck = get_title_bonus(user)
        luck = user.get("luck", 1) + pet_luck + title_luck
        _, _, ev_lucky, _ = get_event_multipliers()
        pos_chance = min(luck * 4 + ev_lucky, 95) / 100
        branch_events = WORK_EVENTS.get(branch, {}) if branch else {}

        if random.random() < pos_chance:
            earned_coins *= 2
            event_prefix  = "🎲 <b>Случайное событие!</b>\n"
            event_line    = (
                random.choice(branch_events["positive"])
                if branch_events.get("positive")
                else "🔥 Удача! Двойная выплата!"
            ) + " <b>(х2 монеты)</b>"
        else:
            earned_coins  = max(1, earned_coins // 2)
            event_prefix  = "🎲 <b>Случайное событие!</b>\n"
            event_line    = (
                random.choice(branch_events["negative"])
                if branch_events.get("negative")
                else "⚠️ Неудачный день. Доход урезан."
            ) + " <b>(х0.5 монеты)</b>"

    new_balance = user["balance"] + earned_coins
    new_exp     = user["exp"]     + earned_exp
    new_energy  = max(0, user["energy"] - energy_cost)

    update_user(
        user["user_id"],
        balance=new_balance, exp=new_exp,
        last_work_time=now, energy=new_energy,
    )
    user = {**user, "balance": new_balance, "exp": new_exp, "energy": new_energy}
    user, level_msgs = auto_level_up(user)
    level_block = "".join(level_msgs)

    ach_msgs = check_and_grant_achievements(user)
    ach_block = ("\n\n" + "\n".join(ach_msgs)) if ach_msgs else ""

    title_msgs = check_and_grant_titles(user)
    title_block = ("\n\n" + "\n".join(title_msgs)) if title_msgs else ""

    quest_msgs = update_quest_progress(user["user_id"], "work")
    quest_msgs += update_quest_progress(user["user_id"], "earn", earned_coins)
    quest_block = ("\n\n" + "\n".join(quest_msgs)) if quest_msgs else ""

    luck_ach_msg = None
    if event_line:
        if "🔥" in event_line:
            change_reputation(user["user_id"], +1)
            luck_ach_msg = grant_achievement_now(user["user_id"], "luck_event")
        elif "⚠️" in event_line:
            change_reputation(user["user_id"], -3)
    bump_stat(user["user_id"], "stat_work_count")
    event_block = f"\n\n{event_prefix}{event_line}" if event_line else ""
    if luck_ach_msg:
        event_block += f"\n\n{luck_ach_msg}"
    max_energy = get_max_energy(user)
    contribute_faculty_points(user["user_id"], max(1, earned_coins // 20))
    return True, (
        f"🛠 Ты поработал как <b>{user['job']}</b>!"
        f"{event_block}\n\n"
        f"💰 Получено: <b>+{earned_coins}</b> монет\n"
        f"✨ Опыт: <b>+{earned_exp}</b>  (всего: {user['exp']} / {xp_needed(user['level'])})\n"
        f"⚡ Энергия: <b>{new_energy}</b> / {max_energy}  (-{energy_cost})\n"
        f"📊 Итого монет: <b>{user['balance']}</b>"
        f"{level_block}"
        f"{ach_block}"
        f"{title_block}"
        f"{quest_block}"
    )
def get_work_cooldown(user: dict) -> int:
    """1 сек. кулдауна снимается за каждые 3 Ловкости, максимум -180 сек, минимум 60 сек."""
    agility = user.get("agility", 1)
    reduction = min(180, agility // 3)
    return max(60, WORK_COOLDOWN - reduction)

def get_charisma_shop_discount(user: dict) -> int:
    """1% скидки за каждые 20 Харизмы, максимум 15%."""
    charisma = user.get("charisma", 1)
    return min(15, charisma // 20)


def apply_price_modifiers(user: dict, price: int) -> int:
    """Скидка/наценка от репутации + скидка от Харизмы, суммарно ограничено -50%..+50%."""
    rep_discount = get_rep_discount(user.get("reputation", 0))
    cha_discount = get_charisma_shop_discount(user)
    total = max(-50, min(50, rep_discount + cha_discount))
    return max(1, int(price * (1 - total / 100)))
# =====================================================================
# ЛОГИКА: НАВЫКИ
# =====================================================================
def build_skills_text(user: dict) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["🧠 <b>Навыки</b>\n"]
    builder = InlineKeyboardBuilder()

    for key, cfg in SKILL_CONFIG.items():
        val  = user.get(key, 0)
        cost = max(cfg["cost_base"], val * cfg["cost_base"])

        unlock = cfg.get("unlock_item")
        locked = unlock and not user.get(unlock)

        lines.append(
            f"{cfg['label']}: <b>{val} ур.</b>\n"
            f"  <i>{cfg['description']}</i>"
        )
        if locked:
            lines.append(f"  🔒 Требуется предмет (Магазин)\n")
        else:
            lines.append(f"  Следующий уровень: <b>{cost} монет</b>\n")
            builder.button(
                text=f"⬆️ {cfg['label']} ({cost} мон.)",
                callback_data=f"upgrade_skill:{key}"
            )

    lines.append(f"\n💰 Баланс: <b>{user['balance']}</b> монет")
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


def do_upgrade_skill(user: dict, skill_key: str) -> tuple[bool, str]:
    cfg = SKILL_CONFIG.get(skill_key)
    if not cfg:
        return False, "❌ Неизвестный навык."

    unlock = cfg.get("unlock_item")
    if unlock and not user.get(unlock):
        return False, "❌ Сначала купи нужный предмет в Магазине."

    val  = user.get(skill_key, 0)
    cost = max(cfg["cost_base"], val * cfg["cost_base"])

    if user["balance"] < cost:
        return False, f"❌ Нужно <b>{cost}</b> монет, есть <b>{user['balance']}</b>."

    update_user(user["user_id"], **{skill_key: val + 1, "balance": user["balance"] - cost})
    return True, (
        f"✅ <b>{cfg['label']}</b> прокачана до уровня <b>{val + 1}</b>!\n"
        f"💰 Потрачено: {cost} монет."
    )

# =====================================================================
# ЛОГИКА: ТРЕНИРОВКИ
# =====================================================================
TRAIN_CONFIG = {
    "intellect": {"name": "📖 Почитать книгу",        "stat_label": "🧠 Интеллект",   "active": True},
    "endurance": {"name": "🏃 Пробежка",              "stat_label": "💪 Выносливость", "active": True},
    "agility":   {"name": "🤸 Акробатика",            "stat_label": "🏃 Ловкость",     "active": True},
    "charisma":  {"name": "🎤 Публичное выступление", "stat_label": "✨ Харизма",       "active": True},
}
TRAIN_TIERS = {
    1:  {"energy_cost": TRAIN_ENERGY_COST, "min_level": 1,  "label": "Обычная"},
    5:  {"energy_cost": 260,               "min_level": 15, "label": "🔥 Усиленная"},
    10: {"energy_cost": 550,               "min_level": 40, "label": "💥 Интенсивная"},
}
def get_stat_train_cap(user: dict) -> int:
    """Лимит стата, накачиваемого тренировкой: 10 на 1 lvl, 20 на 2 lvl и т.д."""
    return user["level"] * 10
def build_training_text(user: dict) -> str:
    max_energy = get_max_energy(user)
    cap = get_stat_train_cap(user)
    tiers_lines = []
    for amount, tier in TRAIN_TIERS.items():
        lock = "" if user["level"] >= tier["min_level"] else f" 🔒 (нужен {tier['min_level']} ур.)"
        tiers_lines.append(f"  • {tier['label']}: +{amount} — {tier['energy_cost']} ⚡{lock}")

    return (
        f"🏋️ <b>Тренировки</b>\n\n"
        f"⚡ Энергия: <b>{user['energy']}</b> / {max_energy}\n\n"
        f"📈 Лимит тренировки на твоём уровне: <b>{cap}</b> (растёт с уровнем: 10 на 1 lvl, 20 на 2 lvl...)\n"
        f"<i>⚡ Энергия восстанавливается только расходниками из Магазина!</i>\n\n"
        f"<b>Виды тренировок:</b>\n" + "\n".join(tiers_lines) + "\n\n"
        f"🏃 Ловкость: -1 сек. кулдауна работы за каждые 5 ед. (сейчас: {get_work_cooldown(user)}с)\n"
        f"✨ Харизма: скидка в 🛒 Магазине (сейчас: -{get_charisma_shop_discount(user)}%)"
    )

def get_training_keyboard(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    stat_emojis = {
        "intellect": ("📖 Почитать книгу", "🧠 Интеллект"),
        "endurance": ("🏃 Пробежка", "💪 Выносливость"),
        "agility":   ("🤸 Акробатика", "🏃 Ловкость"),
        "charisma":  ("🎤 Публичное выступление", "✨ Харизма"),
    }
    for stat, (name, label) in stat_emojis.items():
        for amount, tier in TRAIN_TIERS.items():
            if user["level"] < tier["min_level"]:
                continue
            builder.button(
                text=f"{name} {tier['label']} (-{tier['energy_cost']}⚡) → +{amount} {label}",
                callback_data=TrainCallback(stat=stat, amount=amount).pack()
            )
    builder.adjust(1)
    return builder.as_markup()

def do_train(user: dict, stat: str, amount: int = 1) -> tuple[bool, str]:
    if is_incapacitated(user):
        return False, get_incapacitated_message(user)

    cfg = TRAIN_CONFIG.get(stat)
    if not cfg:
        return False, "❌ Неизвестная тренировка."
    if not cfg["active"]:
        return False, f"🚧 <b>{cfg['name']}</b> пока в разработке. Скоро появится!"

    tier = TRAIN_TIERS.get(amount)
    if not tier:
        return False, "❌ Неизвестный уровень тренировки."
    if user["level"] < tier["min_level"]:
        return False, (
            f"❌ Для «{tier['label']}» нужен уровень <b>{tier['min_level']}</b> "
            f"(у тебя {user['level']})."
        )

    energy_cost = apply_energy_discount(tier["energy_cost"])
    if user["energy"] < energy_cost:
        return False, (
            f"😴 Недостаточно энергии! Нужно {energy_cost} ⚡, "
            f"есть {user['energy']} ⚡."
        )
    new_energy = max(0, user["energy"] - energy_cost)

    cap = get_stat_train_cap(user)
    current_val = user[stat]
    if current_val >= cap:
        return False, (
            f"📈 <b>{cfg['stat_label']}</b> уже на пределе для твоего уровня!\n"
            f"Лимит тренировки: <b>{cap}</b> (10 × уровень {user['level']}).\n"
            f"Повысь уровень, чтобы качать дальше."
        )

    # Если до кап-лимита осталось меньше, чем даёт тир — урезаем прирост
    # и пропорционально снижаем стоимость энергии, чтобы не переплачивать впустую
    actual_amount = min(amount, cap - current_val)
    actual_cost = max(1, round(energy_cost * actual_amount / amount))

    new_energy = max(0, user["energy"] - actual_cost)
    new_stat   = current_val + actual_amount
    update_user(user["user_id"], energy=new_energy, **{stat: new_stat})
    quest_msgs = update_quest_progress(user["user_id"], "train")
    updated    = {**user, stat: new_stat, "energy": new_energy}
    max_energy = get_max_energy(updated)

    tier_note = "" if actual_amount == amount else f" (лимит уровня, дали только +{actual_amount})"

    return True, (
        f"✅ <b>{cfg['name']}</b> ({tier['label']}) завершена!{tier_note}\n\n"
        f"{cfg['stat_label']}: <b>+{actual_amount}</b> → {new_stat} / {cap} (лимит уровня)\n"
        f"⚡ Энергия: <b>{new_energy}</b> / {max_energy}  (-{actual_cost})"
    )
# =====================================================================
# ЛОГИКА: МАГАЗИН
# =====================================================================
def build_shop_text(user: dict) -> str:
    return (
        "🛒 <b>Магазин</b>\n\n"
        "🎒 <b>Снаряжение</b> — предметы для прокачки профессий\n"
        "🍔 <b>Еда и расходники</b> — восстановление HP и энергии\n\n"
        f"💰 Твой баланс: <b>{user['balance']}</b> монет\n\n"
        "Выбери категорию:"
    )
def get_shop_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎒 Снаряжение", callback_data="shop_cat:gear")
    builder.button(text="🍔 Еда и расходники", callback_data="shop_cat:food")
    builder.adjust(2)
    return builder.as_markup()

def get_shop_gear_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, item in SHOP_ITEMS.items():
        builder.button(text=f"{item['name']} — {item['price']} монет", callback_data=ShopCallback(item_key=key).pack())
    builder.button(text="◀ Назад", callback_data="shop_back")
    builder.adjust(1)
    return builder.as_markup()

def build_food_category_text(user: dict) -> str:
    lines = ["🍔 <b>Еда и расходники</b>\n"]
    for item in CONSUMABLES.values():
        effects = []
        if item["hp"] > 0: effects.append(f"+{min(item['hp'],9999)} HP")
        if item["energy"] > 0: effects.append(f"+{min(item['energy'],9999)} ⚡")
        if item["hp"] >= 9999 and item["energy"] >= 9999: effects = ["полное восстановление"]
        lines.append(
            f"{item['name']} — <b>{item['price']} монет</b>  ({', '.join(effects)})\n"
            f"  <i>{item['description']}</i>"
        )
    lines.append(f"\n💰 Баланс: <b>{user['balance']}</b> монет")
    return "\n".join(lines)

def get_shop_food_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, item in CONSUMABLES.items():
        builder.button(text=f"{item['name']} x1",  callback_data=f"consume:{key}:1")
        builder.button(text="x5",  callback_data=f"consume:{key}:5")
        builder.button(text="x10", callback_data=f"consume:{key}:10")
    builder.button(text="◀ Назад", callback_data="shop_back")
    sizes = [3] * len(CONSUMABLES) + [1]
    builder.adjust(*sizes)
    return builder.as_markup()


def do_buy_item(user: dict, item_key: str) -> tuple[bool, str]:
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return False, "❌ Такого товара нет."
    if user.get(item["flag"]):
        return False, f"У тебя уже есть {item['name']}!"
    _, _, _, ev_discount = get_event_multipliers()
    base_price = int(item["price"] * (1 - ev_discount / 100))
    actual_price = apply_price_modifiers(user, base_price)
    if user["balance"] < actual_price:
        return False, (
            f"❌ Недостаточно монет.\n"
            f"Нужно: <b>{actual_price}</b>, есть: <b>{user['balance']}</b>."
        )
    new_balance = user["balance"] - actual_price
    extra = {item["flag"]: 1}
    if "skill_bonus" in item:
        skill_key, skill_bonus = item["skill_bonus"]
        extra[skill_key] = user.get(skill_key, 0) + skill_bonus

    update_user(user["user_id"], balance=new_balance, **extra)
    update_quest_progress(user["user_id"], "spend", item["price"])

    bonus_line = ""
    if "skill_bonus" in item:
        sk, _ = item["skill_bonus"]
        cfg = SKILL_CONFIG.get(sk)
        if cfg:
            bonus_line = f"\n🎁 Бонус: {cfg['label']} +1!"

    return True, (
        f"✅ Ты купил {item['name']}!\n"
        f"💰 Потрачено: <b>{item['price']}</b> монет."
        f"{bonus_line}\n"
        f"<i>{item['description']}</i>"
    )


def do_use_consumable(user: dict, item_key: str, quantity: int = 1) -> tuple[bool, str]:
    item = CONSUMABLES.get(item_key)
    if not item:
        return False, "❌ Такого предмета нет."
    quantity = max(1, min(quantity, 50))  # защита от абсурдных значений

    _, _, _, ev_discount = get_event_multipliers()
    base_price = int(item["price"] * quantity * (1 - ev_discount / 100))
    actual_price = apply_rep_to_price(user, base_price)

    if user["balance"] < actual_price:
        return False, (
            f"❌ Недостаточно монет.\n"
            f"Нужно: <b>{actual_price}</b>, есть: <b>{user['balance']}</b>."
        )

    max_hp     = get_max_hp(user)
    max_energy = get_max_energy(user)
    old_hp     = user["hp"]
    old_energy = user["energy"]
    new_hp     = min(max_hp,     old_hp     + item["hp"]     * quantity)
    new_energy = min(max_energy, old_energy + item["energy"] * quantity)
    new_balance = user["balance"] - actual_price

    update_user(user["user_id"], hp=new_hp, energy=new_energy, balance=new_balance)
    update_quest_progress(user["user_id"], "spend", item["price"] * quantity)

    gained_hp     = new_hp     - old_hp
    gained_energy = new_energy - old_energy
    lines = [f"✅ Использовано {item['name']} x<b>{quantity}</b>!"]
    if gained_hp     > 0: lines.append(f"❤️ HP:     +{gained_hp} → {new_hp} / {max_hp}")
    if gained_energy > 0: lines.append(f"⚡ Энергия: +{gained_energy} → {new_energy} / {max_energy}")
    if gained_hp == 0 and gained_energy == 0:
        lines.append("ℹ️ Ресурсы уже на максимуме — часть предметов потрачена впустую!")
    lines.append(f"💰 Потрачено: {actual_price} монет")
    return True, "\n".join(lines)
# =====================================================================
# ПРОФИЛЬ
# =====================================================================
def build_profile_text(user: dict, mention: str) -> str:
    lvl        = user["level"]
    needed_xp  = xp_needed(lvl)
    max_hp     = get_max_hp(user)
    max_energy = get_max_energy(user)
    rank       = user.get("job_rank", 1)
    job        = get_job(user)
    grade      = job["grade"] if job else 0
    rep = user.get("reputation", 0)
    rep_title, _ = get_rep_title(rep)
    active_title = user.get("active_title", "")
    title_line = f"🎖 Титул: <b>{TITLES[active_title]['name']}</b>\n" if active_title in TITLES else ""
    spouse_id_val = user.get("spouse_id")
    spouse_line = ""
    if spouse_id_val:
        spouse_data = get_user(spouse_id_val)
        if spouse_data:
            spouse_name_val = spouse_data.get("username") or f"#{spouse_id_val}"
            spouse_line = f"💍 Супруг(а): <b>{spouse_name_val}</b>\n"

    inv_parts = []
    for key, item in SHOP_ITEMS.items():
        if user.get(item["flag"]):
            inv_parts.append(item["name"])
    inventory_str = ", ".join(inv_parts) if inv_parts else "пусто"

    skills_lines = []
    for sk, cfg in SKILL_CONFIG.items():
        val = user.get(sk, 0)
        if val > 0:
            skills_lines.append(f"{cfg['label']}: <b>{val} ур.</b>")
    if not skills_lines:
        skills_lines = ["(навыки ещё не прокачаны)"]

    return (
        f"👤 <b>Профиль</b> {mention}\n\n"
        f"💼 Профессия: <b>{user['job']}</b>"
        + (f"  [Грейд {grade}/9, Ранг {rank}]" if grade > 0 else "") + "\n"
        f"{title_line}"                                                               
        f"⭐ Уровень: <b>{lvl}</b>\n"
        f"⭐ Репутация:     <b>{rep}</b> ({rep_title})\n"
        f"🔄 Перерождений: <b>{user.get('rebirths', 0)}</b> "
        f"(бонус: +{user.get('rebirths', 0) * REBIRTH_COIN_BONUS_PER}% монет, "
        f"+{user.get('rebirths', 0) * REBIRTH_XP_BONUS_PER}% опыта)\n"                                                               
        f"{spouse_line}"                                                               
        f"✨ Опыт: <b>{user['exp']}</b> / {needed_xp}\n"
        f"💰 Баланс: <b>{user['balance']}</b> монет\n"
        f"🔶 Осколки: <b>{user.get('shards', 0)}</b>\n"
        f"🌌 Кристаллы Вознесения: <b>{user.get('ascension_crystals', 0)}</b>\n\n"                                                               
        f"━━━ 💗 Ресурсы ━━━\n"
        f"❤️ Здоровье:  <b>{user['hp']}</b> / {max_hp}\n"
        f"⚡ Энергия:   <b>{user['energy']}</b> / {max_energy}\n"
        f"<i>Восстановление — через расходники в Магазине</i>\n\n"
        f"━━━ 📊 Характеристики ━━━\n"
        f"🏃 Ловкость:      <b>{user['agility']}</b>\n"
        f"💪 Выносливость:  <b>{user['endurance']}</b>\n"
        f"✨ Харизма:       <b>{user['charisma']}</b>\n"
        f"🧠 Интеллект:     <b>{user['intellect']}</b>\n"
        f"🍀 Удача:         <b>{user['luck']}</b>\n\n"
        f"━━━ 🗣 Навыки ━━━\n"
        + "\n".join(skills_lines) + "\n\n"
        f"━━━ 🎒 Инвентарь ━━━\n"
        f"{inventory_str}"
    )

# =====================================================================
# ГЛАВНОЕ МЕНЮ
# =====================================================================
def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"),      KeyboardButton(text="💼 Профессии")],
            [KeyboardButton(text="🛠 Работа"),        KeyboardButton(text="🏋️ Тренировки")],
            [KeyboardButton(text="🧠 Навыки"),        KeyboardButton(text="🛒 Магазин")],
            [KeyboardButton(text="🏠 Недвижимость"),  KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🎁 Ежедневный"),    KeyboardButton(text="🔗 Пригласить друзей")],
        ],
        resize_keyboard=True,
        persistent=True,
    )

# =====================================================================
# БИРЖА
# =====================================================================
STOCK_MIN_BET = 100
STOCK_OUTCOMES = ["ап"] * 18 + ["давн"] * 18 + ["нейтрал"] * 2

# Множитель выплаты (сколько раз от ставки игрок получает как ПРОФИТ, помимо возврата ставки)
STOCK_PAYOUT_MULT = {
    "ап":      1,
    "давн":    1,
    "нейтрал": 20,   # редкий исход (2/38 ≈ 5.3%) — джекпот
}

STOCK_LABELS = {
    "ап":      "📈 АП (рынок вырос)",
    "давн":    "📉 ДАВН (рынок упал)",
    "нейтрал": "➡️ НЕЙТРАЛ (флэт)",
}

STOCK_WIN_PHRASES = [
    "🎯 Вы поймали тренд как настоящий трейдер КТУ!",
    "🤑 Уоррен Баффет из Джала гордился бы вами!",
    "📊 Анализ — огонь! Депозит пополнен!",
    "🚀 Вы в плюсе! Биржа покорилась!",
]
STOCK_LOSE_PHRASES = [
    "📉 Рынок — это не Джал-Маркет, тут цены не фиксированные...",
    "💀 Стоп-лосс не спас. Ставка сгорела дотла.",
    "😭 Инвестиции — это риск. Особенно твои.",
    "🔥 Ставка улетела вместе с надеждами.",
]

def do_stock_bet(user: dict, outcome_input: str, bet: int) -> tuple[bool, str]:
    outcome_input = outcome_input.strip().lower()

    if outcome_input not in ("ап", "давн", "нейтрал"):
        return False, (
            "❌ Неверный исход.\n"
            "Используй: <b>акция ап [сумма]</b>, <b>акция давн [сумма]</b> "
            "или <b>акция нейтрал [сумма]</b>"
        )

    if bet < STOCK_MIN_BET:
        return False, f"❌ Минимальная ставка: <b>{STOCK_MIN_BET}</b> монет."

    if user["balance"] < bet:
        return False, (
            f"❌ Недостаточно монет.\n"
            f"Ставка: <b>{bet}</b> | Баланс: <b>{user['balance']}</b>"
        )

    market_result = random.choice(STOCK_OUTCOMES)
    market_label  = STOCK_LABELS[market_result]
    won           = (outcome_input == market_result)

    if won:
        mult = STOCK_PAYOUT_MULT.get(outcome_input, 1)
        profit = apply_full_coin_bonus(user, bet * mult)
        new_balance = user["balance"] + profit
        update_user(user["user_id"], balance=new_balance)
        change_reputation(user["user_id"], +1)
        bump_stat(user["user_id"], "stat_stock_wins")
        update_quest_progress(user["user_id"], "stock")
        stock_ach_msg = grant_achievement_now(user["user_id"], "stock_win")
        updated = get_user(user["user_id"])
        if updated:
            check_and_grant_achievements(updated)
        phrase = random.choice(STOCK_WIN_PHRASES)
        mult_line = f"\n🎲 Множитель: <b>x{mult}</b>" if mult > 1 else ""
        text = (
            f"📊 <b>Рынок пришёл в движение!</b>\n"
            f"График пошёл: <b>{market_label}</b>\n\n"
            f"🎉 <b>Вы угадали тренд!</b>\n"
            f"{phrase}{mult_line}\n\n"
            f"💰 Выигрыш: <b>+{profit}</b> монет\n"
            f"📈 Баланс: <b>{new_balance}</b> монет"
        )
        if stock_ach_msg:
            text += f"\n\n{stock_ach_msg}"
    else:
        new_balance = user["balance"] - bet
        update_user(user["user_id"], balance=new_balance)
        change_reputation(user["user_id"], -2)
        bump_stat(user["user_id"], "stat_stock_losses")
        phrase = random.choice(STOCK_LOSE_PHRASES)
        player_label = STOCK_LABELS[outcome_input]
        text = (
            f"📊 <b>Рынок пришёл в движение!</b>\n"
            f"Ты ставил на: <b>{player_label}</b>\n"
            f"График пошёл: <b>{market_label}</b>\n\n"
            f"📉 <b>Мимо!</b>\n"
            f"{phrase}\n\n"
            f"💸 Потеря: <b>-{bet}</b> монет\n"
            f"📉 Баланс: <b>{new_balance}</b> монет"
        )

    return True, text

# =====================================================================
# МОДУЛЬ «БУНКЕР»
# =====================================================================
BUNKER_CLASSIC = {
    "disasters": [
        "☢️ <b>Ядерная война</b>\n"
        "Мировые сверхдержавы нажали кнопки. Горизонт пылает. "
        "Радиационный фон смертелен. У вас есть считанные минуты, "
        "чтобы скрыться в бункере.",

        "🧟 <b>Зомби-вирус «Штамм-Х»</b>\n"
        "Неизвестный патоген превращает людей в агрессивных мертвецов. "
        "Правительства рухнули. Единственный шанс на выживание — "
        "изоляция в бункере.",

        "🌊 <b>Всемирный потоп</b>\n"
        "Полюса стремительно тают, уровень океана поднялся на 50 метров. "
        "Большинство городов под водой. Суша осталась только в горах. "
        "Бункер — последнее сухое убежище.",

        "☄️ <b>Падение астероида</b>\n"
        "Астероид диаметром 2 км вошёл в атмосферу. Ударная волна "
        "сметает всё в радиусе 500 км. Пылевое облако накроет Землю "
        "на десятилетия. Бункер — единственный шанс.",
    ],
    "bunker_desc": (
        "🏗 <b>Бункер:</b> Классическое подземное убежище глубиной 50 м. "
        "Гермодвери, система фильтрации воздуха, запас консервов на 5 лет, "
        "дизельный генератор, медотсек и библиотека."
    ),
    "professions": [
        "👨‍⚕️ Врач общей практики",
        "🔧 Инженер-механик",
        "🔬 Учёный-биохимик",
        "🪖 Военный (спецназ)",
        "🌾 Агроном",
        "👩‍🍳 Шеф-повар",
        "🧑‍💻 IT-специалист",
        "🧑‍🏫 Педагог",
        "🧰 Сантехник",
        "📻 Радиоинженер",
    ],
    "baggage": [
        "🔫 Охотничье ружьё с патронами",
        "💊 Большая аптечка",
        "🌱 Семена овощей (годовой запас)",
        "📖 Энциклопедия выживания",
        "🔋 Солнечная панель + аккумулятор",
        "🔪 Многофункциональный нож",
        "📡 Портативная рация",
        "🧲 Набор инструментов",
        "🌡️ Счётчик Гейгера",
        "🥫 Запас консервов на 6 месяцев",
    ],
    "hobbies": [
        "🏹 Охота и рыбалка",
        "📚 Чтение и самообразование",
        "🍳 Кулинария",
        "🎸 Игра на гитаре",
        "🧘 Йога и медитация",
        "🌿 Огородничество",
        "🛠 Слесарное дело",
        "🎲 Настольные игры",
    ],
    "facts": [
        "💰 Тайный миллионер — владеет оффшорным счётом",
        "🦠 Имеет природный иммунитет к вирусу",
        "🎖 Бывший агент ЦРУ",
        "🩸 Универсальный донор крови (I группа)",
        "🧬 Несёт ключевые гены для восстановления генофонда",
        "⚡ Умеет собирать генератор из подручных материалов",
        "🗺 Знает расположение всех бункеров страны",
        "🔐 Бывший взломщик сейфов",
    ],
}

BUNKER_MANAS = {
    "disaster": (
        "📋 <b>КАТАСТРОФА: Тотальная проверка ректората!</b>\n\n"
        "Ректорат объявил внезапную тотальную проверку посещаемости "
        "и Сом-сынав (экзамен) по ВСЕМ предметам за ВСЕ 4 года. "
        "Деканы с ведомостями идут по коридорам. "
        "Всех, кто не пройдёт — отчислят без права восстановления!\n"
        "Единственный выход — успеть спрятаться в Бункере!"
    ),
    "bunkers": [
        (
            "🍵 <b>Бункер: Секретный подвал корпуса Джал</b>\n"
            "Здесь хранится бесконечный запас турецкого чая и симитов. "
            "Wi-Fi не ловит (деканат не найдёт), зато есть розетки и "
            "старый диван. Вместимость ограничена."
        ),
        (
            "🎧 <b>Бункер: Заброшенная аудитория синхронного перевода</b>\n"
            "Сюда вообще не поступает сигнал деканата — "
            "глушилка для связи работает ещё с 2009 года. "
            "Есть наушники, сломанный проектор и вечно закрытая доска. "
            "Охранники сюда не заходят принципиально."
        ),
        (
            "🏛 <b>Бункер: Кабинет ректора</b>\n"
            "Ректор срочно улетел в Анкару на конференцию. "
            "Кожаные кресла, кофемашина, холодильник с едой. "
            "Секретарша подкуплена симитами и молчит. "
            "Самое комфортное место в университете."
        ),
    ],
    "professions": [
        "📚 Вечный студент подготовительного курса (Хазырлык)",
        "🗣 Отличник-коммуникатор с Факультета Филологии (ФФ)",
        "🍲 Повар на раздаче из столовой корпуса Джал",
        "🚌 Студент, у которого пары на Турусбекова, а он в Джале",
        "📋 Активист-Староста своей группы",
        "🎮 Геймер с кафедры ИТ",
        "💅 Красотка с ФГиЭ (Факультет Гуманитарных и Экономических наук)",
        "⚽ Спортсмен из студенческой сборной КТУ",
        "🎵 Участник студенческого ансамбля «Жаштык»",
        "🏆 Победитель университетской олимпиады по математике",
    ],
    "baggage": [
        "🥐 Коробка свежих симитов (ещё тёплых)",
        "💾 Флешка с ответами на Сом-сынав 2025 года",
        "🪪 Студенческий билет с подписью самого ректора",
        "🫕 Огромный казан для плова (на 40 персон)",
        "📝 Шпаргалка, написанная микрошрифтом 2pt на туалетной бумаге",
        "📱 Телефон с 100% зарядкой и безлимитом",
        "🔑 Ключи от всех аудиторий корпуса Джал",
        "🎁 Коробка турецких конфет для задабривания охраны",
        "💻 Ноутбук с пиратским Office и VPN",
        "🧃 Упаковка турецкого чая (50 пакетиков)",
    ],
    "characters": [
        "😴 Спит на первой парте даже во время Сом-сынава",
        "🤝 Умеет договариваться с охранниками через шоколадку",
        "🚌 Постоянно опаздывает на маршрутку №100",
        "🌙 Прогуливает пары ради чиллаута у фонтана",
        "📸 Фотографирует всё для студенческих пабликов",
        "🔕 Никогда не отвечает на звонки деканата",
        "☕ Не может жить без кофе из автомата в коридоре",
        "📊 Делает красивые таблицы в Excel для каждой мелочи",
    ],
    "hobbies": [
        "🎮 Играть в корейские ММО прямо на парах",
        "🎤 Петь на фестивалях и вечерах Манаса",
        "😤 Жаловаться на еду в столовой (но всё равно есть там каждый день)",
        "💬 Писать мемы в студенческие паблики ВКонтакте",
        "🎶 Слушать турецкие сериалы в оригинале",
        "🛒 Ходить за едой в Джал-Маркет во время лекций",
        "📺 Смотреть аниме в читальном зале библиотеки",
        "🃏 Играть в карты в общаге вместо подготовки к сессии",
    ],
    "facts": [
        "👨‍👩‍👦 Двоюродный племянник замдекана по учебной части",
        "🏃 Ни разу в жизни не был на физкультуре (и гордится этим)",
        "☕ Умеет варить идеальный турецкий кофе в турке",
        "📶 Знает секретный пароль от Wi-Fi ректората",
        "🔑 Имеет дубликат ключа от деканата (откуда — не говорит)",
        "📱 Его номер есть в телефоне у самого ректора",
        "🎓 Написал дипломную работу за одну ночь и получил «А»",
        "🃏 Профессиональный переписчик чужих конспектов за деньги",
    ],
}

bunker_games: dict[int, "BunkerGame"] = {}
BUNKER_REGISTRATION_SECONDS = 120

class BunkerGame:
    def __init__(self, chat_id: int, creator_id: int, creator_name: str, mode: str):
        self.chat_id      = chat_id
        self.creator_id   = creator_id
        self.creator_name = creator_name
        self.mode         = mode

        self.players: dict[int, dict] = {}
        self.phase = "registration"
        self.disaster_text   = ""
        self.bunker_text     = ""
        self.survivors_limit = 0
        self.round_votes: dict[int, int] = {}
        self.eliminated: list[int] = []
        self.reg_deadline = int(time.time()) + BUNKER_REGISTRATION_SECONDS

    def _generate_card(self) -> dict:
        if self.mode == "classic":
            p = BUNKER_CLASSIC
            return {
                "profession": random.choice(p["professions"]),
                "baggage":    random.choice(p["baggage"]),
                "hobby":      random.choice(p["hobbies"]),
                "fact":       random.choice(p["facts"]),
                "revealed":   set(),
            }
        else:
            p = BUNKER_MANAS
            return {
                "profession": random.choice(p["professions"]),
                "baggage":    random.choice(p["baggage"]),
                "character":  random.choice(p["characters"]),
                "hobby":      random.choice(p["hobbies"]),
                "fact":       random.choice(p["facts"]),
                "revealed":   set(),
            }

    def start_game(self):
        n = len(self.players)
        self.survivors_limit = max(1, n // 2)

        if self.mode == "classic":
            self.disaster_text = random.choice(BUNKER_CLASSIC["disasters"])
            self.bunker_text   = BUNKER_CLASSIC["bunker_desc"]
        else:
            self.disaster_text = BUNKER_MANAS["disaster"]
            self.bunker_text   = random.choice(BUNKER_MANAS["bunkers"])

        for uid in self.players:
            self.players[uid]["card"] = self._generate_card()

        self.phase = "active"

    def card_text(self, user_id: int) -> str:
        card = self.players[user_id]["card"]
        if self.mode == "classic":
            return (
                f"🃏 <b>Твоя карта персонажа</b>\n\n"
                f"💼 Профессия: <b>{card['profession']}</b>\n"
                f"🎒 Багаж: <b>{card['baggage']}</b>\n"
                f"🎮 Хобби: <b>{card['hobby']}</b>\n"
                f"🔍 Секретный факт: <b>{card['fact']}</b>\n\n"
                f"<i>Открывай характеристики командой:</i>\n"
                f"<code>открыть профессия</code> / <code>открыть багаж</code> / "
                f"<code>открыть хобби</code> / <code>открыть факт</code>"
            )
        else:
            return (
                f"🃏 <b>Твоя карта студента</b>\n\n"
                f"🎓 Факультет/роль: <b>{card['profession']}</b>\n"
                f"🎒 Багаж: <b>{card['baggage']}</b>\n"
                f"😏 Черта характера: <b>{card['character']}</b>\n"
                f"🎮 Хобби: <b>{card['hobby']}</b>\n"
                f"🔍 Секрет: <b>{card['fact']}</b>\n\n"
                f"<i>Открывай характеристики командой:</i>\n"
                f"<code>открыть факультет</code> / <code>открыть багаж</code> / "
                f"<code>открыть характер</code> / <code>открыть хобби</code> / "
                f"<code>открыть секрет</code>"
            )

    def reveal(self, user_id: int, attr_raw: str) -> tuple[bool, str]:
        if user_id not in self.players:
            return False, "Ты не участвуешь в этой игре."
        if self.phase != "active":
            return False, "Сейчас не фаза обсуждения."

        card = self.players[user_id]["card"]
        name = self.players[user_id]["name"]

        mapping_classic = {
            "профессия": "profession", "профессию": "profession",
            "багаж": "baggage",
            "хобби": "hobby",
            "факт": "fact", "секрет": "fact",
        }
        mapping_manas = {
            "факультет": "profession", "роль": "profession",
            "багаж": "baggage",
            "характер": "character", "черта": "character",
            "хобби": "hobby",
            "секрет": "fact", "факт": "fact",
        }
        mapping = mapping_classic if self.mode == "classic" else mapping_manas
        key = mapping.get(attr_raw.lower())

        if not key or key not in card:
            valid = " / ".join(f"<code>{k}</code>" for k in mapping)
            return False, f"Неизвестная характеристика. Доступны: {valid}"

        if key in card["revealed"]:
            label = {
                "profession": "Профессия/Факультет",
                "baggage":    "Багаж",
                "character":  "Характер",
                "hobby":      "Хобби",
                "fact":       "Секрет",
            }.get(key, key)
            return False, f"Ты уже открывал <b>{label}</b>!"

        card["revealed"].add(key)
        label_map = {
            "profession": "💼 Профессия/Факультет",
            "baggage":    "🎒 Багаж",
            "character":  "😏 Черта характера",
            "hobby":      "🎮 Хобби",
            "fact":       "🔍 Секретный факт",
        }
        label = label_map.get(key, key)
        return True, f"📢 <b>{name}</b> открывает {label}:\n<b>{card[key]}</b>"

    def vote(self, voter_id: int, target_id: int) -> tuple[bool, str]:
        if voter_id not in self.players:
            return False, "Ты не в игре."
        if target_id not in self.players:
            return False, "Такого игрока нет в игре."
        if voter_id == target_id:
            return False, "Нельзя голосовать против себя!"
        if self.phase != "voting":
            return False, "Сейчас не фаза голосования."
        self.round_votes[voter_id] = target_id
        return True, f"✅ Твой голос принят против <b>{self.players[target_id]['name']}</b>."

    def count_votes(self) -> tuple[int | None, str]:
        if not self.round_votes:
            return None, "Никто не проголосовал — голосование не засчитано."

        tally: dict[int, int] = {}
        for target in self.round_votes.values():
            tally[target] = tally.get(target, 0) + 1

        max_votes  = max(tally.values())
        candidates = [uid for uid, v in tally.items() if v == max_votes]
        loser_id   = random.choice(candidates)

        loser_name = self.players[loser_id]["name"]
        self.eliminated.append(loser_id)
        del self.players[loser_id]
        self.round_votes.clear()

        lines = ["📊 <b>Итоги голосования:</b>"]
        for uid, cnt in sorted(tally.items(), key=lambda x: -x[1]):
            pname = self.players.get(uid, {}).get("name", f"#{uid}")
            lines.append(f"  • {pname}: {cnt} голос(а)")

        if self.mode == "manas":
            lines.append(
                f"\n😱 <b>{loser_name}</b> поймали деканы и отправили "
                f"на отчисление без права восстановления!"
            )
        else:
            lines.append(
                f"\n☠️ <b>{loser_name}</b> выдворен из бункера и остаётся "
                f"лицом к лицу с катастрофой!"
            )

        if len(self.players) <= self.survivors_limit:
            self.phase = "finished"

        return loser_id, "\n".join(lines)

    def final_text(self) -> str:
        survivors = list(self.players.values())
        names     = [p["name"] for p in survivors]
        names_str = "\n".join(f"  🏅 {n}" for n in names)

        if self.mode == "manas":
            story = (
                f"Пока деканы бушевали по коридорам с ведомостями, "
                f"наши герои тихо сидели в бункере, попивали турецкий чай "
                f"и делали вид, что очень заняты. "
                f"Когда проверка закончилась, они вышли с невинными лицами "
                f"и записались на пересдачу. Победа!"
            )
            title = "🎓 Спаслись от отчисления!"
        else:
            story = (
                f"Прошли месяцы. Выжившие наладили быт, установили дежурства "
                f"и начали строить новое общество. "
                f"Когда фон снизился и опасность миновала, "
                f"они вышли наружу — основателями нового мира."
            )
            title = "🏆 Выжившие в бункере!"

        return (
            f"🎉 <b>ИГРА ОКОНЧЕНА!</b>\n\n"
            f"🔒 <b>{title}</b>\n{names_str}\n\n"
            f"📖 <i>{story}</i>"
        )

    def vote_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for uid, data in self.players.items():
            builder.button(
                text=f"👎 {data['name']}",
                callback_data=BunkerVoteCallback(
                    target_id=uid, chat_id=self.chat_id
                ).pack()
            )
        builder.adjust(1)
        return builder.as_markup()

    def join_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🚪 Участвовать",
            callback_data=BunkerJoinCallback(chat_id=self.chat_id).pack()
        )
        builder.adjust(1)
        return builder.as_markup()


def _bunker_active(chat_id: int) -> "BunkerGame | None":
    g = bunker_games.get(chat_id)
    return g if g and g.phase != "finished" else None


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("бункер создать"))
)
async def bunker_create(message: Message):
    chat_id    = message.chat.id
    creator_id = message.from_user.id

    if _bunker_active(chat_id):
        await message.answer("⚠️ В этом чате уже идёт игра «Бункер»! Дождись её завершения.")
        return

    text_lower = message.text.strip().lower()

    if "манас" in text_lower:
        mode = "manas"
    elif "обычный" in text_lower or "классик" in text_lower:
        mode = "classic"
    else:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🏫 Режим «Манас» (КТУ-студенты)",
            callback_data=BunkerModeCallback(mode="manas").pack()
        )
        builder.button(
            text="☢️ Режим «Обычный» (классический апокалипсис)",
            callback_data=BunkerModeCallback(mode="classic").pack()
        )
        builder.adjust(1)
        await message.answer(
            "🏗 <b>Создание игры «Бункер»</b>\n\nВыберите режим:",
            reply_markup=builder.as_markup()
        )
        return

    await _start_bunker_registration(message, creator_id, mode)


@dp.callback_query(BunkerModeCallback.filter())
async def bunker_mode_chosen(callback: CallbackQuery, callback_data: BunkerModeCallback):
    chat_id    = callback.message.chat.id
    creator_id = callback.from_user.id

    if _bunker_active(chat_id):
        await callback.answer("Игра уже идёт!", show_alert=True)
        return

    await callback.answer()
    await _start_bunker_registration(callback.message, creator_id, callback_data.mode)


async def _start_bunker_registration(message: Message, creator_id: int, mode: str):
    chat_id = message.chat.id
    creator_name = (
        message.from_user.full_name
        if hasattr(message, "from_user") and message.from_user
        else "Организатор"
    )

    game = BunkerGame(chat_id, creator_id, creator_name, mode)
    game.players[creator_id] = {"name": creator_name, "card": {}}
    bunker_games[chat_id] = game

    mode_label = "🏫 Режим «Манас»" if mode == "manas" else "☢️ Режим «Обычный»"
    await message.answer(
        f"🏗 <b>Открыта регистрация в «Бункер»!</b>\n"
        f"{mode_label}\n\n"
        f"👤 Создал: <b>{creator_name}</b>\n"
        f"⏳ Регистрация открыта <b>{BUNKER_REGISTRATION_SECONDS // 60} минуты</b>.\n\n"
        f"Напиши <b>+</b> в чате или нажми кнопку ниже, чтобы войти!\n"
        f"Когда все готовы — создатель пишет <code>бункер старт</code>.",
        reply_markup=game.join_keyboard()
    )


@dp.callback_query(BunkerJoinCallback.filter())
async def bunker_join_button(callback: CallbackQuery, callback_data: BunkerJoinCallback):
    chat_id = callback_data.chat_id
    game    = bunker_games.get(chat_id)
    if not game or game.phase != "registration":
        await callback.answer("Регистрация уже закрыта.", show_alert=True)
        return

    uid  = callback.from_user.id
    name = callback.from_user.full_name
    if uid in game.players:
        await callback.answer("Ты уже в списке!", show_alert=True)
        return

    game.players[uid] = {"name": name, "card": {}}
    await callback.answer(f"✅ Ты в игре, {name}!", show_alert=True)
    await bot.send_message(chat_id,
        f"✅ <b>{name}</b> вошёл в бункер! "
        f"Всего игроков: <b>{len(game.players)}</b>"
    )


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("бункер старт", "бункер start"))
)
async def bunker_start(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)

    if not game:
        await message.answer("❌ Нет активной игры. Начни с <code>бункер создать</code>.")
        return
    if game.phase != "registration":
        await message.answer("⚠️ Игра уже началась!")
        return
    if message.from_user.id != game.creator_id:
        await message.answer("❌ Только создатель игры может её запустить.")
        return
    if len(game.players) < 2:
        await message.answer("❌ Нужно хотя бы 2 игрока для начала!")
        return

    game.start_game()
    n     = len(game.players)
    limit = game.survivors_limit

    await message.answer(
        f"🚨 <b>ИГРА «БУНКЕР» НАЧАЛАСЬ!</b>\n\n"
        f"{game.disaster_text}\n\n"
        f"{game.bunker_text}\n\n"
        f"👥 Игроков: <b>{n}</b> | В бункер попадут: <b>{limit}</b>\n"
        f"Остальные останутся снаружи..."
    )

    failed = []
    for uid, data in game.players.items():
        try:
            await bot.send_message(uid, game.card_text(uid))
        except Exception:
            failed.append(data["name"])

    players_list = "\n".join(f"  • {d['name']}" for d in game.players.values())
    msg = (
        f"📋 <b>Список игроков:</b>\n{players_list}\n\n"
        f"📬 Карты персонажей отправлены в личные сообщения!\n\n"
        f"<b>Фаза обсуждения:</b>\n"
        f"Открывайте характеристики командой <code>открыть [характеристика]</code> "
        f"прямо в этом чате.\n"
        f"Аргументируйте, почему ВЫ нужны в бункере!\n\n"
        f"Когда наговорились — создатель пишет <code>бункер голосование</code>."
    )
    if failed:
        msg += f"\n\n⚠️ Не удалось доставить карту: {', '.join(failed)} " \
               f"(возможно, не начали диалог с ботом)."
    await message.answer(msg)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("открыть "))
)
async def bunker_reveal(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)
    if not game or game.phase != "active":
        return

    attr = message.text.strip()[len("открыть "):].strip()
    ok, text = game.reveal(message.from_user.id, attr)
    if ok or "не участвуешь" in text or "Неизвестная" in text or "уже открывал" in text:
        await message.answer(text)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("бункер голосование", "бункер голосовать"))
)
async def bunker_vote_start(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)

    if not game:
        await message.answer("❌ Нет активной игры.")
        return
    if game.phase not in ("active", "voting"):
        await message.answer("⚠️ Голосование сейчас недоступно.")
        return
    if message.from_user.id != game.creator_id:
        await message.answer("❌ Только создатель игры запускает голосование.")
        return
    if len(game.players) <= 1:
        await message.answer("Остался один игрок — игра завершена.")
        return

    game.phase = "voting"
    game.round_votes.clear()
    await message.answer(
        f"🗳 <b>Голосование!</b>\n"
        f"Кого выгоняем из бункера?\n"
        f"Нажмите на кнопку или напишите <code>кик @username</code>.",
        reply_markup=game.vote_keyboard()
    )


@dp.callback_query(BunkerVoteCallback.filter())
async def bunker_vote_button(callback: CallbackQuery, callback_data: BunkerVoteCallback):
    chat_id   = callback_data.chat_id
    target_id = callback_data.target_id
    game      = bunker_games.get(chat_id)

    if not game or game.phase != "voting":
        await callback.answer("Голосование недоступно.", show_alert=True)
        return

    ok, text = game.vote(callback.from_user.id, target_id)
    await callback.answer(text[:200], show_alert=not ok)

    if ok:
        active_voters = set(game.players.keys())
        voted         = set(game.round_votes.keys())
        if active_voters == voted:
            await _finish_vote_round(callback.message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("кик "))
)
async def bunker_kick_text(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)
    if not game or game.phase != "voting":
        return

    target_id   = None
    target_name = None
    if message.entities:
        for ent in message.entities:
            if ent.type == "mention":
                username = message.text[ent.offset + 1: ent.offset + ent.length]
                for uid, data in game.players.items():
                    if data["name"].lstrip("@").lower() == username.lower():
                        target_id   = uid
                        target_name = data["name"]
                        break
            elif ent.type == "text_mention" and ent.user:
                target_id   = ent.user.id
                target_name = ent.user.full_name
                break

    if target_id is None:
        raw = message.text.strip()[len("кик "):].strip().lower().lstrip("@")
        for uid, data in game.players.items():
            if data["name"].lower() == raw:
                target_id   = uid
                target_name = data["name"]
                break

    if target_id is None:
        await message.answer("❌ Игрок не найден. Убедись, что он в списке игроков.")
        return

    ok, text = game.vote(message.from_user.id, target_id)
    await message.answer(text)

    if ok:
        active_voters = set(game.players.keys())
        voted         = set(game.round_votes.keys())
        if active_voters == voted:
            await _finish_vote_round(message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("бункер итог", "бункер результат"))
)
async def bunker_vote_end(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)
    if not game or game.phase != "voting":
        await message.answer("❌ Сейчас нет активного голосования.")
        return
    if message.from_user.id != game.creator_id:
        await message.answer("❌ Только создатель подводит итоги голосования.")
        return
    await _finish_vote_round(message, game)


async def _finish_vote_round(message: Message, game: BunkerGame):
    _, result_text = game.count_votes()
    await message.answer(result_text)

    if game.phase == "finished":
        await message.answer(game.final_text())
        del bunker_games[game.chat_id]
    else:
        remaining = len(game.players)
        need      = game.survivors_limit
        await message.answer(
            f"👥 Осталось игроков: <b>{remaining}</b> (нужно выбыть ещё "
            f"<b>{remaining - need}</b>)\n\n"
            f"Продолжайте обсуждение! Когда готовы — <code>бункер голосование</code>."
        )


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("бункер статус", "бункер status"))
)
async def bunker_status(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)
    if not game:
        await message.answer("Активной игры «Бункер» нет.")
        return

    phase_labels = {
        "registration": "📝 Регистрация",
        "active":       "💬 Обсуждение",
        "voting":       "🗳 Голосование",
        "finished":     "✅ Завершена",
    }
    players_list = "\n".join(f"  • {d['name']}" for d in game.players.values())
    mode_label = "🏫 Манас" if game.mode == "manas" else "☢️ Обычный"
    await message.answer(
        f"🏗 <b>Игра «Бункер»</b>\n"
        f"Режим: {mode_label}\n"
        f"Фаза: {phase_labels.get(game.phase, game.phase)}\n"
        f"Игроков: <b>{len(game.players)}</b> (бункер вмещает {game.survivors_limit})\n\n"
        f"<b>Участники:</b>\n{players_list}"
    )


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("бункер отмена", "бункер стоп"))
)
async def bunker_cancel(message: Message):
    chat_id = message.chat.id
    game    = _bunker_active(chat_id)
    if not game:
        await message.answer("Нет активной игры для отмены.")
        return
    if message.from_user.id != game.creator_id:
        await message.answer("❌ Только создатель может отменить игру.")
        return
    del bunker_games[chat_id]
    await message.answer("🚫 Игра «Бункер» отменена.")


# =====================================================================
# ТЕКСТ ПОМОЩИ
# =====================================================================
HELP_CATEGORIES = {
    "main": {
        "label": "🏠 Главное меню помощи",
        "text": (
            "📋 <b>Команды МанасWorker</b>\n\n"
            "Выбери раздел:"
        ),
    },
    "character": {
        "label": "👤 Персонаж и развитие",
        "text": (
            "👤 <b>Персонаж и развитие</b>\n\n"
            "<b>Профиль</b> — уровень, баланс, характеристики\n"
            "<b>Профессии</b> — выбор и повышение грейда\n"
            "<b>Титулы</b> — уникальные баффы за достижения (/titles)\n"
            "<b>Тренировки</b> — прокачать Интеллект/Выносливость\n"
            "<b>Навыки</b> — Коммуникация, Вождение, Сервис и др.\n"
            "<b>Магазин</b> — снаряжение и еда\n"
            "<b>Работа</b> — отработать смену (+монеты, +XP)\n"
            "<b>Статистика</b> / /stats — твоя статистика: смены, дуэли, покер, "
            "биржа и т.д.\n"
            "<b>покушать [название] [xN]</b> — быстро съесть предмет из магазина\n\n"
            "📊 Репутация влияет на скидки в магазине!\n"
            "🐾 Питомцы дают бонусы к монетам, XP и удаче."
        ),
    },
    "economy": {
        "label": "💰 Экономика и биржа",
        "text": (
            "💰 <b>Экономика</b>\n\n"
            "<b>акция ап [сумма]</b> — ставка на рост рынка\n"
            "<b>акция давн [сумма]</b> — ставка на падение\n"
            "<b>акция нейтрал [сумма]</b> — ставка на флэт\n"
            f"  Мин. ставка: {STOCK_MIN_BET} монет\n\n"
            "<b>перевод @username 500</b> — перевести монеты\n"
            "<b>перевод 500</b> — перевод ответом на сообщение\n\n"
            "<b>репутация</b> — посмотреть репутацию и скидки\n"
            "<b>баланс</b> — быстро посмотреть монеты и осколки"
        ),
    },
    "property": {
        "label": "🏠 Недвижимость и доход",
        "text": (
            "🏠 <b>Недвижимость и пассивный доход</b>\n\n"
            "<b>недвижимость</b> или /properties — купить бизнес и собрать доход\n"
            "  Каждый объект приносит монеты в час, копится макс. "
            f"{PASSIVE_INCOME_CAP_HOURS}ч\n\n"
            "🎁 <b>Ежедневный бонус</b>\n\n"
            "<b>ежедневный</b> / <b>бонус</b> / /daily — забрать награду\n"
            "  Растёт со стриком захода каждый день (сгорает при пропуске 20ч)\n\n"
            "🔗 <b>Рефералы</b>\n\n"
            "<b>реферал</b> / <b>пригласить</b> / /ref — своя пригласительная ссылка\n"
            f"  Тебе: +{REFERRAL_BONUS_COINS_REFERRER} монет, +{REFERRAL_BONUS_EXP_REFERRER} XP за друга\n"
            f"  Другу: +{REFERRAL_BONUS_COINS_NEWBIE} монет, +{REFERRAL_BONUS_EXP_NEWBIE} XP"
        ),
    },
    "rebirth": {
        "label": "🔄 Перерождение и Вознесение",
        "text": (
            "🔄 <b>Перерождение</b>\n\n"
            "<b>переродиться</b> / <b>перерождение</b> / /rebirth — переродиться "
            f"после {REBIRTH_MIN_LEVEL} уровня\n"
            "  Сбрасывает уровень, баланс, характеристики, навыки, снаряжение и "
            "профессию, но даёт постоянный бонус к монетам/опыту и открывает "
            "новые ветки профессий. Питомцы, титулы и достижения сохраняются!\n\n"
            "🌌 <b>Вознесение</b>\n\n"
            "<b>вознесение</b> / <b>алтарь</b> — магазин перманентных улучшений "
            "за 🌌 кристаллы (не сбрасывается перерождением)\n"
            "<b>гача вознесения</b> / /asc_gacha — крутка артефактов за кристаллы\n\n"
            "🚗 <b>Транспорт (40+ ур.)</b>\n\n"
            "<b>транспорт</b> / <b>авто</b> / <b>гараж</b> / /vehicles — "
            "купить транспорт и собирать пассивный опыт"
        ),
    },
    "bosses": {
        "label": "👹 Боссы и трофеи",
        "text": (
            "👹 <b>Боссы</b>\n\n"
            "<b>боссы</b> или /bosses — список боссов и их статус\n"
            "  Побеждай, чтобы получить 🔶 осколки и предметы\n\n"
            "🎒 <b>Трофеи</b>\n\n"
            "<b>рюкзак</b> / <b>трофеи</b> или /inventory — твои предметы с боссов\n"
            "  Экипируй один предмет — он даёт пассивный бонус к монетам/опыту/удаче\n"
            "  Улучшай предметы за 🔶 осколки"
        ),
    },
    "clans": {
        "label": "🏛 Факультеты и мировые боссы",
        "text": (
            "🏛 <b>Факультеты (кланы)</b>\n\n"
            "<b>факультет</b> / <b>факультеты</b> / <b>клан</b> / /faculty — "
            "выбрать факультет и посмотреть свой бонус\n"
            "  Каждый факультет даёт постоянный %-бонус (монеты/опыт/удача), "
            "растущий вместе с очками всех его участников\n"
            "  Очки начисляются за работу, добычу ресурсов и победы над боссами\n"
            f"  Смена факультета стоит <b>3000</b> монет\n"
            "  🏆 Топ факультетов — кнопка в меню факультета\n\n"
            "🌍 <b>Мировые боссы</b>\n\n"
            "<b>мировой босс</b> / <b>мб</b> / /world_boss — посмотреть статус "
            "и атаковать текущего мирового босса\n"
            "  Общий на все чаты противник с огромным HP — сражайтесь все вместе!\n"
            "  Награда каждому пропорциональна нанесённому урону, "
            "а лучший по урону получает дополнительный бонус\n"
            "  Появляется автоматически или вручную от администрации"
        ),
    },
    "gathering": {
        "label": "🌲 Промыслы (охота/рыбалка/шахта)",
        "text": (
            "🌲 <b>Промыслы</b>\n\n"
            "<b>охота [xN]</b> — сходить на охоту 🏹 (можно сразу x5 / x20)\n"
            "<b>рыбалка [xN]</b> — сходить на рыбалку 🎣\n"
            "<b>шахта [xN]</b> — сходить в шахту ⛏\n\n"
            "<b>навыки сбора</b> / /gskills — прокачать Охотничье мастерство, "
            "Рыболовное мастерство, Горное дело\n"
            "<b>мастерство</b> / /mastery — ранги мастерства и постоянные бонусы\n\n"
            "<b>зона охота</b> / <b>зона рыбалка</b> / <b>зона шахта</b> — выбрать "
            "зону добычи (новые открываются с ростом навыка)\n\n"
            "<b>ресурсы</b> — посмотреть добытые ресурсы\n"
            "<b>продать</b> — продать ресурсы по одному\n"
            "<b>продать всё</b> — продать все ресурсы разом\n"
            "<b>коллекция</b> / <b>альбом</b> — какие ресурсы ты уже находил\n\n"
            "<b>мастерская</b> / <b>крафт</b> / <b>инструменты</b> — скрафтить и "
            "улучшить инструменты (кирка/удочка/оружие, 9 тиров каждый)\n\n"
            "<b>лок боссы</b> / /loc_bosses — боссы локаций (Секач, Чудище озера, "
            "Голем штольни и др.)\n"
            "<b>трофеи локаций</b> — трофеи с боссов локаций, улучшение за 🔶 осколки\n\n"
            "<i>Инструменты, трофеи локаций и ранги мастерства увеличивают "
            "количество и редкость добычи!</i>"
        ),
    },
    "relationships": {
        "label": "💞 Отношения и семья",
        "text": (
            "💞 <b>Отношения</b> (в группах)\n\n"
            "<b>обнять @username</b> — поднять уровень отношений\n"
            "<b>подарок @username</b> — подарить подарок за монеты\n"
            "<b>отношения</b> — свой список отношений\n"
            "<b>отношения @username</b> — отношения с конкретным человеком\n\n"
            "💍 <b>Брак</b>\n\n"
            "<b>брак @username</b> — сделать предложение\n"
            "<b>развод</b> / /divorce — расторгнуть брак\n"
            "<b>семья</b> / <b>супруг</b> / /family — инфо о браке и бонусах"
        ),
    },
    "games": {
        "label": "🎮 Игры и дуэли",
        "text": (
            "🎮 <b>Игры</b>\n\n"
            "<b>дуэль @username 500</b> — дуэль на монеты\n"
            "<b>кости @username 500</b> — бросок кубиков\n"
            "<b>слоты [сумма]</b> — слоты (мин. 50 монет)\n"
            "<b>блекджек [сумма]</b> — блекджек (мин. 50 монет)\n"
            "  🍒🍒🍒 x3 | ⭐⭐⭐ x5 | 💎💎💎 x10 | 7️⃣7️⃣7️⃣ x20\n\n"
            "<b>акция ап/давн/нейтрал [сумма]</b> — биржа\n\n"
            "📈 Покер:\n"
            "<b>покер создать</b> / <b>покер старт</b>\n"
            "<b>чек</b> / <b>колл</b> / <b>рейз [сумма]</b> / <b>фолд</b> / <b>ва-банк</b>"
        ),
    },
    "bunker": {
        "label": "🏗 Бункер",
        "text": (
            "🏗 <b>Бункер</b>\n\n"
            "<b>бункер создать</b> — создать игру\n"
            "<b>бункер создать манас</b> — режим КТУ\n"
            "<b>бункер создать обычный</b> — апокалипсис\n"
            "<b>+</b> — войти в игру\n"
            "<b>бункер старт</b> — начать (создатель)\n"
            "<b>открыть [характеристика]</b> — раскрыть черту\n"
            "<b>бункер голосование</b> — запустить голосование\n"
            "<b>кик @username</b> — голосовать против игрока\n"
            "<b>бункер итог</b> — подвести итоги\n"
            "<b>бункер статус</b> — состояние игры\n"
            "<b>бункер отмена</b> — отменить игру"
        ),
    },
    "pets": {
        "label": "🐾 Питомцы и квесты",
        "text": (
            "🐾 <b>Питомцы</b>\n\n"
            "<b>гача</b> или /gacha — открыть меню гачи\n"
            "  Обычная: 2000 монет\n"
            "  Премиум: 5000 монет (выше шанс редких)\n"
            "  Дубликат = бонус питомца +1% (макс +20%)\n"
            "  Питомцы хранятся в коллекции!\n\n"
            "📋 <b>Квесты</b>\n\n"
            "<b>квесты</b> или /quests — ежедневные задания\n"
            "  Обновляются каждый день, дают монеты и XP\n\n"
            "🏅 <b>Достижения</b>\n\n"
            "/achievements или <b>достижения</b> — список ачивок\n\n"
            "🎉 <b>Ивенты</b>\n\n"
            "<b>ивент</b> — посмотреть активный ивент"
        ),
    },
    "rating": {
        "label": "🏆 Рейтинги",
        "text": (
            "🏆 <b>Рейтинги</b>\n\n"
            "/top — топ-10 богачей\n"
            "/my_place — твоё место в рейтинге по балансу\n"
            "<b>топ уровней</b> / /top_level — топ по уровню\n"
            "<b>топ репутации</b> / /top_rep — топ по репутации\n"
            "<b>топ рефералов</b> / /top_ref — топ по рефералам\n"
            "<b>топ отношений</b> / /top_relationships — топ-10 пар по XP отношений\n"
            "<b>список браков</b> / /marriages — все пары в браке"
        ),
    },
}

@dp.message(F.text.func(lambda t: _is(t, "команда", "команды", "помощь", "help")))
async def txt_help_any(message: Message):
    await _send_help_main(message)

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await _send_help_main(message)

async def _send_help_main(message: Message):
    builder = InlineKeyboardBuilder()
    for key, cat in HELP_CATEGORIES.items():
        if key == "main":
            continue
        builder.button(text=cat["label"], callback_data=f"help_cat:{key}")
    builder.adjust(1)
    await message.answer(HELP_CATEGORIES["main"]["text"], reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("help_cat:"))
async def callback_help_cat(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    cat = HELP_CATEGORIES.get(key)
    if not cat:
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ Назад", callback_data="help_back")
    await callback.answer()
    await callback.message.edit_text(cat["text"], reply_markup=builder.as_markup())

@dp.callback_query(F.data == "help_back")
async def callback_help_back(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    for key, cat in HELP_CATEGORIES.items():
        if key == "main":
            continue
        builder.button(text=cat["label"], callback_data=f"help_cat:{key}")
    builder.adjust(1)
    await callback.answer()
    await callback.message.edit_text(HELP_CATEGORIES["main"]["text"], reply_markup=builder.as_markup())

# =====================================================================
# МОДУЛЬ «ТЕХАССКИЙ ПОКЕР»
# =====================================================================
POKER_SMALL_BLIND  = 10
POKER_BIG_BLIND    = 20
POKER_MAX_PLAYERS  = 6
POKER_MIN_PLAYERS  = 2
POKER_REG_SECONDS  = 120
POKER_TURN_SECONDS = 60

RANKS = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
SUITS = ['♥️','♦️','♣️','♠️']
RANK_VALUE = {r: i for i, r in enumerate(RANKS, 2)}
HAND_NAMES = [
    'Старшая карта', 'Пара', 'Две пары', 'Тройка',
    'Стрит', 'Флеш', 'Фулл-хаус', 'Каре',
    'Стрит-флеш', 'Роял-флеш'
]

poker_games: dict[int, "PokerGame"] = {}


def _new_deck() -> list[str]:
    deck = [f"{r}{s}" for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def _card_rank(card: str) -> int:
    for r in sorted(RANK_VALUE, key=lambda x: -len(x)):
        if card.startswith(r):
            return RANK_VALUE[r]
    return 0


def _card_suit(card: str) -> str:
    for s in SUITS:
        if card.endswith(s):
            return s
    return ''


def _hand_rank_5(cards: list[str]) -> tuple:
    ranks  = sorted([_card_rank(c) for c in cards], reverse=True)
    suits  = [_card_suit(c) for c in cards]
    is_flush    = len(set(suits)) == 1
    is_straight = (ranks == list(range(ranks[0], ranks[0] - 5, -1))) or \
                  (sorted(ranks) == [2, 3, 4, 5, 14])

    if is_straight and sorted(ranks) == [2, 3, 4, 5, 14]:
        ranks = [5, 4, 3, 2, 1]

    from collections import Counter
    cnt    = Counter(ranks)
    groups = sorted(cnt.values(), reverse=True)
    vals   = sorted(cnt.keys(), key=lambda x: (cnt[x], x), reverse=True)

    if is_flush and is_straight:
        return (9, ranks) if ranks[0] == 14 else (8, ranks)
    if groups[0] == 4:
        return (7, vals)
    if groups[:2] == [3, 2]:
        return (6, vals)
    if is_flush:
        return (5, ranks)
    if is_straight:
        return (4, ranks)
    if groups[0] == 3:
        return (3, vals)
    if groups[:2] == [2, 2]:
        return (2, vals)
    if groups[0] == 2:
        return (1, vals)
    return (0, ranks)


def _best_hand(cards: list[str]) -> tuple:
    best = None
    best_combo = []
    for combo in combinations(cards, 5):
        rank = _hand_rank_5(list(combo))
        if best is None or rank > best:
            best = rank
            best_combo = list(combo)
    return best, best_combo


class PokerGame:
    def __init__(self, chat_id: int, creator_id: int, creator_name: str):
        self.chat_id      = chat_id
        self.creator_id   = creator_id
        self.creator_name = creator_name
        self.players: dict[int, dict] = {}
        self.order:   list[int] = []
        self.phase = "registration"
        self.deck:        list[str] = []
        self.community:   list[str] = []
        self.pot:         int       = 0
        self.current_bet: int       = 0
        self.dealer_idx:  int       = 0
        self.current_idx: int       = 0
        self.round_done:  set[int]  = set()
        self.reg_deadline = int(time.time()) + POKER_REG_SECONDS
        self.turn_task: asyncio.Task | None = None

    def active_players(self) -> list[int]:
        return [uid for uid in self.order if not self.players[uid]["folded"]]

    def players_who_can_act(self) -> list[int]:
        return [uid for uid in self.active_players() if not self.players[uid]["allin"]]

    def table_text(self) -> str:
        community_str = " ".join(self.community) if self.community else "—"
        lines = [
            f"🃏 <b>Карты на столе:</b> {community_str}",
            f"💰 <b>Банк (Pot):</b> {self.pot} монет",
            f"💵 <b>Текущая ставка:</b> {self.current_bet}",
            "",
            "<b>👤 Статус игроков:</b>",
        ]
        dealer_id = self.order[self.dealer_idx] if self.order else None
        for uid in self.order:
            p = self.players[uid]
            if p["folded"]:
                status = "❌ Фолд"
            elif p["allin"]:
                status = f"💥 Ва-банк (ставка {p['total_bet']})"
            else:
                status = f"Ставка {p['total_bet']}, баланс {p['balance']}"
            dealer_mark = " 🎴Дилер" if uid == dealer_id else ""
            lines.append(f"  • {p['name']}{dealer_mark} — {status}")
        return "\n".join(lines)

    def start_game(self):
        uids = list(self.players.keys())
        random.shuffle(uids)
        self.order = uids
        self.deck  = _new_deck()

        for uid in self.order:
            self.players[uid]["hole"] = [self.deck.pop(), self.deck.pop()]
            self.players[uid]["bet"]       = 0
            self.players[uid]["total_bet"] = 0
            self.players[uid]["folded"]    = False
            self.players[uid]["allin"]     = False

        n = len(self.order)
        self.dealer_idx = 0
        sb_idx = 1 % n
        bb_idx = 2 % n

        self._post_blind(self.order[sb_idx], POKER_SMALL_BLIND)
        self._post_blind(self.order[bb_idx], POKER_BIG_BLIND)
        self.current_bet = POKER_BIG_BLIND
        self.current_idx = (bb_idx + 1) % n
        if n == 2:
            self.current_idx = sb_idx

        self.round_done = set()
        self.phase = "preflop"

    def _post_blind(self, uid: int, amount: int):
        p = self.players[uid]
        actual = min(amount, p["balance"])
        p["balance"]   -= actual
        p["bet"]        = actual
        p["total_bet"] += actual
        self.pot       += actual
        if p["balance"] == 0:
            p["allin"] = True
        update_user(uid, balance=p["balance"])

    def action_fold(self, uid: int) -> str:
        self.players[uid]["folded"] = True
        self.round_done.add(uid)
        return f"❌ {self.players[uid]['name']} сбросил карты (Фолд)."

    def action_check(self, uid: int) -> tuple[bool, str]:
        p = self.players[uid]
        if p["bet"] < self.current_bet:
            return False, (
                f"❌ Нельзя чек — текущая ставка {self.current_bet}, "
                f"твоя ставка {p['bet']}. Нужно Колл или Рейз."
            )
        self.round_done.add(uid)
        return True, f"✅ {p['name']} — Чек."

    def action_call(self, uid: int) -> str:
        p    = self.players[uid]
        need = self.current_bet - p["bet"]
        actual = min(need, p["balance"])
        p["balance"]   -= actual
        p["bet"]       += actual
        p["total_bet"] += actual
        self.pot       += actual
        if p["balance"] == 0:
            p["allin"] = True
        update_user(uid, balance=p["balance"])
        self.round_done.add(uid)
        return f"✅ {p['name']} — Колл ({actual} монет). Баланс: {p['balance']}"

    def action_raise(self, uid: int, amount: int) -> tuple[bool, str]:
        p = self.players[uid]
        total_raise = self.current_bet + amount
        need = total_raise - p["bet"]
        if need <= 0:
            return False, "❌ Некорректная сумма рейза."
        if need > p["balance"]:
            return False, f"❌ Недостаточно монет. Нужно {need}, есть {p['balance']}."
        p["balance"]   -= need
        p["bet"]       += need
        p["total_bet"] += need
        self.pot       += need
        self.current_bet = p["bet"]
        if p["balance"] == 0:
            p["allin"] = True
        update_user(uid, balance=p["balance"])
        self.round_done = {uid}
        return True, f"📈 {p['name']} — Рейз до {self.current_bet}! Баланс: {p['balance']}"

    def action_allin(self, uid: int) -> str:
        p = self.players[uid]
        amount = p["balance"]
        if p["bet"] + amount > self.current_bet:
            self.current_bet = p["bet"] + amount
            self.round_done = {uid}
        p["total_bet"] += amount
        p["bet"]       += amount
        p["balance"]    = 0
        p["allin"]      = True
        self.pot       += amount
        update_user(uid, balance=0)
        self.round_done.add(uid)
        return f"💥 {p['name']} — ВА-БАНК! (+{amount} монет в банк)"

    def is_round_over(self) -> bool:
        can_act = self.players_who_can_act()
        if not can_act:
            return True
        for uid in can_act:
            if uid not in self.round_done:
                return False
            if self.players[uid]["bet"] < self.current_bet:
                return False
        return True

    def advance_phase(self) -> str:
        transitions = {
            "preflop": "flop",
            "flop":    "turn",
            "turn":    "river",
            "river":   "showdown",
        }
        self.phase = transitions.get(self.phase, "showdown")

        for uid in self.order:
            self.players[uid]["bet"] = 0
        self.current_bet = 0
        self.round_done  = set()

        if self.phase == "flop":
            self.community = [self.deck.pop(), self.deck.pop(), self.deck.pop()]
        elif self.phase in ("turn", "river"):
            self.community.append(self.deck.pop())

        n = len(self.order)
        idx = (self.dealer_idx + 1) % n
        for _ in range(n):
            uid = self.order[idx]
            if not self.players[uid]["folded"] and not self.players[uid]["allin"]:
                self.current_idx = idx
                break
            idx = (idx + 1) % n
        else:
            self.current_idx = idx

        return self.phase

    def showdown(self) -> list[tuple]:
        alive = self.active_players()
        results = []
        for uid in alive:
            all_cards = self.players[uid]["hole"] + self.community
            rank, best5 = _best_hand(all_cards)
            hand_name   = HAND_NAMES[rank[0]]
            cards_str   = " ".join(self.players[uid]["hole"])
            results.append((uid, hand_name, cards_str, rank, best5))
        results.sort(key=lambda x: x[3], reverse=True)
        return results

    def distribute_pot(self) -> dict[int, int]:
        alive    = self.active_players()
        winnings: dict[int, int] = {uid: 0 for uid in self.order}
        if len(alive) == 1:
            winnings[alive[0]] = self.pot
            return winnings
        results   = self.showdown()
        best_rank = results[0][3]
        winners   = [r for r in results if r[3] == best_rank]
        share     = self.pot // len(winners)
        for w in winners:
            winnings[w[0]] = share
        winnings[winners[0][0]] += self.pot - share * len(winners)
        return winnings


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() == "покер создать")
)
async def poker_create(message: Message):
    chat_id = message.chat.id
    if chat_id in poker_games and poker_games[chat_id].phase != "showdown":
        await message.answer("⚠️ В этом чате уже идёт покер!")
        return

    uid  = message.from_user.id
    name = message.from_user.full_name
    game = PokerGame(chat_id, uid, name)
    user_data = get_user_safe(uid)
    game.players[uid] = {
        "name": name, "hole": [], "balance": user_data["balance"],
        "bet": 0, "total_bet": 0, "folded": False, "allin": False
    }
    poker_games[chat_id] = game

    await message.answer(
        f"🃏 <b>Техасский Покер!</b>\n\n"
        f"👤 Создал: <b>{name}</b>\n"
        f"⏳ Регистрация открыта <b>2 минуты</b>. Пиши <b>+</b> чтобы войти!\n"
        f"Мест: 1/{POKER_MAX_PLAYERS}\n\n"
        f"Когда все готовы — <code>покер старт</code>\n"
        f"Блайнды: малый {POKER_SMALL_BLIND} / большой {POKER_BIG_BLIND} монет"
    )

    async def auto_start():
        await asyncio.sleep(POKER_REG_SECONDS)
        g = poker_games.get(chat_id)
        if g and g.phase == "registration" and len(g.players) >= POKER_MIN_PLAYERS:
            await _poker_begin(message, g)
        elif g and g.phase == "registration":
            del poker_games[chat_id]
            await message.answer("⏰ Время регистрации вышло. Недостаточно игроков.")

    asyncio.create_task(auto_start())


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text == "+"
)
async def poker_or_bunker_join(message: Message):
    chat_id = message.chat.id
    uid  = message.from_user.id
    name = message.from_user.full_name

    game = poker_games.get(chat_id)
    if game and game.phase == "registration":
        if uid in game.players:
            await message.answer(f"🟢 {name}, ты уже за столом!")
            return
        if len(game.players) >= POKER_MAX_PLAYERS:
            await message.answer("❌ Стол заполнен (максимум 6 игроков).")
            return
        user_data = get_user_safe(uid)
        if not user_data:
            await message.answer("❌ Зарегистрируйся через /start")
            return
        if user_data["balance"] < POKER_BIG_BLIND:
            await message.answer(
                f"❌ {name}, недостаточно монет для игры. "
                f"Нужно минимум {POKER_BIG_BLIND}."
            )
            return
        game.players[uid] = {
            "name": name, "hole": [], "balance": user_data["balance"],
            "bet": 0, "total_bet": 0, "folded": False, "allin": False
        }
        await message.answer(
            f"✅ <b>{name}</b> сел за стол! "
            f"Игроков: {len(game.players)}/{POKER_MAX_PLAYERS}\n"
            f"Баланс в игре: {user_data['balance']} монет"
        )
        return

    b_game = _bunker_active(chat_id)
    if b_game and b_game.phase == "registration":
        if uid in b_game.players:
            await message.answer(f"🟢 {name}, ты уже в бункере!")
            return
        b_game.players[uid] = {"name": name, "card": {}}
        await message.answer(
            f"✅ <b>{name}</b> вошёл в бункер! "
            f"Всего игроков: <b>{len(b_game.players)}</b>"
        )


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("покер старт", "покер start"))
)
async def poker_start_cmd(message: Message):
    chat_id = message.chat.id
    game    = poker_games.get(chat_id)

    if not game or game.phase != "registration":
        await message.answer("❌ Нет активной регистрации. Начни с <code>покер создать</code>.")
        return
    if message.from_user.id != game.creator_id:
        await message.answer("❌ Только создатель может запустить игру.")
        return
    if len(game.players) < POKER_MIN_PLAYERS:
        await message.answer(f"❌ Нужно минимум {POKER_MIN_PLAYERS} игрока!")
        return

    await _poker_begin(message, game)


async def _poker_begin(message: Message, game: PokerGame):
    chat_id = game.chat_id
    game.start_game()

    failed = []
    for uid, p in game.players.items():
        try:
            await bot.send_message(
                uid,
                f"🃏 <b>Твои карманные карты:</b>\n\n"
                f"<b>{p['hole'][0]}  {p['hole'][1]}</b>\n\n"
                f"Удачи за столом! 🤞"
            )
        except Exception:
            failed.append(p["name"])

    players_list = "\n".join(
        f"  • {p['name']} (баланс: {p['balance']})"
        for p in game.players.values()
    )
    dealer_name = game.players[game.order[game.dealer_idx]]["name"]
    n = len(game.order)
    sb_name = game.players[game.order[1 % n]]["name"]
    bb_name = game.players[game.order[2 % n]]["name"] if n > 2 else sb_name

    msg = (
        f"🃏 <b>ПОКЕР НАЧАЛСЯ!</b>\n\n"
        f"<b>Игроки:</b>\n{players_list}\n\n"
        f"🎴 Дилер: <b>{dealer_name}</b>\n"
        f"💰 Малый блайнд ({POKER_SMALL_BLIND}): <b>{sb_name}</b>\n"
        f"💰 Большой блайнд ({POKER_BIG_BLIND}): <b>{bb_name}</b>\n\n"
        f"📬 Карманные карты отправлены в личные сообщения!"
    )
    if failed:
        msg += f"\n\n⚠️ Не удалось доставить карты: {', '.join(failed)}"

    await message.answer(msg)
    await message.answer(game.table_text())
    await _poker_next_turn(message, game)


async def _poker_next_turn(message: Message, game: PokerGame):
    chat_id = game.chat_id
    alive = game.active_players()
    if len(alive) == 1:
        await _poker_end_single(message, game, alive[0])
        return

    if game.is_round_over():
        if game.phase == "river":
            await _poker_showdown(message, game)
            return
        new_phase = game.advance_phase()
        phase_labels = {
            "flop":     "🌅 ФЛОП",
            "turn":     "🌄 ТЕРН",
            "river":    "🌃 РИВЕР",
            "showdown": "🏆 ВСКРЫТИЕ",
        }
        await message.answer(
            f"\n{phase_labels.get(new_phase, new_phase)}\n\n" + game.table_text()
        )
        if not game.players_who_can_act():
            if new_phase == "showdown":
                await _poker_showdown(message, game)
            else:
                while game.phase != "showdown" and not game.players_who_can_act():
                    np = game.advance_phase()
                    if np == "showdown":
                        break
                    await message.answer(
                        f"{phase_labels.get(np, np)}\n\n" + game.table_text()
                    )
                await _poker_showdown(message, game)
            return

    current_uid = None
    n = len(game.order)
    for i in range(n):
        idx = game.current_idx % n
        uid = game.order[idx]
        p   = game.players[uid]
        if not p["folded"] and not p["allin"]:
            current_uid = uid
            game.current_idx = idx
            break
        game.current_idx = (game.current_idx + 1) % n

    if current_uid is None:
        if game.phase == "river":
            await _poker_showdown(message, game)
        else:
            while game.phase not in ("showdown", "river"):
                new_p = game.advance_phase()
                if new_p == "showdown" or not game.players_who_can_act():
                    await _poker_showdown(message, game)
                    return
            await _poker_showdown(message, game)
        return

    p    = game.players[current_uid]
    need = game.current_bet - p["bet"]

    actions = []
    if need == 0:
        actions.append("<code>чек</code>")
    else:
        actions.append(f"<code>колл</code> ({need} монет)")
    actions.append("<code>рейз [сумма]</code>")
    actions.append("<code>ва-банк</code>")
    actions.append("<code>фолд</code>")

    mention = f"<a href='tg://user?id={current_uid}'>{p['name']}</a>"

    await message.answer(
        f"⏳ Ход игрока: {mention}\n"
        f"💰 Банк: {game.pot} | Ставка: {game.current_bet} | "
        f"Твоя ставка: {p['bet']} | Баланс: {p['balance']}\n\n"
        f"Доступные действия: {' / '.join(actions)}\n"
        f"<i>У тебя {POKER_TURN_SECONDS} секунд</i>"
    )

    if game.turn_task:
        game.turn_task.cancel()

    async def auto_fold_task():
        await asyncio.sleep(POKER_TURN_SECONDS)
        g = poker_games.get(chat_id)
        if not g or g.phase == "showdown":
            return
        if game.current_idx < len(g.order):
            uid_check = g.order[g.current_idx % len(g.order)]
            if uid_check == current_uid and not g.players[current_uid]["folded"]:
                text = g.action_fold(current_uid)
                g.current_idx = (g.current_idx + 1) % len(g.order)
                await message.answer(f"⏰ Время вышло! {text}")
                await _poker_next_turn(message, g)

    game.turn_task = asyncio.create_task(auto_fold_task())


async def _poker_end_single(message: Message, game: PokerGame, winner_id: int):
    winner = game.players[winner_id]
    new_bal = winner["balance"] + game.pot
    bump_stat(winner_id, "stat_poker_wins")
    update_user(winner_id, balance=new_bal)
    ach_msg = grant_achievement_now(winner_id, "poker_win")

    text = (
        f"🏆 Все остальные сбросили карты!\n\n"
        f"🥇 Победитель: <b>{winner['name']}</b>\n"
        f"💰 Выигрыш: <b>{game.pot}</b> монет\n"
        f"💳 Новый баланс: <b>{new_bal}</b> монет"
    )
    if ach_msg:
        text += f"\n\n{ach_msg}"
    await message.answer(text)
    if game.chat_id in poker_games:
        del poker_games[game.chat_id]


async def _poker_showdown(message: Message, game: PokerGame):
    results  = game.showdown()
    winnings = game.distribute_pot()

    lines = ["🏆 <b>ВСКРЫТИЕ!</b>\n"]
    for uid, hand_name, cards_str, rank, best5 in results:
        lines.append(
            f"👤 <b>{game.players[uid]['name']}</b>\n"
            f"   🃏 Карты: {cards_str}\n"
            f"   🥇 Комбинация: <b>{hand_name}</b>"
        )

    lines.append(f"\n🃏 <b>Общие карты:</b> {' '.join(game.community)}\n")

    winners_text = []
    for uid, prize in winnings.items():
        if prize > 0:
            new_bal = game.players[uid]["balance"] + prize
            update_user(uid, balance=new_bal)
            bump_stat(uid, "stat_poker_wins")
            ach_msg = grant_achievement_now(uid, "poker_win")
            line = (
                f"🥇 <b>{game.players[uid]['name']}</b> "
                f"выигрывает <b>{prize}</b> монет! "
                f"(баланс: {new_bal})"
            )
            if ach_msg:
                line += f"\n{ach_msg}"
            winners_text.append(line)

    lines.append("\n".join(winners_text))
    await message.answer("\n".join(lines))

    if game.chat_id in poker_games:
        del poker_games[game.chat_id]


def _get_poker_game_and_player(chat_id: int, uid: int):
    game = poker_games.get(chat_id)
    if not game or game.phase in ("registration", "showdown"):
        return None, None
    if uid not in game.players:
        return None, None
    if game.order[game.current_idx % len(game.order)] != uid:
        return None, None
    p = game.players[uid]
    if p["folded"] or p["allin"]:
        return None, None
    return game, p


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() == "чек")
)
async def poker_check(message: Message):
    game, p = _get_poker_game_and_player(message.chat.id, message.from_user.id)
    if not game:
        return
    ok, text = game.action_check(message.from_user.id)
    await message.answer(text)
    if ok:
        if game.turn_task:
            game.turn_task.cancel()
        game.current_idx = (game.current_idx + 1) % len(game.order)
        await _poker_next_turn(message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() == "колл")
)
async def poker_call(message: Message):
    game, p = _get_poker_game_and_player(message.chat.id, message.from_user.id)
    if not game:
        return
    if game.turn_task:
        game.turn_task.cancel()
    text = game.action_call(message.from_user.id)
    await message.answer(text)
    game.current_idx = (game.current_idx + 1) % len(game.order)
    await _poker_next_turn(message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("рейз "))
)
async def poker_raise(message: Message):
    game, p = _get_poker_game_and_player(message.chat.id, message.from_user.id)
    if not game:
        return
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ Формат: <code>рейз 100</code>")
        return
    amount = int(parts[1])
    ok, text = game.action_raise(message.from_user.id, amount)
    await message.answer(text)
    if ok:
        if game.turn_task:
            game.turn_task.cancel()
        game.current_idx = (game.current_idx + 1) % len(game.order)
        await _poker_next_turn(message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() == "фолд")
)
async def poker_fold(message: Message):
    game, p = _get_poker_game_and_player(message.chat.id, message.from_user.id)
    if not game:
        return
    if game.turn_task:
        game.turn_task.cancel()
    text = game.action_fold(message.from_user.id)
    await message.answer(text)
    game.current_idx = (game.current_idx + 1) % len(game.order)
    await _poker_next_turn(message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() == "ва-банк")
)
async def poker_allin(message: Message):
    game, p = _get_poker_game_and_player(message.chat.id, message.from_user.id)
    if not game:
        return
    if game.turn_task:
        game.turn_task.cancel()
    text = game.action_allin(message.from_user.id)
    await message.answer(text)
    game.current_idx = (game.current_idx + 1) % len(game.order)
    await _poker_next_turn(message, game)


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("покер статус", "покер стол"))
)
async def poker_status(message: Message):
    game = poker_games.get(message.chat.id)
    if not game:
        await message.answer("Активной покер-игры нет.")
        return
    await message.answer(game.table_text())


@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower() in ("покер отмена", "покер стоп"))
)
async def poker_cancel(message: Message):
    chat_id = message.chat.id
    game    = poker_games.get(chat_id)
    if not game:
        await message.answer("Нет активной покер-игры.")
        return
    if message.from_user.id != game.creator_id:
        await message.answer("❌ Только создатель может отменить игру.")
        return
    if game.turn_task:
        game.turn_task.cancel()
    for uid, p in game.players.items():
        if p["total_bet"] > 0:
            refund = p["balance"] + p["total_bet"]
            update_user(uid, balance=refund)
    del poker_games[chat_id]
    await message.answer("🚫 Покер отменён. Ставки возвращены игрокам.")


@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "недвижимость", "бизнес")))
async def txt_properties_group(message: Message):
    await cmd_properties(message)

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "статистика")))
async def txt_stats_group(message: Message):
    await cmd_stats(message)

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "ежедневный", "бонус")))
async def txt_daily_group(message: Message):
    await cmd_daily(message)
# =====================================================================
# ПЕРЕВОД ДЕНЕГ
# =====================================================================
@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("перевод"))
)
async def transfer_money_group(message: Message):
    sender_id   = message.from_user.id
    sender_name = message.from_user.full_name
    sender      = get_user_safe(sender_id)
    mention_sender = f"<a href='tg://user?id={sender_id}'>{sender_name}</a>"

    parts = message.text.strip().split()

    target_id   = None
    target_name = None
    amount      = None

    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        if ru.id == sender_id:
            await message.answer("❌ Нельзя переводить самому себе.")
            return
        if ru.is_bot:
            await message.answer("❌ Нельзя переводить боту.")
            return
        target_id   = ru.id
        target_name = ru.full_name
        if len(parts) == 2 and parts[1].isdigit():
            amount = int(parts[1])

    elif message.entities:
        for ent in message.entities:
            if ent.type == "mention":
                uname = message.text[ent.offset:ent.offset + ent.length]
                try:
                    chat_member = await bot.get_chat_member(message.chat.id, uname)
                    ru = chat_member.user
                    if ru.id == sender_id:
                        await message.answer("❌ Нельзя переводить самому себе.")
                        return
                    if ru.is_bot:
                        await message.answer("❌ Нельзя переводить боту.")
                        return
                    target_id   = ru.id
                    target_name = ru.full_name
                except Exception:
                    await message.answer(
                        f"❌ Не удалось найти пользователя {uname}.\n"
                        "Попробуй ответить на его сообщение командой <code>перевод [сумма]</code>."
                    )
                    return
            elif ent.type == "text_mention" and ent.user:
                ru = ent.user
                if ru.id == sender_id:
                    await message.answer("❌ Нельзя переводить самому себе.")
                    return
                target_id   = ru.id
                target_name = ru.full_name

        for part in reversed(parts):
            if part.isdigit():
                amount = int(part)
                break

    if target_id is None:
        await message.answer(
            "❌ Не указан получатель.\n\n"
            "Форматы:\n"
            "• <code>перевод @username 500</code>\n"
            "• Ответь на сообщение и напиши <code>перевод 500</code>"
        )
        return

    if amount is None:
        await message.answer(
            "❌ Не указана сумма.\n\n"
            "Форматы:\n"
            "• <code>перевод @username 500</code>\n"
            "• Ответь на сообщение и напиши <code>перевод 500</code>"
        )
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля.")
        return

    if amount > sender["balance"]:
        await message.answer(
            f"❌ Недостаточно монет.\n"
            f"Хочешь перевести: <b>{amount}</b>\n"
            f"Твой баланс: <b>{sender['balance']}</b>"
        )
        return

    register_user(target_id)
    receiver = get_user(target_id)
    if not receiver:
        await message.answer("❌ Получатель не найден в базе игры. Пусть напишет /start боту.")
        return

    new_sender_balance   = sender["balance"]   - amount
    new_receiver_balance = receiver["balance"] + amount

    update_user(sender_id,  balance=new_sender_balance)
    update_user(target_id,  balance=new_receiver_balance)

    mention_receiver = f"<a href='tg://user?id={target_id}'>{target_name}</a>"

    await message.answer(
        f"💸 <b>Перевод выполнен!</b>\n\n"
        f"👤 От: {mention_sender}\n"
        f"👤 Кому: {mention_receiver}\n"
        f"💰 Сумма: <b>{amount}</b> монет\n\n"
        f"📊 Баланс {sender_name}: <b>{new_sender_balance}</b>\n"
        f"📊 Баланс {target_name}: <b>{new_receiver_balance}</b>"
    )


@dp.message(
    F.chat.type == "private",
    F.text.func(lambda t: t and t.strip().lower().startswith("перевод"))
)
async def transfer_money_private(message: Message):
    await message.answer(
        "ℹ️ Переводы работают только в групповых чатах.\n\n"
        "Форматы:\n"
        "• <code>перевод @username 500</code>\n"
        "• Ответь на сообщение игрока и напиши <code>перевод 500</code>"
    )


# =====================================================================
# ХЕНДЛЕРЫ — ЛИЧНЫЕ СООБЩЕНИЯ
# =====================================================================
from aiogram.filters import CommandStart, CommandObject

@dp.message(CommandStart(), F.chat.type == "private")
async def cmd_start_private(message: Message, command: CommandObject):
    user_id = message.from_user.id
    is_new_user = get_user(user_id) is None

    user = get_user_safe(user_id, message.from_user.username or message.from_user.full_name)

    referral_bonus_text = ""

    # Обрабатываем реферальную ссылку только для НОВЫХ пользователей
    if is_new_user and command.args and command.args.startswith("ref_"):
        raw_id = command.args[len("ref_"):]
        if raw_id.isdigit():
            referrer_id = int(raw_id)

            # Защита: нельзя самого себя пригласить
            if referrer_id != user_id:
                referrer = get_user(referrer_id)
                if referrer:
                    # Помечаем, кто пригласил
                    update_user(user_id, referred_by=referrer_id)

                    # Бонус новому игроку
                    updated_newbie = get_user(user_id)
                    update_user(
                        user_id,
                        balance=updated_newbie["balance"] + REFERRAL_BONUS_COINS_NEWBIE,
                        exp=updated_newbie["exp"] + REFERRAL_BONUS_EXP_NEWBIE,
                    )
                    referral_bonus_text = (
                        f"\n\n🎁 <b>Ты зашёл по приглашению!</b>\n"
                        f"💰 +{REFERRAL_BONUS_COINS_NEWBIE} монет\n"
                        f"✨ +{REFERRAL_BONUS_EXP_NEWBIE} XP"
                    )

                    # Бонус пригласившему
                    new_ref_balance = referrer["balance"] + REFERRAL_BONUS_COINS_REFERRER
                    new_ref_exp     = referrer["exp"]     + REFERRAL_BONUS_EXP_REFERRER
                    update_user(
                        referrer_id,
                        balance=new_ref_balance,
                        exp=new_ref_exp,
                        referral_count=referrer.get("referral_count", 0) + 1,
                        referral_earned=referrer.get("referral_earned", 0) + REFERRAL_BONUS_COINS_REFERRER,
                    )

                    updated_referrer = get_user(referrer_id)
                    if updated_referrer:
                        updated_referrer, level_msgs = auto_level_up(updated_referrer)
                        check_and_grant_achievements(updated_referrer)
                        level_block = "".join(level_msgs)
                    else:
                        level_block = ""

                    try:
                        newbie_name = message.from_user.full_name
                        await bot.send_message(
                            referrer_id,
                            f"🎉 <b>По твоей ссылке зарегистрировался новый игрок!</b>\n"
                            f"👤 {newbie_name}\n\n"
                            f"💰 +{REFERRAL_BONUS_COINS_REFERRER} монет\n"
                            f"✨ +{REFERRAL_BONUS_EXP_REFERRER} XP"
                            f"{level_block}"
                        )
                    except Exception:
                        pass  # реферер мог заблокировать бота — не критично

    await message.answer(
        f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
        f"Добро пожаловать в игру «МанасWorker»! Используй меню ниже."
        f"{referral_bonus_text}",
        reply_markup=get_main_menu()
    )


@dp.message(Command("ref"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in
                                  ("реферал", "рефералы", "пригласить", "invite", "ref")))
async def cmd_referral(message: Message):
    if message.chat.type != "private":
        await message.answer(
            "ℹ️ Реферальную ссылку можно получить в личных сообщениях с ботом.\n"
            "Напиши мне в личку команду <code>реферал</code>."
        )
        return

    user = get_user_safe(
        message.from_user.id,
        message.from_user.username or message.from_user.full_name
    )

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"

    count = user.get("referral_count", 0)
    earned = user.get("referral_earned", 0)

    await message.answer(
        f"🔗 <b>Реферальная система</b>\n\n"
        f"Приглашай друзей в игру и получай бонусы за каждого!\n\n"
        f"👥 Приглашено друзей: <b>{count}</b>\n"
        f"💰 Всего заработано: <b>{earned}</b> монет\n\n"
        f"🎁 <b>Награда тебе</b> за друга: +{REFERRAL_BONUS_COINS_REFERRER} монет, "
        f"+{REFERRAL_BONUS_EXP_REFERRER} XP\n"
        f"🎁 <b>Награда другу</b> при переходе: +{REFERRAL_BONUS_COINS_NEWBIE} монет, "
        f"+{REFERRAL_BONUS_EXP_NEWBIE} XP\n\n"
        f"📎 <b>Твоя персональная ссылка:</b>\n"
        f"<code>{link}</code>\n\n"
        f"<i>Просто перешли эту ссылку другу — бонусы придут автоматически, "
        f"как только он запустит бота.</i>"
    )

@dp.message(F.text == "👤 Профиль", F.chat.type == "private")
async def btn_profile_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_profile_text(user, message.from_user.mention_html()))

@dp.message(F.text == "💼 Профессии", F.chat.type == "private")
async def btn_jobs_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    kb   = get_jobs_keyboard(user)
    text = build_jobs_text(user)
    if kb:
        await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text)

@dp.message(F.text == "🛠 Работа", F.chat.type == "private")
async def btn_work_private(message: Message):
    try:
        user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
        _, text = do_work(user)
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Ошибка при работе. Попробуй ещё раз.\n<code>{e}</code>")

@dp.message(F.text == "🏋️ Тренировки", F.chat.type == "private")
async def btn_training_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_training_text(user), reply_markup=get_training_keyboard(user))

@dp.message(F.text == "🧠 Навыки", F.chat.type == "private")
async def btn_skills_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    text, kb = build_skills_text(user)
    await message.answer(text, reply_markup=kb)

@dp.message(F.text == "🏠 Недвижимость", F.chat.type == "private")
async def btn_properties_private(message: Message):
    await cmd_properties(message)

@dp.message(F.text == "📊 Статистика", F.chat.type == "private")
async def btn_stats_private(message: Message):
    await cmd_stats(message)

@dp.message(F.text == "🎁 Ежедневный", F.chat.type == "private")
async def btn_daily_private(message: Message):
    await cmd_daily(message)

@dp.message(F.text == "🛒 Магазин", F.chat.type == "private")
async def btn_shop_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_shop_text(user), reply_markup=get_shop_keyboard())


def _is(text: str, *variants: str) -> bool:
    if not text:
        return False
    return text.strip().lower() in {v.lower() for v in variants}
@dp.message(Command("properties"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("недвижимость", "бизнес", "доход")))
async def cmd_properties(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_properties_text(user), reply_markup=get_properties_keyboard(user))


@dp.callback_query(F.data == "income_collect")
async def callback_income_collect(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    success, text = do_collect_income(user)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_properties_text(updated), reply_markup=get_properties_keyboard(updated))


@dp.callback_query(F.data.startswith("property_buy:"))
async def callback_property_buy(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_buy_property(user, key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_properties_text(updated), reply_markup=get_properties_keyboard(updated))

@dp.message(Command("start"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_start_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    save_chat(message.chat.id)
    await message.answer(
        f"👋 {message.from_user.mention_html()}, добро пожаловать!\n"
        f"Пиши <b>Профиль</b>, <b>Работа</b>, <b>Профессии</b>, "
        f"<b>Тренировки</b>, <b>Навыки</b>, <b>Магазин</b>.",
        reply_markup=get_main_menu()
    )

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "профиль", "profile", "перс", "персонаж")))
async def txt_profile_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_profile_text(user, message.from_user.mention_html()))

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "профессии", "профессия", "jobs", "job")))
async def txt_jobs_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    kb   = get_jobs_keyboard(user)
    text = f"{message.from_user.mention_html()}\n{build_jobs_text(user)}"
    if kb:
        await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text)

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "работа", "работать", "work")))
async def txt_work_group(message: Message):
    try:
        user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
        _, text = do_work(user)
        full_text = f"{message.from_user.mention_html()}\n{text}"
        if len(full_text) > 4000:
            await message.answer(full_text[:4000])
            await message.answer(full_text[4000:])
        else:
            await message.answer(full_text)
    except Exception as e:
        await message.answer(f"❌ Ошибка. Попробуй ещё раз.\n<code>{e}</code>")

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "тренировки", "тренировка", "train")))
async def txt_train_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(
        f"{message.from_user.mention_html()}\n{build_training_text(user)}",
        reply_markup=get_training_keyboard(user)
    )

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "навыки", "навык", "skills")))
async def txt_skills_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    text, kb = build_skills_text(user)
    await message.answer(f"{message.from_user.mention_html()}\n{text}", reply_markup=kb)

@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and _is(t, "магазин", "shop")))
async def txt_shop_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(
        f"{message.from_user.mention_html()}\n{build_shop_text(user)}",
        reply_markup=get_shop_keyboard()
    )
@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda t: t and t.strip().lower().startswith("акция ")))
async def txt_stock_group(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    mention = message.from_user.mention_html()
    parts   = message.text.strip().split()
    if len(parts) != 3:
        await message.answer(
            f"{mention}\n❌ Неверный формат.\n"
            "Используй: <b>акция ап 300</b> / <b>акция давн 500</b> / <b>акция нейтрал 150</b>"
        )
        return
    outcome_input = parts[1].lower()
    try:
        bet = int(parts[2])
    except ValueError:
        await message.answer(f"{mention}\n❌ Сумма ставки должна быть числом.")
        return
    _, text = do_stock_bet(user, outcome_input, bet)
    await message.answer(f"{mention}\n{text}")

@dp.message(F.chat.type == "private",
            F.text.func(lambda t: t and t.strip().lower().startswith("акция ")))
async def txt_stock_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    parts = message.text.strip().split()
    if len(parts) != 3:
        await message.answer(
            "❌ Неверный формат.\n"
            "Используй: <b>акция ап 300</b> / <b>акция давн 500</b> / <b>акция нейтрал 150</b>"
        )
        return
    outcome_input = parts[1].lower()
    try:
        bet = int(parts[2])
    except ValueError:
        await message.answer("❌ Сумма ставки должна быть числом.")
        return
    _, text = do_stock_bet(user, outcome_input, bet)
    await message.answer(text)
# =====================================================================
# CALLBACKS
# =====================================================================
@dp.callback_query(JobCallback.filter())
async def callback_choose_job(callback: CallbackQuery, callback_data: JobCallback):
    user_id = callback.from_user.id
    user    = get_user_safe(user_id)
    job_key = callback_data.job_key
    job     = JOBS.get(job_key)

    if not job:
        await callback.answer("❌ Профессия не найдена.", show_alert=True)
        return
    if user["job"] != "Безработный":
        await callback.answer("⛔ Ты уже выбрал профессию!", show_alert=True)
        return
    if job_key not in get_available_starter_jobs(user):
        await callback.answer("❌ Эта профессия ещё не открыта.", show_alert=True)
        return

    update_user(user_id, job=job["name"])
    await callback.answer(f"✅ Выбрана: {job['name']}!", show_alert=True)
    await callback.message.edit_text(
        f"✅ {callback.from_user.mention_html()} начинает карьеру!\n\n"
        f"💼 <b>{job['name']}</b>\n"
        f"<i>{job['description']}</i>\n\n"
        f"📌 Это твой путь. Сменить его нельзя."
    )


@dp.callback_query(UpgradeJobCallback.filter())
async def callback_upgrade_job(callback: CallbackQuery, callback_data: UpgradeJobCallback):
    user     = get_user_safe(callback.from_user.id)
    next_key = callback_data.job_key
    next_job = JOBS.get(next_key)

    if not next_job:
        await callback.answer("❌ Профессия не найдена.", show_alert=True)
        return

    can, why = check_upgrade_conditions(user)
    if not can:
        await callback.answer(why[:200], show_alert=True)
        return

    current_job_key = get_job_key(user)
    if not current_job_key:
        await callback.answer("❌ Ошибка профессии.", show_alert=True)
        return
    current_job = JOBS[current_job_key]
    if current_job.get("evolves_to") != next_key:
        await callback.answer("❌ Этот грейд не следует из твоей профессии.", show_alert=True)
        return

    update_user(callback.from_user.id, job=next_job["name"], job_rank=1)
    await callback.answer(f"🌟 Грейд повышен! Теперь ты: {next_job['name']}", show_alert=True)
    updated = get_user(callback.from_user.id)
    await callback.message.edit_text(
        build_jobs_text(updated),
        reply_markup=get_jobs_keyboard(updated)
    )


@dp.callback_query(F.data.startswith("upgrade_skill:"))
async def callback_upgrade_skill(callback: CallbackQuery):
    skill_key = callback.data.split(":")[1]
    user      = get_user_safe(callback.from_user.id)
    success, text = do_upgrade_skill(user, skill_key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        new_text, new_kb = build_skills_text(updated)
        await callback.message.edit_text(new_text, reply_markup=new_kb)

@dp.callback_query(ShopCallback.filter())
async def callback_shop_buy(callback: CallbackQuery, callback_data: ShopCallback):
    user    = get_user_safe(callback.from_user.id)
    success, text = do_buy_item(user, callback_data.item_key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(
            build_shop_text(updated),
            reply_markup=get_shop_keyboard()
        )

@dp.callback_query(F.data == "shop_back")
async def callback_shop_back(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    await callback.answer()
    await callback.message.edit_text(build_shop_text(user), reply_markup=get_shop_keyboard())

@dp.callback_query(F.data == "shop_cat:gear")
async def callback_shop_gear(callback: CallbackQuery):
    user  = get_user_safe(callback.from_user.id)
    lines = ["🎒 <b>Снаряжение</b>\n"]
    for item in SHOP_ITEMS.values():
        owned = "✅ куплено" if user.get(item["flag"]) else f"{item['price']} монет"
        lines.append(f"{item['name']} — <b>{owned}</b>\n  <i>{item['description']}</i>")
    lines.append(f"\n💰 Баланс: <b>{user['balance']}</b> монет")
    await callback.answer()
    await callback.message.edit_text("\n".join(lines), reply_markup=get_shop_gear_keyboard())

@dp.callback_query(F.data == "shop_cat:food")
async def callback_shop_food(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    lines = ["🍔 <b>Еда и расходники</b>\n"]
    for item in CONSUMABLES.values():
        effects = []
        if item["hp"] > 0: effects.append(f"+{min(item['hp'],9999)} HP")
        if item["energy"] > 0: effects.append(f"+{min(item['energy'],9999)} ⚡")
        if item["hp"] >= 9999 and item["energy"] >= 9999: effects = ["полное восстановление"]
        lines.append(f"{item['name']} — <b>{item['price']} монет</b>  ({', '.join(effects)})\n  <i>{item['description']}</i>")
    lines.append(f"\n💰 Баланс: <b>{user['balance']}</b> монет")
    await callback.answer()
    await callback.message.edit_text(build_food_category_text(user), reply_markup=get_shop_food_keyboard())

@dp.callback_query(F.data.startswith("consume:"))
async def callback_use_consumable(callback: CallbackQuery):
    parts     = callback.data.split(":")
    item_key  = parts[1]
    quantity  = int(parts[2]) if len(parts) > 2 else 1
    user      = get_user_safe(callback.from_user.id)
    success, text = do_use_consumable(user, item_key, quantity)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(
            build_food_category_text(updated),
            reply_markup=get_shop_food_keyboard()
        )

@dp.callback_query(TrainCallback.filter())
async def callback_train(callback: CallbackQuery, callback_data: TrainCallback):
    user = get_user_safe(callback.from_user.id)
    success, text = do_train(user, callback_data.stat, callback_data.amount)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(
            build_training_text(updated),
            reply_markup=get_training_keyboard(updated)
        )
# =====================================================================
# ТОП ИГРОКОВ
# =====================================================================
@dp.message(Command("top"))
async def cmd_top(message: Message):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, username, balance
                FROM users
                ORDER BY balance DESC
                LIMIT 10
            """)
            rows = cur.fetchall()

    if not rows:
        await message.answer("Рейтинг пока пуст.")
        return

    medals = ["🥇","🥈","🥉"]
    lines  = ["💰 <b>Топ-10 богачей МанасWorker</b>\n"]
    for i, row in enumerate(rows, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        name  = row["username"] or f"#{row['user_id']}"
        lines.append(f"{medal} <b>{name}</b> — {row['balance']} монет")

    await message.answer("\n".join(lines))


@dp.message(Command("my_place"))
async def cmd_my_place(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) + 1 AS place
                FROM users
                WHERE balance > (SELECT balance FROM users WHERE user_id = %s)
            """, (uid,))
            row = cur.fetchone()

    place = row[0] if row else "?"
    await message.answer(
        f"📊 Твоё место в рейтинге по балансу: <b>#{place}</b>\n"
        f"💰 Баланс: <b>{user['balance']}</b> монет"
    )


# =====================================================================
# ДОСТИЖЕНИЯ
# =====================================================================
@dp.message(Command("achievements"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("достижения", "ачивки")))
async def cmd_achievements(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    # Проверяем и выдаём новые ачивки
    new_msgs = check_and_grant_achievements(user)
    for msg in new_msgs:
        await message.answer(msg)

    user  = get_user(uid)
    owned = get_user_achievements(user)

    lines = ["🏅 <b>Достижения</b>\n"]
    for key, ach in ACHIEVEMENTS.items():
        icon = "✅" if key in owned else "🔒"
        lines.append(
            f"{icon} <b>{ach['name']}</b>\n"
            f"   <i>{ach['description']}</i>\n"
            f"   🎁 {ach['reward_coins']} монет + {ach['reward_exp']} XP"
        )

    total   = len(ACHIEVEMENTS)
    unlocked = len(owned)
    lines.append(f"\n📊 Открыто: <b>{unlocked}/{total}</b>")

    await message.answer("\n".join(lines))


# =====================================================================
# АДМИН-КОМАНДЫ
# =====================================================================
def admin_only(func):
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Нет доступа.")
            return
        await func(message, *args, **kwargs)
    return wrapper

def _resolve_id_and_arg(message: Message, parts: list[str]) -> tuple[int | None, str | None]:
    """
    Поддерживает 2 формата:
      - ответом на сообщение:   /команда аргумент
      - без ответа:             /команда id аргумент
    Возвращает (target_id, arg) или (None, None).
    """
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        arg = " ".join(parts[1:]) if len(parts) >= 2 else None
        return target_id, arg
    else:
        if len(parts) >= 3 and parts[1].isdigit():
            return int(parts[1]), " ".join(parts[2:])
    return None, None

def _resolve_id_only(message: Message, parts: list[str]) -> int | None:
    """Возвращает target_id либо из reply, либо из parts[1]."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None

async def _resolve_target(message: Message, parts: list[str], need_amount: bool = True):
    """Определяет target_id и amount из команды или reply."""
    target_id = None
    amount    = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if need_amount and len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            amount = int(parts[1])
    else:
        if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            # /give_money 12345678 500
            if len(parts) >= 3 and parts[2].lstrip("-").isdigit():
                target_id = int(parts[1])
                amount    = int(parts[2])
            else:
                # только сумма без ID — ошибка
                pass

    return target_id, amount


@dp.message(Command("give_money"))
async def cmd_give_money(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    parts     = message.text.strip().split()
    target_id, amount = await _resolve_target(message, parts)

    if not target_id or amount is None:
        await message.answer(
            "❌ Формат:\n"
            "<code>/give_money 12345678 500</code>\n"
            "или ответом на сообщение:\n"
            "<code>/give_money 500</code>"
        )
        return

    register_user(target_id)
    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return

    new_balance = user["balance"] + amount
    update_user(target_id, balance=new_balance)
    await message.answer(
        f"✅ Начислено <b>{amount}</b> монет пользователю <code>{target_id}</code>\n"
        f"Новый баланс: <b>{new_balance}</b>"
    )


@dp.message(Command("give_exp"))
async def cmd_give_exp(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    parts     = message.text.strip().split()
    target_id, amount = await _resolve_target(message, parts)

    if not target_id or amount is None:
        await message.answer(
            "❌ Формат:\n"
            "<code>/give_exp 12345678 500</code>\n"
            "или ответом: <code>/give_exp 500</code>"
        )
        return

    register_user(target_id)
    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return

    new_exp = user["exp"] + amount
    update_user(target_id, exp=new_exp)
    user, level_msgs = auto_level_up({**user, "exp": new_exp})
    level_block = "\n".join(level_msgs)
    await message.answer(
        f"✅ Начислено <b>{amount}</b> XP пользователю <code>{target_id}</code>"
        + (f"\n{level_block}" if level_block else "")
    )

@dp.message(Command("give_resource"))
async def cmd_give_resource(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = None
    res_key = None
    amount = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if len(parts) >= 3 and parts[2].isdigit():
            res_key = parts[1]
            amount = int(parts[2])
    else:
        if len(parts) >= 4 and parts[1].isdigit() and parts[3].isdigit():
            target_id = int(parts[1])
            res_key = parts[2]
            amount = int(parts[3])

    if not target_id or not res_key or res_key not in RESOURCES or not amount or amount <= 0:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in RESOURCES.items())
        await message.answer(
            "❌ Формат:\n"
            "<code>/give_resource 12345678 iron_ore 10</code>\n"
            "или ответом: <code>/give_resource iron_ore 10</code>\n\n"
            f"Доступные ресурсы:\n{keys}"
        )
        return

    register_user(target_id)
    user = get_user(target_id)
    resources = get_resources(user)
    resources[res_key] = resources.get(res_key, 0) + amount
    save_resources(target_id, resources)
    await message.answer(
        f"✅ Выдано {RESOURCES[res_key]['name']} x<b>{amount}</b> пользователю <code>{target_id}</code>"
    )

@dp.message(Command("give_tool"))
async def cmd_give_tool(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = None
    ttype = None
    level = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if len(parts) >= 3 and parts[2].isdigit():
            ttype, level = parts[1], int(parts[2])
    else:
        if len(parts) >= 4 and parts[1].isdigit() and parts[3].isdigit():
            target_id, ttype, level = int(parts[1]), parts[2], int(parts[3])

    if not target_id or ttype not in TOOL_TIERS or not level or not (0 <= level <= len(TOOL_TIERS[ttype])):
        await message.answer(
            "❌ Формат:\n<code>/give_tool 12345678 mining 5</code>\n"
            "или ответом: <code>/give_tool mining 5</code>\n\n"
            "Типы: mining / fishing / hunting"
        )
        return
    register_user(target_id)
    update_user(target_id, **{f"tool_level_{ttype}": level})
    await message.answer(f"✅ Инструмент «{ttype}» установлен на уровень {level} для <code>{target_id}</code>")

@dp.message(Command("give_location_item"))
async def cmd_give_location_item(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, key = _resolve_id_and_arg(message, parts)
    if not target_id or not key or key not in LOCATION_BOSS_ITEMS:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in LOCATION_BOSS_ITEMS.items())
        await message.answer(
            "❌ Формат:\n<code>/give_location_item 12345678 golem_core</code>\n"
            "или ответом: <code>/give_location_item golem_core</code>\n\n"
            f"Доступные трофеи:\n{keys}"
        )
        return
    register_user(target_id)
    user = get_user(target_id)
    items = get_location_items(user)
    if key in items:
        items[key] += 1
    else:
        items[key] = 1
        if not user.get("equipped_location_item"):
            update_user(target_id, equipped_location_item=key)
    save_location_items(target_id, items)
    await message.answer(f"✅ Трофей <b>{LOCATION_BOSS_ITEMS[key]['name']}</b> выдан пользователю <code>{target_id}</code>")

@dp.message(Command("set_reputation"))
async def cmd_set_reputation(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, val_str = _resolve_id_and_arg(message, parts)
    if not target_id or not val_str or not val_str.lstrip("-").isdigit():
        await message.answer(
            "❌ Формат: <code>/set_reputation 12345678 50</code> "
            "или ответом: <code>/set_reputation 50</code>"
        )
        return
    value = max(REP_MIN, min(REP_MAX, int(val_str)))
    register_user(target_id)
    update_user(target_id, reputation=value)
    title, _ = get_rep_title(value)
    await message.answer(
        f"✅ Репутация пользователя <code>{target_id}</code> установлена: <b>{value}</b> ({title})"
    )

@dp.message(Command("reset_all_cooldowns"))
async def cmd_reset_all_cooldowns(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = _resolve_id_only(message, parts)
    if not target_id:
        await message.answer(
            "❌ Формат: <code>/reset_all_cooldowns 12345678</code> "
            "или ответом на сообщение игрока"
        )
        return
    register_user(target_id)
    update_user(
        target_id,
        last_work_time=0,
        last_hunt_time=0,
        last_fish_time=0,
        last_mine_time=0,
        boss_cooldowns="{}",
        location_boss_cooldowns="{}",
    )
    await message.answer(
        f"✅ Все кулдауны сброшены для <code>{target_id}</code> "
        f"(работа, добыча, боссы, боссы локаций)"
    )

@dp.message(Command("server_stats"))
async def cmd_server_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(balance),0), "
                "COALESCE(AVG(level),0), COALESCE(MAX(level),0) FROM users"
            )
            total_users, total_balance, avg_level, max_level = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
            banned = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE spouse_id IS NOT NULL")
            married = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM relationships")
            relationships_count = cur.fetchone()[0]

    await message.answer(
        f"📊 <b>Статистика сервера</b>\n\n"
        f"👥 Всего игроков: <b>{total_users}</b>\n"
        f"🚫 Забанено: <b>{banned}</b>\n"
        f"💍 В браке: <b>{married // 2}</b> пар\n"
        f"💞 Связей (отношения): <b>{relationships_count}</b>\n\n"
        f"💰 Монет в экономике: <b>{total_balance}</b>\n"
        f"⭐ Средний уровень: <b>{avg_level:.1f}</b>\n"
        f"🏆 Макс. уровень: <b>{max_level}</b>\n\n"
        f"👥 Групп с ботом: <b>{len(registered_chats)}</b>"
    )

@dp.message(Command("give_all"))
async def cmd_give_all(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    if len(parts) != 3 or parts[1].lower() not in ("coins", "exp") or not parts[2].lstrip("-").isdigit():
        await message.answer(
            "❌ Формат:\n"
            "<code>/give_all coins 100</code> — начислить всем монеты\n"
            "<code>/give_all exp 50</code> — начислить всем опыт"
        )
        return

    field = "balance" if parts[1].lower() == "coins" else "exp"
    amount = int(parts[2])

    status_msg = await message.answer("⏳ Начисляю всем игрокам...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {field} = {field} + %s", (amount,))
            count = cur.rowcount
            conn.commit()

    label = "монет" if field == "balance" else "опыта"
    await status_msg.edit_text(f"✅ Начислено <b>{amount}</b> {label} всем игрокам (<b>{count}</b> чел.)")

@dp.message(Command("give_item"))
async def cmd_give_item(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, key = _resolve_id_and_arg(message, parts)
    if not target_id or not key or key not in SHOP_ITEMS:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in SHOP_ITEMS.items())
        await message.answer(
            "❌ Формат:\n<code>/give_item 12345678 laptop</code>\n"
            "или ответом: <code>/give_item laptop</code>\n\n"
            f"Доступные предметы:\n{keys}"
        )
        return
    register_user(target_id)
    item = SHOP_ITEMS[key]
    update_user(target_id, **{item["flag"]: 1})
    await message.answer(f"✅ Предмет <b>{item['name']}</b> выдан пользователю <code>{target_id}</code>")


@dp.message(Command("give_pet"))
async def cmd_give_pet(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    import json
    parts = message.text.strip().split()
    target_id, key = _resolve_id_and_arg(message, parts)
    if not target_id or not key or key not in PETS:
        normal_keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in PETS.items() if not v.get("admin_only"))
        admin_keys  = "\n".join(f"  <code>{k}</code> — {v['name']} 👑" for k, v in PETS.items() if v.get("admin_only"))
        await message.answer(
            "❌ Формат:\n<code>/give_pet 12345678 dragon</code>\n"
            "или ответом: <code>/give_pet dragon</code>\n\n"
            f"Обычные питомцы:\n{normal_keys}\n\n"
            f"👑 Админские питомцы (только вручную):\n{admin_keys}"
        )
        return
    register_user(target_id)
    user = get_user(target_id)
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}
    pet = PETS[key]
    if key in collection:
        collection[key] = min(collection[key] + 1, 20)
    else:
        collection[key] = pet["base_bonus"]
        if not user.get("active_pet"):
            update_user(target_id, active_pet=key)
    update_user(target_id, pet_collection=json.dumps(collection))
    tag = " 👑 (админский)" if pet.get("admin_only") else ""
    await message.answer(f"✅ Питомец <b>{pet['name']}</b>{tag} выдан пользователю <code>{target_id}</code>")

@dp.message(Command("give_boss_item"))
async def cmd_give_boss_item(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, key = _resolve_id_and_arg(message, parts)
    if not target_id or not key or key not in BOSS_ITEMS:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in BOSS_ITEMS.items())
        await message.answer(
            "❌ Формат:\n<code>/give_boss_item 12345678 manas_bow</code>\n"
            "или ответом: <code>/give_boss_item manas_bow</code>\n\n"
            f"Доступные предметы:\n{keys}"
        )
        return
    register_user(target_id)
    user = get_user(target_id)
    items = get_boss_items(user)
    if key in items:
        items[key] += 1
    else:
        items[key] = 1
        if not user.get("equipped_boss_item"):
            update_user(target_id, equipped_boss_item=key)
    save_boss_items(target_id, items)
    await message.answer(f"✅ Предмет <b>{BOSS_ITEMS[key]['name']}</b> выдан пользователю <code>{target_id}</code>")


@dp.message(Command("give_property"))
async def cmd_give_property(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, key = _resolve_id_and_arg(message, parts)
    if not target_id or not key or key not in PROPERTIES:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in PROPERTIES.items())
        await message.answer(
            "❌ Формат:\n<code>/give_property 12345678 kiosk</code>\n"
            "или ответом: <code>/give_property kiosk</code>\n\n"
            f"Доступная недвижимость:\n{keys}"
        )
        return
    register_user(target_id)
    user = get_user(target_id)
    props = get_user_properties(user)
    props[key] = int(time.time())
    save_user_properties(target_id, props)
    await message.answer(
        f"✅ Недвижимость <b>{PROPERTIES[key]['name']}</b> выдана пользователю <code>{target_id}</code>")


@dp.message(Command("give_shards"))
async def cmd_give_shards(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, amount_str = _resolve_id_and_arg(message, parts)
    if not target_id or not amount_str or not amount_str.lstrip("-").isdigit():
        await message.answer(
            "❌ Формат:\n<code>/give_shards 12345678 100</code>\n"
            "или ответом: <code>/give_shards 100</code>"
        )
        return
    amount = int(amount_str)
    register_user(target_id)
    user = get_user(target_id)
    new_shards = max(0, user.get("shards", 0) + amount)
    update_user(target_id, shards=new_shards)
    await message.answer(
        f"✅ Осколки пользователя <code>{target_id}</code>: <b>{new_shards}</b> "
        f"(изменение: {amount:+d})"
    )


@dp.message(Command("give_achievement"))
async def cmd_give_achievement(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, key = _resolve_id_and_arg(message, parts)
    if not target_id or not key or key not in ACHIEVEMENTS:
        keys = "\n".join(f"  <code>{k}</code>" for k in ACHIEVEMENTS)
        await message.answer(
            "❌ Формат:\n<code>/give_achievement 12345678 first_work</code>\n"
            "или ответом: <code>/give_achievement first_work</code>\n\n"
            f"Доступные ключи:\n{keys}"
        )
        return
    register_user(target_id)
    msg = grant_achievement_now(target_id, key)
    if msg:
        await message.answer(f"✅ Достижение выдано пользователю <code>{target_id}</code>:\n{msg}")
    else:
        await message.answer("ℹ️ У пользователя уже есть это достижение (или ключ неверный).")


@dp.message(Command("set_job"))
async def cmd_set_job(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, job_key = _resolve_id_and_arg(message, parts)
    if not target_id or not job_key or job_key not in JOBS:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in JOBS.items())
        await message.answer(
            "❌ Формат:\n<code>/set_job 12345678 intel_3</code>\n"
            "или ответом: <code>/set_job intel_3</code>\n\n"
            f"Доступные профессии:\n{keys}"
        )
        return
    register_user(target_id)
    update_user(target_id, job=JOBS[job_key]["name"], job_rank=1)
    await message.answer(
        f"✅ Профессия пользователя <code>{target_id}</code> установлена: "
        f"<b>{JOBS[job_key]['name']}</b>"
    )


@dp.message(Command("set_energy"))
async def cmd_set_energy(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, val_str = _resolve_id_and_arg(message, parts)
    if not target_id or not val_str or not val_str.isdigit():
        await message.answer(
            "❌ Формат: <code>/set_energy 12345678 100</code> "
            "или ответом: <code>/set_energy 100</code>"
        )
        return
    register_user(target_id)
    update_user(target_id, energy=int(val_str))
    await message.answer(f"✅ Энергия пользователя <code>{target_id}</code> установлена: <b>{val_str}</b>")


@dp.message(Command("set_hp"))
async def cmd_set_hp(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id, val_str = _resolve_id_and_arg(message, parts)
    if not target_id or not val_str or not val_str.isdigit():
        await message.answer(
            "❌ Формат: <code>/set_hp 12345678 100</code> "
            "или ответом: <code>/set_hp 100</code>"
        )
        return
    register_user(target_id)
    update_user(target_id, hp=int(val_str))
    await message.answer(f"✅ HP пользователя <code>{target_id}</code> установлено: <b>{val_str}</b>")


@dp.message(Command("reset_cooldown"))
async def cmd_reset_cooldown(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = _resolve_id_only(message, parts)
    if not target_id:
        await message.answer(
            "❌ Формат: <code>/reset_cooldown 12345678</code> "
            "или ответом на сообщение игрока"
        )
        return
    register_user(target_id)
    update_user(target_id, last_work_time=0)
    await message.answer(f"✅ Кулдаун работы сброшен для <code>{target_id}</code>")


@dp.message(Command("ban"))


async def cmd_ban_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = _resolve_id_only(message, parts)
    if not target_id:
        await message.answer(
            "❌ Формат: <code>/ban 12345678</code> или ответом на сообщение игрока"
        )
        return
    if target_id == ADMIN_ID:
        await message.answer("❌ Нельзя забанить самого себя.")
        return
    register_user(target_id)
    update_user(target_id, is_banned=1)
    await message.answer(f"🚫 Пользователь <code>{target_id}</code> заблокирован в игре.")


@dp.message(Command("unban"))
async def cmd_unban_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = _resolve_id_only(message, parts)
    if not target_id:
        await message.answer(
            "❌ Формат: <code>/unban 12345678</code> или ответом на сообщение игрока"
        )
        return
    register_user(target_id)
    update_user(target_id, is_banned=0)
    await message.answer(f"✅ Пользователь <code>{target_id}</code> разблокирован.")


@dp.message(Command("user_info"))
async def cmd_user_info(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = _resolve_id_only(message, parts)
    if not target_id:
        await message.answer(
            "❌ Формат: <code>/user_info 12345678</code> или ответом на сообщение игрока"
        )
        return
    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден в базе.")
        return
    job = get_job(user)
    await message.answer(
        f"🔍 <b>Инфо об игроке</b> <code>{target_id}</code>\n\n"
        f"👤 Username: @{user.get('username') or '—'}\n"
        f"⭐ Уровень: {user['level']} | XP: {user['exp']}\n"
        f"💰 Баланс: {user['balance']}\n"
        f"🔶 Осколки: {user.get('shards', 0)}\n"
        f"💼 Профессия: {user['job']} (грейд {job['grade'] if job else 0})\n"
        f"❤️ HP: {user['hp']} | ⚡ Энергия: {user['energy']}\n"
        f"⭐ Репутация: {user.get('reputation', 0)}\n"
        f"🎖 Титул: {user.get('active_title') or '—'}\n"
        f"💍 Супруг: {user.get('spouse_id') or '—'}\n"
        f"🐾 Питомец: {user.get('active_pet') or '—'}\n"
        f"🔗 Приглашено рефералов: {user.get('referral_count', 0)}\n"
        f"🚫 Забанен: {'Да' if user.get('is_banned') else 'Нет'}"
    )


ADMIN_HELP_CATEGORIES = {
    "economy": {
        "label": "💰 Экономика",
        "text": (
            "💰 <b>Экономика</b>\n\n"
            "<code>/give_money [id] сумма</code> — начислить монеты\n"
            "<code>/give_exp [id] сумма</code> — начислить опыт\n"
            "<code>/give_shards [id] сумма</code> — начислить осколки\n\n"
            "<i>Вместо [id] можно ответить на сообщение игрока</i>"
        ),
    },
    "stats": {
        "label": "📊 Характеристики",
        "text": (
            "📊 <b>Характеристики и ресурсы</b>\n\n"
            "<code>/set_stat [id] стат значение</code> — установить характеристику/навык\n"
            "<code>/set_energy [id] значение</code> — установить энергию\n"
            "<code>/set_hp [id] значение</code> — установить HP\n"
            "<code>/reset_cooldown [id]</code> — сбросить кулдаун работы\n"
            "<code>/reset_daily [id]</code> — сбросить ежедневный бонус\n"
            "<code>/reset_all_cooldowns [id]</code> — сбросить кулдаун всего"
        ),
    },
    "items": {
        "label": "🎒 Предметы и питомцы",
        "text": (
            "🎒 <b>Предметы, питомцы, недвижимость</b>\n\n"
            "<code>/give_item [id] ключ</code> — выдать снаряжение\n"
            "<code>/give_pet [id] ключ</code> — выдать питомца\n"
            "<code>/give_boss_item [id] ключ</code> — выдать трофей с босса\n"
            "<code>/give_property [id] ключ</code> — выдать недвижимость\n"
            "<code>/give_resource [id] ключ</code> — выдать ресурс\n"
            "<code>/give_tool [id] ключ</code> — выдать инструмент\n"
            "<code>/give_location_item [id] ключ</code> — выдать трофей локационного босса"
        ),
    },
    "progression": {
        "label": "🏆 Прогресс",
        "text": (
            "🏆 <b>Профессии, титулы, достижения</b>\n\n"
            "<code>/set_job [id] job_key</code> — установить профессию\n"
            "<code>/set_reputation [id] значение</code> — установить репутацию\n"
            "<code>/give_title [id] ключ</code> — выдать титул\n"
            "<code>/remove_title [id] ключ</code> — снять титул\n"
            "<code>/give_achievement [id] ключ</code> — выдать достижение"
        ),
    },
    "moderation": {
        "label": "🚫 Модерация",
        "text": (
            "🚫 <b>Модерация</b>\n\n"
            "<code>/ban [id]</code> — заблокировать игрока\n"
            "<code>/unban [id]</code> — разблокировать игрока\n"
            "<code>/user_info [id]</code> — посмотреть данные игрока\n\n"
            "<i>Вместо [id] можно ответить на сообщение игрока</i>"
        ),
    },
    "system": {
        "label": "⚙️ Система и рассылки",
        "text": (
            "⚙️ <b>Система и ивенты</b>\n\n"
            "<code>/start_event ключ</code> — запустить ивент\n"
            "<code>/end_event</code> — завершить ивент\n"
            "<code>/current_event</code> — посмотреть активный ивент\n\n"
            "📢 <b>Рассылка</b>\n"
            "<code>объявление текст</code> — рассылка текста всем\n"
            "<code>объявление</code> (ответом на сообщение) — рассылка копии "
            "(фото/видео/текст)\n\n"
            "<code>/server_stats</code> — статистика сервера\n"
            "<code>/give_all coins/exp сумма</code> — начислить всем игрокам монеты/опыт"
        ),
    },
}


@dp.message(Command("admin"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("админ", "admin", "админка")))
async def cmd_admin_help(message: Message):
    if message.from_user.id != ADMIN_ID:
        return  # обычным игрокам не отвечаем вообще, чтобы не палить наличие админки

    builder = InlineKeyboardBuilder()
    for key, cat in ADMIN_HELP_CATEGORIES.items():
        builder.button(text=cat["label"], callback_data=f"admin_help:{key}")
    builder.adjust(1)
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\nВыбери раздел команд:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("admin_help:"))
async def callback_admin_help(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    key = callback.data.split(":")[1]
    cat = ADMIN_HELP_CATEGORIES.get(key)
    if not cat:
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ Назад", callback_data="admin_help_back")
    await callback.answer()
    await callback.message.edit_text(cat["text"], reply_markup=builder.as_markup())


@dp.callback_query(F.data == "admin_help_back")
async def callback_admin_help_back(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for key, cat in ADMIN_HELP_CATEGORIES.items():
        builder.button(text=cat["label"], callback_data=f"admin_help:{key}")
    builder.adjust(1)
    await callback.answer()
    await callback.message.edit_text(
        "🛠 <b>Панель администратора</b>\n\nВыбери раздел команд:",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("reset_daily"))
async def cmd_reset_daily(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    parts = message.text.strip().split()
    target_id = _resolve_id_only(message, parts)
    if not target_id:
        await message.answer(
            "❌ Формат: <code>/reset_daily 12345678</code> "
            "или ответом на сообщение игрока"
        )
        return
    register_user(target_id)
    update_user(target_id, last_daily_claim=0)
    await message.answer(f"✅ Ежедневный бонус сброшен для <code>{target_id}</code>")


@dp.message(Command("set_stat"))
async def cmd_set_stat(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    parts = message.text.strip().split()
    # /set_stat 12345678 agility 10  ИЛИ reply + /set_stat agility 10
    target_id = None
    stat_name = None
    value     = None

    VALID_STATS = {
        "agility", "endurance", "charisma", "intellect", "luck",
        "level", "balance",
        "communication_level", "driving_level", "service_level",
        "organization_level", "management_level",
    }

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if len(parts) >= 3:
            stat_name = parts[1].lower()
            if parts[2].lstrip("-").isdigit():
                value = int(parts[2])
    else:
        if len(parts) >= 4 and parts[1].lstrip("-").isdigit():
            target_id = int(parts[1])
            stat_name = parts[2].lower()
            if parts[3].lstrip("-").isdigit():
                value = int(parts[3])

    if not target_id or stat_name not in VALID_STATS or value is None:
        await message.answer(
            "❌ Формат:\n"
            "<code>/set_stat 12345678 agility 10</code>\n"
            "или ответом: <code>/set_stat agility 10</code>\n\n"
            f"Доступные статы: {', '.join(sorted(VALID_STATS))}"
        )
        return

    register_user(target_id)
    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return

    update_user(target_id, **{stat_name: value})
    await message.answer(
        f"✅ Стат <b>{stat_name}</b> пользователя <code>{target_id}</code> "
        f"установлен в <b>{value}</b>"
    )
@dp.message(Command("give_title"))
async def cmd_give_title(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    parts = message.text.strip().split()
    target_id  = None
    title_key  = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if len(parts) >= 2:
            title_key = parts[1].lower()
    else:
        if len(parts) >= 3 and parts[1].isdigit():
            target_id = int(parts[1])
            title_key = parts[2].lower()

    if not target_id or not title_key or title_key not in TITLES:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in TITLES.items())
        await message.answer(
            "❌ Формат:\n"
            "<code>/give_title 12345678 tester</code>\n"
            "или ответом: <code>/give_title tester</code>\n\n"
            f"Доступные титулы:\n{keys}"
        )
        return

    register_user(target_id)
    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return

    owned = get_user_titles(user)
    owned.add(title_key)
    save_titles(target_id, owned)
    if not user.get("active_title"):
        update_user(target_id, active_title=title_key)

    await message.answer(
        f"✅ Титул <b>{TITLES[title_key]['name']}</b> выдан пользователю <code>{target_id}</code>"
    )


@dp.message(Command("remove_title"))
async def cmd_remove_title(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    parts = message.text.strip().split()
    target_id = None
    title_key = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        if len(parts) >= 2:
            title_key = parts[1].lower()
    else:
        if len(parts) >= 3 and parts[1].isdigit():
            target_id = int(parts[1])
            title_key = parts[2].lower()

    if not target_id or not title_key:
        await message.answer("❌ Формат: <code>/remove_title 12345678 tester</code>")
        return

    user = get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return

    owned = get_user_titles(user)
    owned.discard(title_key)
    save_titles(target_id, owned)
    if user.get("active_title") == title_key:
        update_user(target_id, active_title="")

    await message.answer(f"✅ Титул <code>{title_key}</code> снят с пользователя <code>{target_id}</code>")

@dp.message(F.text.func(lambda t: t and t.strip().lower().startswith(("покушать ", "съесть ", "eat "))))
async def cmd_eat_text(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        return  # просто "покушать" — уже обработано другим хендлером

    qty_str = parts[-1].lower().lstrip("x")
    quantity = int(qty_str) if qty_str.isdigit() else 1
    item_query = " ".join(parts[1:-1]) if qty_str.isdigit() else " ".join(parts[1:])
    item_query = item_query.lower().strip()

    # ищем предмет по названию (без эмодзи, без учёта регистра)
    item_key = None
    for key, item in CONSUMABLES.items():
        clean_name = item["name"].split(" ", 1)[-1].lower()  # убираем эмодзи
        if item_query in clean_name or item_query == key:
            item_key = key
            break

    if not item_key:
        await message.answer(f"❌ Не найден предмет «{item_query}». Посмотри список: <code>покушать</code>")
        return

    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    success, text = do_use_consumable(user, item_key, quantity)
    await message.answer(text)

@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("перс", "персонаж")), F.chat.type == "private")
async def txt_profile_alias_private(message: Message):
    await btn_profile_private(message)

# =====================================================================
# БРАКИ
# =====================================================================
active_marriage_proposals: dict[int, dict] = {}

@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and (
        t.strip().lower() == "брак" or
        t.strip().lower().startswith("брак ")
    ))
)
async def marriage_propose(message: Message):
    chat_id       = message.chat.id
    proposer_id   = message.from_user.id
    proposer_name = message.from_user.full_name

    if chat_id in active_marriage_proposals:
        await message.answer("💍 В этом чате уже есть незавершённое предложение!")
        return

    proposer = get_user_safe(proposer_id, message.from_user.username or proposer_name)
    if proposer.get("spouse_id"):
        await message.answer("❌ Ты уже в браке! Разведись командой <b>развод</b>.")
        return

    target_id   = None
    target_name = None
    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        if not ru.is_bot:
            target_id, target_name = ru.id, ru.full_name
    else:
        if message.entities:
            for ent in message.entities:
                if ent.type == "text_mention" and ent.user:
                    target_id, target_name = ent.user.id, ent.user.full_name
                    break
                elif ent.type == "mention":
                    uname = message.text[ent.offset:ent.offset + ent.length]
                    try:
                        cm = await bot.get_chat_member(chat_id, uname)
                        target_id, target_name = cm.user.id, cm.user.full_name
                    except Exception:
                        pass
                    break

    if not target_id:
        await message.answer("❌ Укажи пользователя: <code>брак @username</code> или ответом на сообщение.")
        return
    if target_id == proposer_id:
        await message.answer("❌ Нельзя жениться на себе!")
        return

    register_user(target_id)
    target = get_user(target_id)
    if not target:
        await message.answer("❌ Этот пользователь ещё не зарегистрирован в игре.")
        return
    if target.get("spouse_id"):
        await message.answer(f"❌ {target_name} уже состоит в браке!")
        return

    active_marriage_proposals[chat_id] = {
        "proposer_id": proposer_id, "proposer_name": proposer_name,
        "target_id": target_id, "target_name": target_name,
    }

    builder = InlineKeyboardBuilder()
    builder.button(text="💍 Согласен(на)!", callback_data=f"marry_accept:{chat_id}:{target_id}")
    builder.button(text="💔 Отказать",       callback_data=f"marry_decline:{chat_id}:{target_id}")
    builder.adjust(2)

    await message.answer(
        f"💍 <b>ПРЕДЛОЖЕНИЕ РУКИ И СЕРДЦА!</b>\n\n"
        f"👤 {proposer_name} делает предложение {target_name}!\n\n"
        f"<a href='tg://user?id={target_id}'>{target_name}</a>, что скажешь?",
        reply_markup=builder.as_markup()
    )

    async def auto_cancel():
        await asyncio.sleep(120)
        if chat_id in active_marriage_proposals:
            del active_marriage_proposals[chat_id]
            await message.answer(f"⏰ {target_name} не ответил(а). Предложение аннулировано.")
    asyncio.create_task(auto_cancel())


@dp.callback_query(F.data.startswith("marry_accept:"))
async def marriage_accept(callback: CallbackQuery):
    parts   = callback.data.split(":")
    chat_id = int(parts[1])
    tid     = int(parts[2])

    if callback.from_user.id != tid:
        await callback.answer("Это предложение не тебе!", show_alert=True)
        return

    proposal = active_marriage_proposals.get(chat_id)
    if not proposal:
        await callback.answer("Предложение уже недействительно.", show_alert=True)
        return

    proposer_id   = proposal["proposer_id"]
    proposer_name = proposal["proposer_name"]
    target_name   = proposal["target_name"]

    proposer = get_user(proposer_id)
    target   = get_user(tid)
    if not proposer or not target:
        del active_marriage_proposals[chat_id]
        await callback.answer("Ошибка данных.", show_alert=True)
        return
    if proposer.get("spouse_id") or target.get("spouse_id"):
        del active_marriage_proposals[chat_id]
        await callback.answer("Один из вас уже успел жениться!", show_alert=True)
        return

    now = int(time.time())
    update_user(proposer_id, spouse_id=tid, married_at=now)
    update_user(tid, spouse_id=proposer_id, married_at=now)

    del active_marriage_proposals[chat_id]
    await callback.answer("💍 Поздравляем с браком!", show_alert=True)

    extra_msgs = []
    for uid_ in (proposer_id, tid):
        u = get_user(uid_)
        if u:
            extra_msgs += check_and_grant_achievements(u)
            extra_msgs += check_and_grant_titles(u)

    text = (
        f"🎉💍 <b>СВАДЬБА СОСТОЯЛАСЬ!</b>\n\n"
        f"👰🤵 <b>{proposer_name}</b> и <b>{target_name}</b> теперь официально семья!\n"
        f"Совет да любовь! 💕\n\n"
        f"🎁 Брак даёт совместный бонус: +5% к монетам и опыту, "
        f"а если оба супруга недавно работали — бонус удваивается!"
    )
    if extra_msgs:
        text += "\n\n" + "\n".join(extra_msgs)
    await callback.message.answer(text)

@dp.callback_query(F.data.startswith("marry_decline:"))
async def marriage_decline(callback: CallbackQuery):
    parts   = callback.data.split(":")
    chat_id = int(parts[1])
    tid     = int(parts[2])

    if callback.from_user.id != tid:
        await callback.answer("Это предложение не тебе!", show_alert=True)
        return

    proposal = active_marriage_proposals.get(chat_id)
    if not proposal:
        await callback.answer("Предложение уже недействительно.", show_alert=True)
        return

    del active_marriage_proposals[chat_id]
    await callback.answer()
    await callback.message.answer(
        f"💔 <b>{proposal['target_name']}</b> отклонил(а) предложение {proposal['proposer_name']}..."
    )


@dp.message(Command("divorce"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("развод", "divorce")))
async def cmd_divorce(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)
    spouse_id = user.get("spouse_id")
    if not spouse_id:
        await message.answer("❌ Ты не в браке.")
        return

    spouse = get_user(spouse_id)
    update_user(uid, spouse_id=None, married_at=0)
    update_user(spouse_id, spouse_id=None, married_at=0)

    spouse_name = (spouse.get("username") if spouse else "") or f"#{spouse_id}"
    await message.answer(f"💔 Ты развёлся(лась) с <b>{spouse_name}</b>. Свободен(на) как ветер!")


@dp.message(Command("family"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("семья", "супруг", "family")))
async def cmd_family(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)
    spouse_id = user.get("spouse_id")
    if not spouse_id:
        await message.answer("💍 Ты не в браке.\nИспользуй <code>брак @username</code> в группе, чтобы сделать предложение!")
        return

    spouse = get_user(spouse_id)
    if not spouse:
        update_user(uid, spouse_id=None, married_at=0)
        await message.answer("⚠️ Супруг(а) не найден(а) в базе. Брак аннулирован.")
        return

    married_at  = user.get("married_at", 0)
    days        = max(0, (int(time.time()) - married_at) // 86400)
    spouse_name = spouse.get("username") or f"#{spouse_id}"
    coin_b, xp_b = get_marriage_bonus(user)

    await message.answer(
        f"💍 <b>Семья</b>\n\n"
        f"👤 Супруг(а): <b>{spouse_name}</b>\n"
        f"📅 В браке: <b>{days}</b> дн.\n"
        f"🎁 Текущий бонус: +{coin_b}% монет, +{xp_b}% опыта\n\n"
        f"<i>Переводите монеты друг другу командой <code>перевод</code>!</i>"
    )
# =====================================================================
# ДУЭЛИ
# =====================================================================
active_duels: dict[int, dict] = {}  # chat_id -> duel data

@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("дуэль "))
)
async def duel_challenge(message: Message):
    chat_id   = message.chat.id
    challenger_id   = message.from_user.id
    challenger_name = message.from_user.full_name

    if chat_id in active_duels:
        await message.answer("⚔️ В этом чате уже идёт дуэль! Дождитесь окончания.")
        return

    # Парсим ставку
    parts = message.text.strip().split()
    bet   = None
    for p in reversed(parts):
        if p.isdigit():
            bet = int(p)
            break

    if not bet or bet <= 0:
        await message.answer("❌ Укажи ставку: <code>дуэль @username 500</code>")
        return

    # Определяем цель
    target_id   = None
    target_name = None

    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        if not ru.is_bot:
            target_id   = ru.id
            target_name = ru.full_name
    else:
        if message.entities:
            for ent in message.entities:
                if ent.type == "text_mention" and ent.user:
                    target_id   = ent.user.id
                    target_name = ent.user.full_name
                    break
                elif ent.type == "mention":
                    uname = message.text[ent.offset:ent.offset + ent.length]
                    try:
                        cm = await bot.get_chat_member(chat_id, uname)
                        target_id   = cm.user.id
                        target_name = cm.user.full_name
                    except Exception:
                        pass
                    break

    if not target_id:
        await message.answer("❌ Укажи игрока: <code>дуэль @username 500</code>")
        return
    if target_id == challenger_id:
        await message.answer("❌ Нельзя вызвать на дуэль самого себя!")
        return

    challenger = get_user_safe(challenger_id)
    if is_incapacitated(challenger):
        await message.answer(get_incapacitated_message(challenger))
        return
    if challenger["balance"] < bet:
        await message.answer(
            f"❌ Недостаточно монет!\n"
            f"Ставка: <b>{bet}</b> | Баланс: <b>{challenger['balance']}</b>"
        )
        return

    register_user(target_id)
    target = get_user(target_id)
    if not target:
        await message.answer("❌ Противник не зарегистрирован в игре.")
        return
    if is_incapacitated(target):
        await message.answer(f"❌ {target_name} сейчас слишком слаб для дуэли (HP < 5%).")
        return
    if target["balance"] < bet:
        await message.answer(
            f"❌ У <b>{target_name}</b> недостаточно монет для этой ставки.\n"
            f"Его баланс: <b>{target['balance']}</b>"
        )
        return

    active_duels[chat_id] = {
        "challenger_id":   challenger_id,
        "challenger_name": challenger_name,
        "target_id":       target_id,
        "target_name":     target_name,
        "bet":             bet,
        "accepted":        False,
    }

    builder = InlineKeyboardBuilder()
    builder.button(
        text="⚔️ Принять дуэль",
        callback_data=f"duel_accept:{chat_id}:{target_id}"
    )
    builder.button(
        text="🏳️ Отказаться",
        callback_data=f"duel_decline:{chat_id}:{target_id}"
    )
    builder.adjust(2)

    await message.answer(
        f"⚔️ <b>ВЫЗОВ НА ДУЭЛЬ!</b>\n\n"
        f"🗡 {challenger_name} вызывает {target_name}\n"
        f"💰 Ставка: <b>{bet}</b> монет\n\n"
        f"<a href='tg://user?id={target_id}'>{target_name}</a>, принимаешь вызов?",
        reply_markup=builder.as_markup()
    )

    # Автоотмена через 60 секунд
    async def auto_cancel():
        await asyncio.sleep(60)
        if chat_id in active_duels and not active_duels[chat_id]["accepted"]:
            del active_duels[chat_id]
            await message.answer(
                f"⏰ <b>{target_name}</b> не ответил на вызов. Дуэль отменена."
            )
    asyncio.create_task(auto_cancel())


@dp.callback_query(F.data.startswith("duel_accept:"))
async def duel_accept(callback: CallbackQuery):
    parts   = callback.data.split(":")
    chat_id = int(parts[1])
    tid     = int(parts[2])

    if callback.from_user.id != tid:
        await callback.answer("Это не твой вызов!", show_alert=True)
        return

    duel = active_duels.get(chat_id)
    if not duel:
        await callback.answer("Дуэль уже недействительна.", show_alert=True)
        return

    duel["accepted"] = True
    await callback.answer()

    c_id   = duel["challenger_id"]
    c_name = duel["challenger_name"]
    t_id   = duel["target_id"]
    t_name = duel["target_name"]
    bet    = duel["bet"]

    challenger = get_user(c_id)
    target = get_user(t_id)
    if not challenger or not target:
        del active_duels[chat_id]
        await bot.send_message(chat_id, "❌ Ошибка: игрок не найден в базе.")
        return
    if challenger["balance"] < bet or target["balance"] < bet:
        del active_duels[chat_id]
        await bot.send_message(chat_id, "❌ У одного из игроков не хватает монет. Дуэль отменена.")
        return

    # Считаем силу — характеристики + рандом
    def calc_power(user: dict) -> tuple[int, int]:
        base = (
            user["agility"]   * 3 +
            user["endurance"] * 3 +
            user["charisma"]  * 2 +
            user["intellect"] * 2 +
            user["luck"]      * 2
        )
        roll = random.randint(1, 50)
        return base + roll, roll

    c_power, c_roll = calc_power(challenger)
    t_power, t_roll = calc_power(target)

    await bot.send_message(chat_id,
        f"⚔️ <b>ДУЭЛЬ НАЧАЛАСЬ!</b>\n\n"
        f"🗡 {c_name}\n"
        f"   Сила: {c_power} (стат: {c_power - c_roll} + 🎲{c_roll})\n\n"
        f"🛡 {t_name}\n"
        f"   Сила: {t_power} (стат: {t_power - t_roll} + 🎲{t_roll})\n\n"
        f"💰 Ставка: <b>{bet}</b> монет"
    )

    await asyncio.sleep(2)

    if c_power == t_power:
        # Ничья
        del active_duels[chat_id]
        await bot.send_message(chat_id,
            f"🤝 <b>НИЧЬЯ!</b>\n\n"
            f"Силы равны ({c_power} vs {t_power}).\n"
            f"Монеты остаются у каждого."
        )
        return

    if c_power > t_power:
        winner_id, winner_name = c_id, c_name
        loser_id,  loser_name  = t_id, t_name
        winner_user, loser_user = challenger, target
    else:
        winner_id, winner_name = t_id, t_name
        loser_id,  loser_name  = c_id, c_name
        winner_user, loser_user = target, challenger

    duel_bonus = get_event_extra().get("duel_reward_bonus", 0)
    bonus_win = apply_full_coin_bonus(winner_user, int(bet * (1 + duel_bonus / 100)))
    new_winner_bal = winner_user["balance"] + bonus_win
    new_loser_bal = max(0, loser_user["balance"] - bet)
    update_user(winner_id, balance=new_winner_bal)
    update_user(loser_id, balance=new_loser_bal)
    change_reputation(winner_id, +2)
    change_reputation(loser_id, -4)
    bump_stat(winner_id, "stat_duel_wins")
    bump_stat(loser_id, "stat_duel_losses")

    new_loser_hp, lost_hp = apply_hp_damage(loser_id, loser_user, 8, 15)

    del active_duels[chat_id]

    updated_winner = get_user(winner_id)
    check_and_grant_achievements(updated_winner)
    update_quest_progress(winner_id, "duel_win")

    bonus_line = f" (🐾 бонус: +{bonus_win - bet})" if bonus_win > bet else ""
    await bot.send_message(chat_id,
                           f"🏆 <b>ПОБЕДИТЕЛЬ — {winner_name}!</b>\n\n"
                           f"⚔️ {c_power} vs {t_power}\n\n"
                           f"💰 {winner_name} получает <b>+{bonus_win}</b> монет{bonus_line} → {new_winner_bal}\n"
                           f"💸 {loser_name} теряет <b>-{bet}</b> монет → {new_loser_bal}\n"
                           f"❤️ {loser_name} получает травму: -{lost_hp} HP → {new_loser_hp}/{get_max_hp(loser_user)}"
                           )


@dp.callback_query(F.data.startswith("duel_decline:"))
async def duel_decline(callback: CallbackQuery):
    parts   = callback.data.split(":")
    chat_id = int(parts[1])
    tid     = int(parts[2])

    if callback.from_user.id != tid:
        await callback.answer("Это не твой вызов!", show_alert=True)
        return

    duel = active_duels.get(chat_id)
    if not duel:
        await callback.answer("Дуэль уже недействительна.", show_alert=True)
        return

    del active_duels[chat_id]
    await callback.answer()
    await bot.send_message(chat_id,
        f"🏳️ <b>{duel['target_name']}</b> отказался от дуэли. Трус! 🐔"
    )
# =====================================================================
# ЕЖЕДНЕВНЫЕ КВЕСТЫ
# =====================================================================
DAILY_QUESTS = [
    {"id": "work_3",    "name": "💼 Трудяга",        "desc": "Отработай 3 смены",           "type": "work",     "target": 3,    "reward_coins": 300,   "reward_exp": 100},
    {"id": "work_5",    "name": "💼 Стахановец",      "desc": "Отработай 5 смен",            "type": "work",     "target": 5,    "reward_coins": 600,   "reward_exp": 200},
    {"id": "work_10",   "name": "💼 Работоголик",     "desc": "Отработай 10 смен",           "type": "work",     "target": 10,   "reward_coins": 1500,  "reward_exp": 500},
    {"id": "earn_500",  "name": "💰 Копилка",         "desc": "Заработай 500 монет за смены","type": "earn",     "target": 500,  "reward_coins": 200,   "reward_exp": 80},
    {"id": "earn_2000", "name": "💰 Кошелёк",         "desc": "Заработай 2000 монет",        "type": "earn",     "target": 2000, "reward_coins": 800,   "reward_exp": 300},
    {"id": "earn_5000", "name": "💰 Сейф",            "desc": "Заработай 5000 монет",        "type": "earn",     "target": 5000, "reward_coins": 2000,  "reward_exp": 700},
    {"id": "train_2",   "name": "🏋️ Разминка",        "desc": "Проведи 2 тренировки",        "type": "train",    "target": 2,    "reward_coins": 150,   "reward_exp": 60},
    {"id": "train_5",   "name": "🏋️ Спортсмен",       "desc": "Проведи 5 тренировок",        "type": "train",    "target": 5,    "reward_coins": 400,   "reward_exp": 150},
    {"id": "spend_500", "name": "🛒 Шопоголик",       "desc": "Потрать 500 монет в магазине","type": "spend",    "target": 500,  "reward_coins": 200,   "reward_exp": 80},
    {"id": "stock_3",   "name": "📈 Брокер",          "desc": "Сделай 3 ставки на бирже",    "type": "stock",    "target": 3,    "reward_coins": 300,   "reward_exp": 100},
    {"id": "duel_1",    "name": "⚔️ Боец",            "desc": "Выиграй 1 дуэль",             "type": "duel_win", "target": 1,    "reward_coins": 500,   "reward_exp": 200},
    {"id": "duel_3",    "name": "⚔️ Гладиатор",       "desc": "Выиграй 3 дуэли",             "type": "duel_win", "target": 3,    "reward_coins": 1200,  "reward_exp": 500},
]

# Хранилище прогресса квестов (в памяти, сбрасывается при рестарте — для надёжности лучше в БД)
# Структура: {user_id: {"date": "2024-01-01", "quests": {quest_id: progress}, "completed": set()}}
daily_quest_progress: dict[int, dict] = {}

def get_today() -> str:
    from datetime import date
    return str(date.today())

def get_user_quests(user_id: int) -> dict:
    today = get_today()
    data  = daily_quest_progress.get(user_id)

    if not data or data["date"] != today:
        # Новый день — выдаём 3 случайных квеста
        chosen = random.sample(DAILY_QUESTS, 3)
        daily_quest_progress[user_id] = {
            "date":      today,
            "quests":    {q["id"]: 0 for q in chosen},
            "chosen":    chosen,
            "completed": set(),
        }

    return daily_quest_progress[user_id]

def update_quest_progress(user_id: int, quest_type: str, amount: int = 1) -> list[str]:
    """Обновляет прогресс квестов и возвращает сообщения о завершённых."""
    data      = get_user_quests(user_id)
    messages  = []
    user      = get_user(user_id)
    if not user:
        return messages

    for q in data["chosen"]:
        if q["id"] in data["completed"]:
            continue
        if q["type"] != quest_type:
            continue

        data["quests"][q["id"]] = data["quests"].get(q["id"], 0) + amount

        if data["quests"][q["id"]] >= q["target"]:
            data["completed"].add(q["id"])
            new_balance = user["balance"] + q["reward_coins"]
            new_exp     = user["exp"]     + q["reward_exp"]
            update_user(user_id, balance=new_balance, exp=new_exp)
            user["balance"] = new_balance
            user["exp"]     = new_exp
            change_reputation(user_id, +2)
            messages.append(
                f"✅ <b>Квест выполнен!</b> {q['name']}\n"
                f"<i>{q['desc']}</i>\n"
                f"🎁 +{q['reward_coins']} монет, +{q['reward_exp']} XP"
            )

    return messages

@dp.message(Command("quests"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("квесты", "квест", "задания")))
async def cmd_quests(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)
    data = get_user_quests(uid)

    lines = [f"📋 <b>Ежедневные квесты</b> (обновляются каждый день)\n"]

    for q in data["chosen"]:
        progress  = data["quests"].get(q["id"], 0)
        completed = q["id"] in data["completed"]
        icon      = "✅" if completed else "🔄"
        bar_fill  = min(progress, q["target"])
        bar       = "█" * int(bar_fill / q["target"] * 10) + "░" * (10 - int(bar_fill / q["target"] * 10))

        lines.append(
            f"{icon} <b>{q['name']}</b>\n"
            f"   {q['desc']}\n"
            f"   [{bar}] {min(progress, q['target'])}/{q['target']}\n"
            f"   🎁 {q['reward_coins']} монет + {q['reward_exp']} XP"
        )

    completed_count = len(data["completed"])
    lines.append(f"\n📊 Выполнено: <b>{completed_count}/3</b>")

    if completed_count == 3:
        lines.append("🏆 <b>Все квесты выполнены! Заходи завтра за новыми.</b>")

    await message.answer("\n\n".join(lines))

# =====================================================================
# ЕЖЕДНЕВНЫЙ БОНУС
# =====================================================================
DAILY_BASE_COINS = 100
DAILY_BASE_EXP   = 30
DAILY_STREAK_CAP = 30          # макс. дней в стрике, после которого рост бонуса останавливается
DAILY_RESET_HOURS = 48         # если не зашёл за это время — стрик сбрасывается


def do_claim_daily(user: dict) -> tuple[bool, str]:
    now = int(time.time())
    last = user.get("last_daily_claim", 0)
    streak = user.get("daily_streak", 0)

    if last:
        elapsed_h = (now - last) / 3600
        if elapsed_h < 20:
            remaining_h = 20 - elapsed_h
            return False, f"⏳ Уже забирал сегодня. Возвращайся через ~{remaining_h:.1f}ч."
        if elapsed_h > DAILY_RESET_HOURS:
            streak = 0  # стрик сгорел

    streak = min(streak + 1, DAILY_STREAK_CAP)
    coins = apply_full_coin_bonus(user, DAILY_BASE_COINS + streak * 20)
    exp = apply_combined_xp_bonus(user, DAILY_BASE_EXP + streak * 5)

    new_balance = user["balance"] + coins
    new_exp     = user["exp"]     + exp
    update_user(
        user["user_id"],
        balance=new_balance, exp=new_exp,
        last_daily_claim=now, daily_streak=streak,
    )
    user = {**user, "balance": new_balance, "exp": new_exp}
    user, level_msgs = auto_level_up(user)
    level_block = "".join(level_msgs)

    return True, (
        f"🎁 <b>Ежедневный бонус получен!</b>\n\n"
        f"🔥 Стрик: <b>{streak}</b> дн.\n"
        f"💰 Монеты: <b>+{coins}</b>\n"
        f"✨ Опыт: <b>+{exp}</b>"
        f"{level_block}"
    )

@dp.message(Command("daily"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("ежедневный", "бонус", "daily")))
async def cmd_daily(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    success, text = do_claim_daily(user)
    await message.answer(text)
    if success:
        updated = get_user(message.from_user.id)
        check_and_grant_achievements(updated)
        check_and_grant_titles(updated)

PET_GACHA_PRICE = 2000
PET_GACHA_PREMIUM_PRICE = 5000  # новая премиум гача

PETS = {
    "cat": {
        "name": "🐱 Котик", "rarity": "common", "rarity_label": "⚪ Обычный",
        "bonus_type": "coins", "bonus_label": "монеты с работы",
        "base_bonus": 3, "luck_bonus": 0,
        "description": "Мурлычет и приносит монетки.",
        "weight": 40, "weight_premium": 25,
    },
    "dog": {
        "name": "🐶 Пёсик", "rarity": "common", "rarity_label": "⚪ Обычный",
        "bonus_type": "coins", "bonus_label": "монеты с работы",
        "base_bonus": 3, "luck_bonus": 0,
        "description": "Верный друг, любит монеты.",
        "weight": 40, "weight_premium": 25,
    },
    "hamster": {
        "name": "🐹 Хомяк", "rarity": "common", "rarity_label": "⚪ Обычный",
        "bonus_type": "xp", "bonus_label": "опыт с работы",
        "base_bonus": 3, "luck_bonus": 0,
        "description": "Запасливый зверёк, копит опыт.",
        "weight": 35, "weight_premium": 20,
    },
    "rabbit": {
        "name": "🐰 Кролик", "rarity": "common", "rarity_label": "⚪ Обычный",
        "bonus_type": "luck", "bonus_label": "удача",
        "base_bonus": 2, "luck_bonus": 2,
        "description": "Приносит удачу на работе.",
        "weight": 30, "weight_premium": 18,
    },
    "fox": {
        "name": "🦊 Лисичка", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "xp", "bonus_label": "опыт с работы",
        "base_bonus": 5, "luck_bonus": 1,
        "description": "Хитрая и быстро учится.",
        "weight": 25, "weight_premium": 22,
    },
    "owl": {
        "name": "🦉 Сова", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "xp", "bonus_label": "опыт с работы",
        "base_bonus": 5, "luck_bonus": 1,
        "description": "Мудрая птица, даёт опыт.",
        "weight": 25, "weight_premium": 22,
    },
    "wolf": {
        "name": "🐺 Волк", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "coins", "bonus_label": "монеты с работы",
        "base_bonus": 6, "luck_bonus": 1,
        "description": "Хищник. Хорошо зарабатывает.",
        "weight": 20, "weight_premium": 18,
    },
    "panda": {
        "name": "🐼 Панда", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "luck", "bonus_label": "удача",
        "base_bonus": 4, "luck_bonus": 4,
        "description": "Спокойная и удачливая.",
        "weight": 18, "weight_premium": 16,
    },
    "parrot": {
        "name": "🦜 Попугай", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "both", "bonus_label": "монеты и опыт",
        "base_bonus": 4, "luck_bonus": 0,
        "description": "Болтун, но полезный.",
        "weight": 18, "weight_premium": 15,
    },
    "dragon": {
        "name": "🐉 Дракончик", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "coins", "bonus_label": "монеты с работы",
        "base_bonus": 10, "luck_bonus": 2,
        "description": "Огненный зверь, богатство само идёт.",
        "weight": 10, "weight_premium": 14,
    },
    "unicorn": {
        "name": "🦄 Единорог", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "xp", "bonus_label": "опыт с работы",
        "base_bonus": 10, "luck_bonus": 2,
        "description": "Магическое существо, опыт x бонус.",
        "weight": 10, "weight_premium": 14,
    },
    "tiger": {
        "name": "🐯 Тигр", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "both", "bonus_label": "монеты и опыт",
        "base_bonus": 8, "luck_bonus": 3,
        "description": "Мощный хищник. Всё по максимуму.",
        "weight": 8, "weight_premium": 12,
    },
    "snow_leopard": {
        "name": "🐆 Снежный барс", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "luck", "bonus_label": "удача",
        "base_bonus": 8, "luck_bonus": 8,
        "description": "Символ Кыргызстана. Удача зашкаливает.",
        "weight": 7, "weight_premium": 12,
    },
    "phoenix": {
        "name": "🔥 Феникс", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "bonus_label": "монеты И опыт",
        "base_bonus": 15, "luck_bonus": 5,
        "description": "Легендарная птица. Бонус ко всему.",
        "weight": 3, "weight_premium": 8,
    },
    "manul": {
        "name": "🐈 Манул", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "bonus_label": "монеты И опыт",
        "base_bonus": 15, "luck_bonus": 5,
        "description": "Редчайший степной кот. Приносит удачу.",
        "weight": 2, "weight_premium": 7,
    },
    "golden_dragon": {
        "name": "✨ Золотой дракон", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "bonus_label": "монеты И опыт",
        "base_bonus": 20, "luck_bonus": 10,
        "description": "Существо из легенд. Максимальный бонус.",
        "weight": 1, "weight_premium": 5,
    },
# ── Админские питомцы (не выпадают в гаче, только вручную) ──
    "rectors_ufo": {
        "name": "🛸 НЛО Ректора", "rarity": "admin", "rarity_label": "👑 Админский",
        "bonus_type": "both", "bonus_label": "монеты И опыт",
        "base_bonus": 30, "luck_bonus": 15,
        "description": "Секретный транспорт ректора. Выдаётся только администрацией.",
        "weight": 0, "weight_premium": 0,
        "admin_only": True,
    },
    "founder_spirit": {
        "name": "💀 Дух Основателя", "rarity": "admin", "rarity_label": "👑 Админский",
        "bonus_type": "coins", "bonus_label": "монеты с работы",
        "base_bonus": 35, "luck_bonus": 5,
        "description": "Дух того, кто заложил первый камень КТУ «Манас». Даётся вручную.",
        "weight": 0, "weight_premium": 0,
        "admin_only": True,
    },
    "cosmic_manul": {
        "name": "🌌 Космический Манул", "rarity": "admin", "rarity_label": "👑 Админский",
        "bonus_type": "xp", "bonus_label": "опыт с работы",
        "base_bonus": 35, "luck_bonus": 5,
        "description": "Манул, побывавший на орбите. Легенда среди легенд. Выдаётся только вручную.",
        "weight": 0, "weight_premium": 0,
        "admin_only": True,
    },
    "golden_scepter_beast": {
        "name": "🔱 Зверь Золотого Скипетра", "rarity": "admin", "rarity_label": "👑 Админский",
        "bonus_type": "both", "bonus_label": "монеты И опыт",
        "base_bonus": 40, "luck_bonus": 20,
        "description": "Абсолютный максимум силы. Реликвия, врученная лично администрацией.",
        "weight": 0, "weight_premium": 0,
        "admin_only": True,
    },
}


def gacha_pull(user: dict, premium: bool = False) -> tuple[str, dict, bool]:
    pet_keys = list(PETS.keys())
    if premium:
        weights = [p["weight_premium"] for p in PETS.values()]
    else:
        weights = [p["weight"] for p in PETS.values()]

    chosen_key = random.choices(pet_keys, weights=weights, k=1)[0]
    chosen_pet = PETS[chosen_key]

    # Загружаем коллекцию
    import json
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}

    is_duplicate = chosen_key in collection

    if is_duplicate:
        collection[chosen_key] = min(collection[chosen_key] + 1, 20)
    else:
        collection[chosen_key] = chosen_pet["base_bonus"]
        # Если нет активного пета — ставим этого
        if not user.get("active_pet"):
            update_user(user["user_id"], active_pet=chosen_key)

    update_user(user["user_id"], pet_collection=json.dumps(collection))
    return chosen_key, chosen_pet, is_duplicate


def get_pet_bonus(user: dict) -> tuple[int, int, int]:
    """Возвращает (bonus_coins_pct, bonus_xp_pct, bonus_luck)."""
    import json
    pet_id = user.get("active_pet", "") or user.get("pet_id", "")
    if not pet_id or pet_id not in PETS:
        return 0, 0, 0

    pet = PETS[pet_id]
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}

    bonus = collection.get(pet_id, pet["base_bonus"])
    luck_bonus = pet.get("luck_bonus", 0)

    if pet["bonus_type"] == "coins":
        return bonus, 0, luck_bonus
    elif pet["bonus_type"] == "xp":
        return 0, bonus, luck_bonus
    elif pet["bonus_type"] == "luck":
        return 0, 0, bonus + luck_bonus
    elif pet["bonus_type"] == "both":
        return bonus, bonus, luck_bonus
    return 0, 0, 0

def apply_pet_bonus(user: dict, coins: int, xp: int) -> tuple[int, int]:
    coin_pct, xp_pct, _ = get_pet_bonus(user)
    new_coins = int(coins * (1 + coin_pct / 100))
    new_xp    = int(xp    * (1 + xp_pct   / 100))
    return new_coins, new_xp

def get_marriage_bonus(user: dict) -> tuple[int, int]:
    """Возвращает (bonus_coins_pct, bonus_xp_pct) от брака.
    Базовый бонус +5%/+5%, удваивается если супруг(а) тоже недавно работал(а)."""
    spouse_id = user.get("spouse_id")
    if not spouse_id:
        return 0, 0
    base_coin, base_xp = 5, 5
    spouse = get_user(spouse_id)
    if spouse and (int(time.time()) - spouse.get("last_work_time", 0)) < 3600:
        return base_coin + 5, base_xp + 5
    return base_coin, base_xp


def get_equipped_item_bonus(user: dict) -> tuple[int, int, int]:
    key = user.get("equipped_boss_item", "")
    if not key or key not in BOSS_ITEMS:
        return 0, 0, 0
    item  = BOSS_ITEMS[key]
    items = get_boss_items(user)
    level = items.get(key, 1)
    bonus = item["base_bonus"] + (level - 1) * max(1, item["base_bonus"] // 4)  # рост за апгрейд

    if item["bonus_type"] == "coins":
        return bonus, 0, 0
    elif item["bonus_type"] == "xp":
        return 0, bonus, 0
    elif item["bonus_type"] == "luck":
        return 0, 0, bonus
    elif item["bonus_type"] == "both":
        return bonus, bonus, 0
    return 0, 0, 0


def get_rebirth_bonus(user: dict) -> tuple[int, int]:
    r = user.get("rebirths", 0)
    return r * REBIRTH_COIN_BONUS_PER, r * REBIRTH_XP_BONUS_PER


def get_combined_bonus(user: dict) -> tuple[int, int, int]:
    pet_coins, pet_xp, pet_luck = get_pet_bonus(user)
    title_coins, title_xp, title_luck = get_title_bonus(user)
    marriage_coins, marriage_xp = get_marriage_bonus(user)
    item_coins, item_xp, item_luck = get_equipped_item_bonus(user)
    rebirth_coins, rebirth_xp = get_rebirth_bonus(user)
    asc_coins = get_ascension_upgrade_bonus(user, "coin_boost")
    asc_xp    = get_ascension_upgrade_bonus(user, "xp_boost")
    asc_luck  = get_ascension_upgrade_bonus(user, "luck_boost")
    asc_item_coins, asc_item_xp, asc_item_luck = get_equipped_ascension_item_bonus(user)
    faculty_coins, faculty_xp, faculty_luck = get_faculty_bonus(user)
    return (
        pet_coins + title_coins + marriage_coins + item_coins + rebirth_coins + asc_coins + asc_item_coins + faculty_coins,
        pet_xp + title_xp + marriage_xp + item_xp + rebirth_xp + asc_xp + asc_item_xp + faculty_xp,
        pet_luck + title_luck + item_luck + asc_luck + asc_item_luck + faculty_luck,
    )


def apply_combined_coin_bonus(user: dict, amount: int) -> int:
    coin_pct, _, _ = get_combined_bonus(user)
    return int(amount * (1 + coin_pct / 100))


def apply_combined_xp_bonus(user: dict, amount: int) -> int:
    _, xp_pct, _ = get_combined_bonus(user)
    return int(amount * (1 + xp_pct / 100))


def apply_full_coin_bonus(user: dict, amount: int) -> int:
    """Комбинированный бонус (питомец+титул+брак) ПЛЮС множитель активного ивента."""
    amount = apply_combined_coin_bonus(user, amount)    # ← теперь вызывает переименованную базовую
    ev_coins_mult, _, _, _ = get_event_multipliers()
    return int(amount * ev_coins_mult)


def grant_achievement_now(user_id: int, key: str) -> str | None:
    """Немедленно выдаёт конкретное достижение (для событийных, не state-based, ачивок)."""
    user = get_user(user_id)
    if not user:
        return None
    owned = get_user_achievements(user)
    if key in owned or key not in ACHIEVEMENTS:
        return None
    owned.add(key)
    save_achievements(user_id, owned)
    a = ACHIEVEMENTS[key]
    new_balance = user["balance"] + a["reward_coins"]
    new_exp     = user["exp"]     + a["reward_exp"]
    update_user(user_id, balance=new_balance, exp=new_exp)
    return (
        f"🏅 <b>Новое достижение!</b> {a['name']}\n"
        f"<i>{a['description']}</i>\n"
        f"🎁 Награда: +{a['reward_coins']} монет, +{a['reward_exp']} XP"
    )


@dp.message(Command("gacha"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("гача", "питомец", "gacha", "петы")))
async def cmd_gacha(message: Message):
    import json
    uid = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    active_pet_id = user.get("active_pet", "") or user.get("pet_id", "")
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}

    lines = ["🎰 <b>Гача — питомцы</b>\n"]

    if active_pet_id and active_pet_id in PETS:
        pet = PETS[active_pet_id]
        bonus = collection.get(active_pet_id, pet["base_bonus"])
        _, _, luck_b = get_pet_bonus(user)
        lines.append(
            f"🐾 <b>Активный питомец:</b> {pet['name']} {pet['rarity_label']}\n"
            f"   Бонус: <b>+{bonus}%</b> к {pet['bonus_label']}"
            + (f" | 🍀 +{luck_b} удача" if luck_b > 0 else "") + "\n"
        )
    else:
        lines.append("🐾 У тебя пока нет питомца.\n")

    total_pets = len(collection)
    lines.append(f"📦 Коллекция: <b>{total_pets}</b> питомцев\n")
    lines.append("━━━ Обычная гача (2000 монет) ━━━")
    lines.append("⚪ Обычный: ~52% | 🔵 Редкий: ~35% | 🟣 Эпик: ~12% | 🟡 Леген: ~1%")
    lines.append("\n━━━ Премиум гача (5000 монет) ━━━")
    lines.append("⚪ Обычный: ~28% | 🔵 Редкий: ~36% | 🟣 Эпик: ~28% | 🟡 Леген: ~8%")
    lines.append("\n<i>Дубликат = бонус питомца +1% (макс +20%)</i>")

    builder = InlineKeyboardBuilder()
    builder.button(text="🎰 Обычная гача (2000 монет)", callback_data="gacha_pull:normal")
    builder.button(text="💎 Премиум гача (5000 монет)", callback_data="gacha_pull:premium")
    builder.button(text="📋 Моя коллекция", callback_data="gacha_collection")
    builder.button(text="🔄 Выбрать активного пета", callback_data="gacha_select_menu")
    builder.adjust(1)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("gacha_pull:"))
async def callback_gacha_pull(callback: CallbackQuery):
    import json
    uid = callback.from_user.id
    user = get_user_safe(uid)
    is_premium = callback.data.split(":")[1] == "premium"
    base_price = PET_GACHA_PREMIUM_PRICE if is_premium else PET_GACHA_PRICE
    _, _, _, ev_discount = get_event_multipliers()
    price = int(base_price * (1 - ev_discount / 100))

    if user["balance"] < price:
        await callback.answer(f"❌ Нужно {price} монет, есть {user['balance']}", show_alert=True)
        return

    update_user(uid, balance=user["balance"] - price)
    pet_key, pet, is_duplicate = gacha_pull(user, premium=is_premium)

    updated = get_user(uid)
    raw = updated.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}
    new_bonus = collection.get(pet_key, pet["base_bonus"])
    _, _, luck_b = get_pet_bonus(updated)

    gtype = "💎 Премиум" if is_premium else "🎰 Обычная"
    if is_duplicate:
        text = (
                f"{gtype} гача!\n\n"
                f"✨ Выпал: {pet['name']} {pet['rarity_label']}\n\n"
                f"🔄 <b>Дубликат!</b> Бонус вырос: <b>+{new_bonus}%</b> к {pet['bonus_label']}"
                + (f"\n🍀 Удача: +{luck_b}" if luck_b > 0 else "") +
                f"\n\n💰 Баланс: <b>{updated['balance']}</b> монет"
        )
    else:
        text = (
                f"{gtype} гача!\n\n"
                f"🎉 <b>НОВЫЙ ПИТОМЕЦ!</b>\n"
                f"{pet['name']} {pet['rarity_label']}\n"
                f"<i>{pet['description']}</i>\n\n"
                f"🎁 Бонус: <b>+{new_bonus}%</b> к {pet['bonus_label']}"
                + (f"\n🍀 Удача: +{luck_b}" if luck_b > 0 else "") +
                f"\n\n💰 Баланс: <b>{updated['balance']}</b> монет"
        )

    await callback.answer()
    await callback.message.answer(text)
    check_and_grant_achievements(updated)


@dp.callback_query(F.data == "gacha_collection")
async def callback_gacha_collection(callback: CallbackQuery):
    import json
    user = get_user_safe(callback.from_user.id)
    active_pet_id = user.get("active_pet", "") or user.get("pet_id", "")
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}

    if not collection:
        await callback.answer()
        await callback.message.answer("📦 Коллекция пуста. Крути гачу!")
        return

    lines = ["📦 <b>Твоя коллекция питомцев</b>\n"]
    for key, bonus in collection.items():
        if key not in PETS:
            continue
        pet = PETS[key]
        active_mark = " ◀ активный" if key == active_pet_id else ""
        luck_str = f" | 🍀 +{pet['luck_bonus']} удача" if pet.get("luck_bonus", 0) > 0 else ""
        lines.append(
            f"{'✅' if key == active_pet_id else '•'} {pet['name']} {pet['rarity_label']}{active_mark}\n"
            f"  +{bonus}% к {pet['bonus_label']}{luck_str}"
        )

    await callback.answer()
    await callback.message.answer("\n".join(lines))


@dp.callback_query(F.data == "gacha_select_menu")
async def callback_gacha_select_menu(callback: CallbackQuery):
    import json
    user = get_user_safe(callback.from_user.id)
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}

    if not collection:
        await callback.answer("У тебя нет питомцев!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for key in collection:
        if key not in PETS:
            continue
        pet = PETS[key]
        builder.button(text=f"{pet['name']} {pet['rarity_label']}", callback_data=f"gacha_setactive:{key}")
    builder.adjust(1)

    await callback.answer()
    await callback.message.answer("🔄 Выбери активного питомца:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("gacha_setactive:"))
async def callback_gacha_setactive(callback: CallbackQuery):
    pet_key = callback.data.split(":")[1]
    import json
    user = get_user_safe(callback.from_user.id)
    raw = user.get("pet_collection", "") or "{}"
    try:
        collection = json.loads(raw)
    except Exception:
        collection = {}

    if pet_key not in collection:
        await callback.answer("Этот питомец не в коллекции!", show_alert=True)
        return

    update_user(callback.from_user.id, active_pet=pet_key)
    pet = PETS[pet_key]
    await callback.answer(f"✅ Активный питомец: {pet['name']}!", show_alert=True)
# =====================================================================
# РЕПУТАЦИЯ
# =====================================================================
REP_MAX =  100
REP_MIN = -100

REP_TITLES = [
    (-100, -61, "😈 Изгой",          "Тебя все боятся и ненавидят."),
    ( -60, -31, "😤 Нарушитель",      "Репутация подмочена."),
    ( -30,  -1, "😐 Подозрительный",  "Люди смотрят косо."),
    (   0,   0, "😶 Никто",           "О тебе ещё не знают."),
    (   1,  30, "🙂 Знакомый",        "Тебя начинают замечать."),
    (  31,  60, "😊 Уважаемый",       "Тебя ценят в обществе."),
    (  61,  99, "🌟 Авторитет",       "Тебе доверяют все вокруг."),
    ( 100, 100, "👑 Легенда района",  "Имя знает весь Бишкек!"),
]

REP_SHOP_DISCOUNT = {
    # репутация >= X -> скидка Y%
    100: 20,
    61:  10,
    31:   5,
    0:    0,
    -30: -5,   # наценка
    -60: -10,
    -100:-20,
}

def get_rep_title(rep: int) -> tuple[str, str]:
    for low, high, title, desc in REP_TITLES:
        if low <= rep <= high:
            return title, desc
    return "😶 Никто", ""

def get_rep_discount(rep: int) -> int:
    """Возвращает % скидки (может быть отрицательным = наценка)."""
    discount = 0
    for threshold, value in sorted(REP_SHOP_DISCOUNT.items(), reverse=True):
        if rep >= threshold:
            discount = value
            break
    return discount

def bump_stat(user_id: int, field: str, amount: int = 1):
    user = get_user(user_id)
    if not user:
        return
    update_user(user_id, **{field: user.get(field, 0) + amount})

def change_reputation(user_id: int, amount: int) -> tuple[int, int]:
    user = get_user(user_id)
    if not user:
        return 0, 0
    old_rep = user.get("reputation", 0)

    if amount > 0:
        # Чем ближе к 100 — тем меньше реальный прирост.
        # У -100 репы прирост полный (x1.0), у +100 — почти нулевой (x0.15)
        progress   = (old_rep - REP_MIN) / (REP_MAX - REP_MIN)  # 0..1
        gain_mult  = max(0.15, 1 - progress)
        amount     = max(1, round(amount * gain_mult))
    else:
        # Чем выше репутация — тем сильнее она проседает при проступке.
        # На 100 репе потеря x2, на 0 и ниже — обычная.
        loss_progress = max(0.0, old_rep) / REP_MAX if REP_MAX else 0
        loss_mult     = 1 + loss_progress
        amount        = -max(1, round(abs(amount) * loss_mult))

    new_rep = max(REP_MIN, min(REP_MAX, old_rep + amount))
    update_user(user_id, reputation=new_rep)
    return old_rep, new_rep

def apply_rep_to_price(user: dict, price: int) -> int:
    """Применяет скидку/наценку от репутации к цене."""
    rep      = user.get("reputation", 0)
    discount = get_rep_discount(rep)
    return max(1, int(price * (1 - discount / 100)))

@dp.message(Command("reputation"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("репутация", "rep")))
async def cmd_reputation(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)
    rep  = user.get("reputation", 0)

    title, desc = get_rep_title(rep)
    discount    = get_rep_discount(rep)

    # Визуальная шкала
    filled = int((rep - REP_MIN) / (REP_MAX - REP_MIN) * 20)
    bar    = "█" * filled + "░" * (20 - filled)

    if discount > 0:
        discount_text = f"🏷 Скидка в магазине: <b>-{discount}%</b>"
    elif discount < 0:
        discount_text = f"💸 Наценка в магазине: <b>+{abs(discount)}%</b>"
    else:
        discount_text = "🏷 Скидка в магазине: нет"

    await message.answer(
        f"⭐ <b>Репутация</b>\n\n"
        f"Статус: <b>{title}</b>\n"
        f"<i>{desc}</i>\n\n"
        f"[{bar}]\n"
        f"Очки: <b>{rep}</b> / {REP_MAX}\n\n"
        f"{discount_text}\n\n"
       f"━━━ Как меняется репутация ━━━\n"
        f"✅ Позитивное событие на работе: +1\n"
        f"✅ Победа в дуэли: +2 | в кости: +1\n"
        f"✅ Победа на бирже/боссе/квесте: +1\n"
        f"❌ Негативное событие на работе: -3\n"
        f"❌ Поражение в дуэли: -4 | в кости: -3\n"
        f"❌ Проигрыш на бирже/в казино: -2\n\n"
        f"<i>⚠️ Чем ближе к 100 — тем слабее прирост.\n"
        f"⚠️ Чем выше репутация — тем больнее падение при неудаче.</i>"
    )
@dp.message(Command("titles"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("титулы", "титул")))
async def cmd_titles(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    title_msgs = check_and_grant_titles(user)
    for m in title_msgs:
        await message.answer(m)
    user = get_user(uid)

    owned  = get_user_titles(user)
    active = user.get("active_title", "")

    lines = ["🎖 <b>Титулы</b>\n"]
    if not owned:
        lines.append("У тебя пока нет титулов. Достигай уникальных целей!")
    else:
        for key in owned:
            t = TITLES.get(key)
            if not t:
                continue
            mark = " ◀ активный" if key == active else ""
            bonus_parts = []
            if t["bonus_coins"]: bonus_parts.append(f"+{t['bonus_coins']}% монет")
            if t["bonus_xp"]:    bonus_parts.append(f"+{t['bonus_xp']}% опыта")
            if t["bonus_luck"]:  bonus_parts.append(f"+{t['bonus_luck']} удачи")
            lines.append(
                f"{'✅' if key == active else '•'} <b>{t['name']}</b>{mark}\n"
                f"   {', '.join(bonus_parts)}\n"
                f"   <i>{t['description']}</i>"
            )

    builder = InlineKeyboardBuilder()
    for key in owned:
        if key in TITLES:
            builder.button(text=TITLES[key]["name"], callback_data=f"title_set:{key}")
    if active:
        builder.button(text="🚫 Снять титул", callback_data="title_unset")
    builder.adjust(1)

    await message.answer("\n\n".join(lines), reply_markup=builder.as_markup() if owned else None)


@dp.callback_query(F.data.startswith("title_set:"))
async def callback_title_set(callback: CallbackQuery):
    key  = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    owned = get_user_titles(user)
    if key not in owned or key not in TITLES:
        await callback.answer("Титул недоступен.", show_alert=True)
        return
    update_user(callback.from_user.id, active_title=key)
    await callback.answer(f"✅ Активный титул: {TITLES[key]['name']}!", show_alert=True)


@dp.callback_query(F.data == "title_unset")
async def callback_title_unset(callback: CallbackQuery):
    update_user(callback.from_user.id, active_title="")
    await callback.answer("Титул снят.", show_alert=True)

@dp.message(Command("stats"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("статистика", "stats")))
async def cmd_stats(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)

    duel_total = user.get("stat_duel_wins", 0) + user.get("stat_duel_losses", 0)
    duel_wr = int(user.get("stat_duel_wins", 0) / duel_total * 100) if duel_total else 0

    dice_total = user.get("stat_dice_wins", 0) + user.get("stat_dice_losses", 0)
    dice_wr = int(user.get("stat_dice_wins", 0) / dice_total * 100) if dice_total else 0

    bj_total = user.get("stat_blackjack_wins", 0) + user.get("stat_blackjack_losses", 0)
    bj_wr = int(user.get("stat_blackjack_wins", 0) / bj_total * 100) if bj_total else 0

    stock_total = user.get("stat_stock_wins", 0) + user.get("stat_stock_losses", 0)
    stock_wr = int(user.get("stat_stock_wins", 0) / stock_total * 100) if stock_total else 0

    await message.answer(
        f"📊 <b>Статистика</b> {message.from_user.mention_html()}\n\n"
        f"🛠 Смен отработано: <b>{user.get('stat_work_count', 0)}</b>\n\n"
        f"⚔️ Дуэли: <b>{user.get('stat_duel_wins', 0)}</b>В / <b>{user.get('stat_duel_losses', 0)}</b>П "
        f"({duel_wr}% побед)\n"
        f"🎲 Кости: <b>{user.get('stat_dice_wins', 0)}</b>В / <b>{user.get('stat_dice_losses', 0)}</b>П "
        f"({dice_wr}% побед)\n"
        f"🃏 Покер — побед: <b>{user.get('stat_poker_wins', 0)}</b>\n"
        f"🂡 Блекджек: <b>{user.get('stat_blackjack_wins', 0)}</b>В / "
        f"<b>{user.get('stat_blackjack_losses', 0)}</b>П ({bj_wr}% побед)\n"
        f"🎰 Слотов сыграно: <b>{user.get('stat_slots_played', 0)}</b>\n"
        f"📈 Биржа: <b>{user.get('stat_stock_wins', 0)}</b>В / "
        f"<b>{user.get('stat_stock_losses', 0)}</b>П ({stock_wr}% побед)\n\n"
        f"🔥 Стрик ежедневного бонуса: <b>{user.get('daily_streak', 0)}</b> дн.\n"
        f"🏠 Бизнесов: <b>{len(get_user_properties(user))}</b> "
        f"({get_total_income_per_hour(user)}/ч пассивного дохода)"
    )
# =====================================================================
# КОСТИ (ДАЙСЫ)
# =====================================================================
active_dice: dict[int, dict] = {}  # chat_id -> dice data

@dp.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.func(lambda t: t and t.strip().lower().startswith("кости "))
)
async def dice_challenge(message: Message):
    chat_id      = message.chat.id
    challenger_id   = message.from_user.id
    challenger_name = message.from_user.full_name

    if chat_id in active_dice:
        await message.answer("🎲 В этом чате уже идёт игра в кости!")
        return

    parts = message.text.strip().split()
    bet   = None
    for p in reversed(parts):
        if p.isdigit():
            bet = int(p)
            break

    if not bet or bet <= 0:
        await message.answer("❌ Укажи ставку: <code>кости @username 500</code>")
        return

    target_id   = None
    target_name = None

    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        if not ru.is_bot:
            target_id   = ru.id
            target_name = ru.full_name
    else:
        if message.entities:
            for ent in message.entities:
                if ent.type == "text_mention" and ent.user:
                    target_id   = ent.user.id
                    target_name = ent.user.full_name
                    break
                elif ent.type == "mention":
                    uname = message.text[ent.offset:ent.offset + ent.length]
                    try:
                        cm = await bot.get_chat_member(chat_id, uname)
                        target_id   = cm.user.id
                        target_name = cm.user.full_name
                    except Exception:
                        pass
                    break

    if not target_id:
        await message.answer("❌ Укажи игрока: <code>кости @username 500</code>")
        return
    if target_id == challenger_id:
        await message.answer("❌ Нельзя играть с самим собой!")
        return

    challenger = get_user_safe(challenger_id)
    if challenger["balance"] < bet:
        await message.answer(f"❌ Недостаточно монет! Нужно {bet}, есть {challenger['balance']}")
        return

    register_user(target_id)
    target = get_user(target_id)
    if not target or target["balance"] < bet:
        await message.answer(f"❌ У {target_name} недостаточно монет.")
        return

    active_dice[chat_id] = {
        "challenger_id":   challenger_id,
        "challenger_name": challenger_name,
        "target_id":       target_id,
        "target_name":     target_name,
        "bet":             bet,
        "accepted":        False,
    }

    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 Принять", callback_data=f"dice_accept:{chat_id}:{target_id}")
    builder.button(text="🏳️ Отказ",  callback_data=f"dice_decline:{chat_id}:{target_id}")
    builder.adjust(2)

    await message.answer(
        f"🎲 <b>ВЫЗОВ НА КОСТИ!</b>\n\n"
        f"🎯 {challenger_name} вызывает {target_name}\n"
        f"💰 Ставка: <b>{bet}</b> монет\n\n"
        f"Бросаем по 2 кубика — у кого сумма больше, тот выиграл!\n\n"
        f"<a href='tg://user?id={target_id}'>{target_name}</a>, принимаешь?",
        reply_markup=builder.as_markup()
    )

    async def auto_cancel():
        await asyncio.sleep(60)
        if chat_id in active_dice and not active_dice[chat_id]["accepted"]:
            del active_dice[chat_id]
            await bot.send_message(chat_id, f"⏰ {target_name} не ответил. Игра отменена.")
    asyncio.create_task(auto_cancel())


@dp.callback_query(F.data.startswith("dice_accept:"))
async def dice_accept(callback: CallbackQuery):
    parts   = callback.data.split(":")
    chat_id = int(parts[1])
    tid     = int(parts[2])

    if callback.from_user.id != tid:
        await callback.answer("Это не твой вызов!", show_alert=True)
        return

    dice = active_dice.get(chat_id)
    if not dice:
        await callback.answer("Игра уже недействительна.", show_alert=True)
        return

    dice["accepted"] = True
    await callback.answer()

    c_id   = dice["challenger_id"]
    c_name = dice["challenger_name"]
    t_id   = dice["target_id"]
    t_name = dice["target_name"]
    bet    = dice["bet"]

    challenger = get_user(c_id)
    target     = get_user(t_id)

    if challenger["balance"] < bet or target["balance"] < bet:
        del active_dice[chat_id]
        await bot.send_message(chat_id,"❌ У одного из игроков не хватает монет. Игра отменена.")
        return

    # Бросаем кубики
    c_dice = [random.randint(1, 6), random.randint(1, 6)]
    t_dice = [random.randint(1, 6), random.randint(1, 6)]
    c_sum  = sum(c_dice)
    t_sum  = sum(t_dice)

    await bot.send_message(chat_id,
        f"🎲 <b>БРОСАЕМ КОСТИ!</b>\n\n"
        f"🎯 {c_name}: [{c_dice[0]}] + [{c_dice[1]}] = <b>{c_sum}</b>\n"
        f"🎯 {t_name}: [{t_dice[0]}] + [{t_dice[1]}] = <b>{t_sum}</b>"
    )

    await asyncio.sleep(2)

    del active_dice[chat_id]

    if c_sum == t_sum:
        await bot.send_message(chat_id,
            f"🤝 <b>НИЧЬЯ!</b> Оба выбросили {c_sum}.\n"
            f"Монеты остаются у каждого."
        )
        return

    if c_sum > t_sum:
        winner_id, winner_name = c_id, c_name
        loser_id, loser_name = t_id, t_name
        winner_bal = challenger["balance"]
        loser_bal = target["balance"]
        winner_user = challenger
    else:
        winner_id, winner_name = t_id, t_name
        loser_id, loser_name = c_id, c_name
        winner_bal = target["balance"]
        loser_bal = challenger["balance"]
        winner_user = target

    bonus_win = apply_full_coin_bonus(winner_user, bet)
    new_winner_bal = winner_bal + bonus_win
    new_loser_bal = max(0, loser_bal - bet)
    update_user(winner_id, balance=new_winner_bal)
    update_user(loser_id, balance=new_loser_bal)

    change_reputation(winner_id, +1)
    change_reputation(loser_id, -2)
    bump_stat(winner_id, "stat_dice_wins")
    bump_stat(loser_id, "stat_dice_losses")

    bonus_line = f" (🐾 бонус: +{bonus_win - bet})" if bonus_win > bet else ""
    await bot.send_message(chat_id,
                           f"🏆 <b>ПОБЕДИТЕЛЬ — {winner_name}!</b>\n\n"
                           f"💰 +{bonus_win} монет{bonus_line} → баланс: {new_winner_bal}\n"
                           f"💸 -{bet} монет → баланс: {new_loser_bal}"
                           )

@dp.callback_query(F.data.startswith("dice_decline:"))
async def dice_decline(callback: CallbackQuery):
    parts   = callback.data.split(":")
    chat_id = int(parts[1])
    tid     = int(parts[2])

    if callback.from_user.id != tid:
        await callback.answer("Это не твой вызов!", show_alert=True)
        return

    dice = active_dice.get(chat_id)
    if not dice:
        await callback.answer()
        return

    del active_dice[chat_id]
    await callback.answer()
    await bot.send_message(chat_id,
        f"🏳️ <b>{dice['target_name']}</b> отказался. Трус! 🐔"
    )


# =====================================================================
# СЛОТЫ
# =====================================================================
SLOT_SYMBOLS = ["🍋", "🍊", "🍇", "🍒", "⭐", "💎", "7️⃣"]
SLOT_WEIGHTS  = [30,   25,   20,   15,   6,    3,    1  ]

SLOT_PAYOUTS = {
    # три одинаковых
    "🍋🍋🍋": 2,
    "🍊🍊🍊": 2,
    "🍇🍇🍇": 3,
    "🍒🍒🍒": 3,
    "⭐⭐⭐": 5,
    "💎💎💎": 10,
    "7️⃣7️⃣7️⃣": 20,
    # два одинаковых
    "два": 0,   # возврат ставки
}

SLOT_MIN_BET = 50

@dp.message(F.text.func(lambda t: t and t.strip().lower().startswith("слоты ")))
async def cmd_slots(message: Message):
    uid  = message.from_user.id
    user = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ Формат: <code>слоты 200</code>")
        return

    bet = int(parts[1])
    if bet < SLOT_MIN_BET:
        await message.answer(f"❌ Минимальная ставка: <b>{SLOT_MIN_BET}</b> монет.")
        return
    if user["balance"] < bet:
        await message.answer(
            f"❌ Недостаточно монет.\n"
            f"Ставка: <b>{bet}</b> | Баланс: <b>{user['balance']}</b>"
        )
        return

    # Крутим барабаны
    reels = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    combo = "".join(reels)

    # Определяем выигрыш
    multiplier = 0
    result_text = ""

    if reels[0] == reels[1] == reels[2]:
        multiplier  = SLOT_PAYOUTS.get(combo, 2)
        result_text = f"🎉 <b>ТРИ ОДИНАКОВЫХ!</b> x{multiplier}"
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        multiplier  = 1  # возврат ставки
        result_text = "😐 <b>Два одинаковых — возврат ставки.</b>"
    else:
        multiplier  = 0
        result_text = "😢 <b>Мимо! Ничего не совпало.</b>"

    winnings = bet * multiplier
    profit_raw = winnings - bet
    if profit_raw > 0:
        profit = apply_full_coin_bonus(user, profit_raw)
        winnings = bet + profit
    else:
        profit = profit_raw
    new_balance = user["balance"] - bet + winnings
    update_user(uid, balance=new_balance)
    bump_stat(uid, "stat_slots_played")

    if profit > 0:
        change_reputation(uid, +1)
        money_line = f"💰 Выигрыш: <b>+{profit}</b> монет"
    elif profit == 0:
        money_line = "💰 Ставка возвращена."
    else:
        change_reputation(uid, -1)
        money_line = f"💸 Потеря: <b>{bet}</b> монет"

    mention = message.from_user.mention_html()

    await message.answer(
        f"🎰 <b>СЛОТЫ</b> — {mention}\n\n"
        f"┌─────────────┐\n"
        f"│  {reels[0]}  {reels[1]}  {reels[2]}  │\n"
        f"└─────────────┘\n\n"
        f"{result_text}\n"
        f"{money_line}\n"
        f"📊 Баланс: <b>{new_balance}</b> монет"
    )

    update_quest_progress(uid, "slots")
    check_and_grant_achievements(get_user(uid))

# =====================================================================
# ФАКУЛЬТЕТЫ (кланы)
# =====================================================================
FACULTIES = {
    "it": {
        "name": "🧑‍💻 Факультет ИТ",
        "bonus_type": "coins", "base_bonus": 5, "per_level": 2,
        "description": "Айтишники подрабатывают фрилансом. Бонус к монетам с работы.",
    },
    "ff": {
        "name": "🗣 Факультет Филологии (ФФ)",
        "bonus_type": "xp", "base_bonus": 5, "per_level": 2,
        "description": "Учат языки быстрее всех. Бонус к опыту с работы.",
    },
    "fgie": {
        "name": "💼 ФГиЭ (Гуманитарные и Экономические науки)",
        "bonus_type": "luck", "base_bonus": 5, "per_level": 1,
        "description": "Умеют предсказывать рынок. Бонус к удаче.",
    },
    "eng": {
        "name": "⚙️ Инженерный факультет",
        "bonus_type": "xp", "base_bonus": 5, "per_level": 2,
        "description": "Много практики — быстрая прокачка. Бонус к опыту с работы.",
    },
    "med": {
        "name": "⚕️ Медицинский факультет",
        "bonus_type": "coins", "base_bonus": 5, "per_level": 2,
        "description": "Подрабатывают в клиниках. Бонус к монетам с работы.",
    },
    "fk": {
        "name": "🗣 Факультет Коммуникации (ФК)",
        "bonus_type": "xp", "base_bonus": 5, "per_level": 2,
        "description": "Снимают по всему Манасу ролики. Бонус к опыту с работы.",
    },
    "Dis": {
        "name": "🧑‍🎨 Факультет Искусств",
        "bonus_type": "coins", "base_bonus": 5, "per_level": 2,
        "description": "Вы рисуете на улицах портреты. Бонус к монетам с работы.",
    },
}

FACULTY_LEVEL_THRESHOLDS = [0, 3000, 10000, 30000, 80000, 200000, 500000]
FACULTY_SWITCH_COST = 3000


def get_faculty_level(points: int) -> int:
    level = 0
    for i, threshold in enumerate(FACULTY_LEVEL_THRESHOLDS):
        if points >= threshold:
            level = i
    return level


def ensure_faculty_rows():
    with get_conn() as conn:
        with conn.cursor() as cur:
            for key in FACULTIES:
                cur.execute(
                    "INSERT INTO faculties (faculty_key, points) VALUES (%s, 0) "
                    "ON CONFLICT (faculty_key) DO NOTHING", (key,)
                )
            conn.commit()


def get_faculty_points(faculty_key: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT points FROM faculties WHERE faculty_key = %s", (faculty_key,))
            row = cur.fetchone()
    return row[0] if row else 0


def add_faculty_points(faculty_key: str, amount: int):
    if not faculty_key or faculty_key not in FACULTIES or amount <= 0:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO faculties (faculty_key, points) VALUES (%s, %s) "
                "ON CONFLICT (faculty_key) DO UPDATE SET points = faculties.points + EXCLUDED.points",
                (faculty_key, amount)
            )
            conn.commit()


def contribute_faculty_points(user_id: int, amount: int):
    user = get_user(user_id)
    if user and user.get("faculty"):
        add_faculty_points(user["faculty"], amount)


def get_faculty_bonus(user: dict) -> tuple[int, int, int]:
    """Возвращает (coins_pct, xp_pct, luck) от факультета пользователя."""
    cfg = FACULTIES.get(user.get("faculty", "") or "")
    if not cfg:
        return 0, 0, 0
    level = get_faculty_level(get_faculty_points(user["faculty"]))
    bonus = cfg["base_bonus"] + level * cfg["per_level"]
    if cfg["bonus_type"] == "coins":
        return bonus, 0, 0
    elif cfg["bonus_type"] == "xp":
        return 0, bonus, 0
    return 0, 0, bonus


def build_faculty_text(user: dict) -> str:
    fkey = user.get("faculty", "")
    label_map = {"coins": "монеты с работы", "xp": "опыт с работы", "luck": "удача"}

    if not fkey or fkey not in FACULTIES:
        lines = ["🏛 <b>Факультеты КТУ «Манас»</b>\n",
                  "Выбери факультет — постоянный бонус, растущий вместе со всеми участниками!\n"]
        for key, cfg in FACULTIES.items():
            points = get_faculty_points(key)
            level = get_faculty_level(points)
            bonus = cfg["base_bonus"] + level * cfg["per_level"]
            lines.append(
                f"<b>{cfg['name']}</b> — ур. {level} ({points} очков)\n"
                f"  <i>{cfg['description']}</i>\n"
                f"  Текущий бонус: +{bonus} к {label_map[cfg['bonus_type']]}"
            )
        return "\n\n".join(lines)

    cfg = FACULTIES[fkey]
    points = get_faculty_points(fkey)
    level = get_faculty_level(points)
    bonus = cfg["base_bonus"] + level * cfg["per_level"]
    next_threshold = next((t for t in FACULTY_LEVEL_THRESHOLDS if t > points), None)
    next_line = f"\nДо след. уровня: {next_threshold - points} очков" if next_threshold else "\nМаксимальный уровень факультета!"
    return (
        f"🏛 <b>Твой факультет</b>\n\n<b>{cfg['name']}</b>\n<i>{cfg['description']}</i>\n\n"
        f"📊 Уровень: <b>{level}</b>\n⭐ Очков: <b>{points}</b>{next_line}\n\n"
        f"🎁 Твой бонус: <b>+{bonus}</b> к {label_map[cfg['bonus_type']]}\n\n"
        f"<i>Работай, добывай ресурсы и побеждай боссов — это приносит очки факультету!</i>"
    )


def get_faculty_keyboard(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fkey = user.get("faculty", "")
    for key, cfg in FACULTIES.items():
        if key == fkey:
            continue
        label = "Сменить на" if fkey else "Вступить:"
        builder.button(text=f"{label} {cfg['name']}", callback_data=f"faculty_join:{key}")
    builder.button(text="🏆 Топ факультетов", callback_data="faculty_top")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(Command("faculty"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("факультет", "факультеты", "клан")))
async def cmd_faculty(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_faculty_text(user), reply_markup=get_faculty_keyboard(user))


@dp.callback_query(F.data.startswith("faculty_join:"))
async def cb_faculty_join(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    if key not in FACULTIES:
        await callback.answer("❌ Такого факультета нет.", show_alert=True)
        return
    user = get_user_safe(callback.from_user.id)
    current = user.get("faculty", "")
    if current == key:
        await callback.answer("Ты уже здесь состоишь!", show_alert=True)
        return
    if current:
        if user["balance"] < FACULTY_SWITCH_COST:
            await callback.answer(f"❌ Смена факультета стоит {FACULTY_SWITCH_COST} монет.", show_alert=True)
            return
        update_user(callback.from_user.id, balance=user["balance"] - FACULTY_SWITCH_COST, faculty=key)
        await callback.answer(f"✅ Ты перешёл на {FACULTIES[key]['name']}! (-{FACULTY_SWITCH_COST} монет)", show_alert=True)
    else:
        update_user(callback.from_user.id, faculty=key)
        await callback.answer(f"✅ Добро пожаловать на {FACULTIES[key]['name']}!", show_alert=True)
    updated = get_user(callback.from_user.id)
    await callback.message.edit_text(build_faculty_text(updated), reply_markup=get_faculty_keyboard(updated))


@dp.callback_query(F.data == "faculty_top")
async def cb_faculty_top(callback: CallbackQuery):
    rows = [(key, cfg, get_faculty_points(key)) for key, cfg in FACULTIES.items()]
    rows.sort(key=lambda x: -x[2])
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Топ факультетов</b>\n"]
    for i, (key, cfg, points) in enumerate(rows, 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        lines.append(f"{medal} <b>{cfg['name']}</b> — ур. {get_faculty_level(points)} ({points} очков)")
    await callback.answer()
    await callback.message.answer("\n".join(lines))

# =====================================================================
# СИСТЕМА ИВЕНТОВ
# =====================================================================
EVENTS = {
    "double_xp": {
        "name":        "⚡ Двойной опыт",
        "description": "Весь опыт с работы x2!",
        "duration_hours": 24,
        "multiplier_xp":    2.0,
        "multiplier_coins": 1.0,
        "lucky_boost":      0,
        "shop_discount":    0,
        "emoji":       "⚡",
    },
    "double_coins": {
        "name":        "💰 Золотая лихорадка",
        "description": "Все монеты с работы x2!",
        "duration_hours": 12,
        "multiplier_xp":    1.0,
        "multiplier_coins": 2.0,
        "lucky_boost":      0,
        "shop_discount":    0,
        "emoji":       "💰",
    },
    "lucky_hour": {
        "name":        "🍀 Час удачи",
        "description": "Шанс позитивного события на работе 80%!",
        "duration_hours": 2,
        "multiplier_xp":    1.0,
        "multiplier_coins": 1.0,
        "lucky_boost":      80,
        "shop_discount":    0,
        "emoji":       "🍀",
    },
    "discount": {
        "name":        "🛒 Распродажа",
        "description": "Все товары в магазине -30%!",
        "duration_hours": 6,
        "multiplier_xp":    1.0,
        "multiplier_coins": 1.0,
        "lucky_boost":      0,
        "shop_discount":    30,
        "emoji":       "🛒",
    },
    "exam_week": {
        "name":        "📝 Сессия в Манасе",
        "description": "Опыт x3 но монеты x0.5! Тяжёлые времена.",
        "duration_hours": 48,
        "multiplier_xp":    3.0,
        "multiplier_coins": 0.5,
        "lucky_boost":      0,
        "shop_discount":    0,
        "emoji":       "📝",
    },
    "golden_weekend": {
        "name":        "🌟 Золотые выходные",
        "description": "Монеты x2 И опыт x2 весь уикенд!",
        "duration_hours": 48,
        "multiplier_xp":    2.0,
        "multiplier_coins": 2.0,
        "lucky_boost":      0,
        "shop_discount":    0,
        "emoji":       "🌟",
    },
    "manasday": {
        "name":        "🏫 День КТУ Манас",
        "description": "Праздник! Скидка 50% в магазине и удача x2!",
        "duration_hours": 24,
        "multiplier_xp":    1.5,
        "multiplier_coins": 1.5,
        "lucky_boost":      50,
        "shop_discount":    50,
        "emoji":       "🏫",
    },
"resource_rush": {
        "name": "🌲 Изобилие природы",
        "description": "Добыча ресурсов на охоте/рыбалке/в шахте x2!",
        "duration_hours": 12,
        "multiplier_xp": 1.0, "multiplier_coins": 1.0,
        "lucky_boost": 0, "shop_discount": 0,
        "gather_multiplier": 2.0,   # новое поле — множитель добычи
        "emoji": "🌲",
    },
    "energy_refill": {
        "name": "🔋 Заряд бодрости",
        "description": "Стоимость энергии на все действия -30%! (Учитывай ощутимо)",
        "duration_hours": 6,
        "multiplier_xp": 1.0, "multiplier_coins": 1.0,
        "lucky_boost": 0, "shop_discount": 0,
        "energy_discount": 30,      # новое поле
        "emoji": "🔋",
    },
    "boss_rage": {
        "name": "👹 Ярость боссов",
        "description": "Награда с любых боссов (шахтёрских/охотничьих/классических) +50%!",
        "duration_hours": 12,
        "multiplier_xp": 1.0, "multiplier_coins": 1.0,
        "lucky_boost": 0, "shop_discount": 0,
        "boss_reward_bonus": 50,    # новое поле
        "emoji": "👹",
    },
    "mega_sale": {
        "name": "🏷 Мега-распродажа",
        "description": "Скидка 50% в магазине и на крафт инструментов!",
        "duration_hours": 8,
        "multiplier_xp": 1.0, "multiplier_coins": 1.0,
        "lucky_boost": 0, "shop_discount": 50,
        "emoji": "🏷",
    },
    "triple_xp_weekend": {
        "name": "📚 Тройной опыт",
        "description": "Весь опыт с работы x3! Только по выходным.",
        "duration_hours": 24,
        "multiplier_xp": 3.0, "multiplier_coins": 1.0,
        "lucky_boost": 0, "shop_discount": 0,
        "emoji": "📚",
    },
    "duel_frenzy": {
        "name": "⚔️ Час дуэлей",
        "description": "Победители дуэлей/костей получают награду x1.5!",
        "duration_hours": 4,
        "multiplier_xp": 1.0, "multiplier_coins": 1.0,
        "lucky_boost": 0, "shop_discount": 0,
        "duel_reward_bonus": 50,    # новое поле
        "emoji": "⚔️",
    },
    "cosmic_luck": {
        "name": "🌌 Космическая удача",
        "description": "Удача +15 ко всем броскам на время ивента!",
        "duration_hours": 6,
        "multiplier_xp": 1.0, "multiplier_coins": 1.0,
        "lucky_boost": 30, "shop_discount": 0,
        "global_luck_bonus": 15,    # новое поле
        "emoji": "🌌",
    },
    "mega_coins_10x": {
        "name":        "💥 МЕГА Золотая лихорадка x10",
        "description": "Все монеты с работы x10! Событие для избранных.",
        "duration_hours": 3,
        "multiplier_xp":    1.0,
        "multiplier_coins": 10.0,
        "lucky_boost":      0,
        "shop_discount":    0,
        "emoji":       "💥",
    },
    "mega_xp_10x": {
        "name":        "💥 МЕГА Прорыв опыта x10",
        "description": "Весь опыт с работы x10!",
        "duration_hours": 3,
        "multiplier_xp":    10.0,
        "multiplier_coins": 1.0,
        "lucky_boost":      0,
        "shop_discount":    0,
        "emoji":       "💥",
    },
    "mega_both_10x": {
        "name":        "🌋 АБСОЛЮТНЫЙ ИВЕНТ x10",
        "description": "Монеты И опыт x10 одновременно! Легендарное событие.",
        "duration_hours": 2,
        "multiplier_xp":    10.0,
        "multiplier_coins": 10.0,
        "lucky_boost":      25,
        "shop_discount":    0,
        "emoji":       "🌋",
    },
}

# Хранилище активного ивента в памяти
current_event: dict | None = None
registered_chats: set[int] = set()


def load_chats_from_db():
    """Загружает список чатов из БД."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM event_chats")
                rows = cur.fetchall()
                for row in rows:
                    registered_chats.add(row[0])
    except Exception:
        pass


def save_chat(chat_id: int):
    """Сохраняет chat_id в БД."""
    registered_chats.add(chat_id)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO event_chats (chat_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (chat_id,)
                )
                conn.commit()
    except Exception:
        pass


def get_active_event() -> dict | None:
    """Возвращает активный ивент если он ещё не закончился."""
    global current_event
    if not current_event:
        return None
    if int(time.time()) > current_event["ends_at"]:
        current_event = None
        return None
    return current_event


def start_event(event_key: str) -> dict | None:
    global current_event
    event = EVENTS.get(event_key)
    if not event:
        return None
    now      = int(time.time())
    ends_at  = now + event["duration_hours"] * 3600
    current_event = {
        "key":      event_key,
        "data":     event,
        "started_at": now,
        "ends_at":  ends_at,
    }
    return current_event

def get_event_extra() -> dict:
    ev = get_active_event()
    if not ev:
        return {}
    d = ev["data"]
    return {
        "gather_multiplier": d.get("gather_multiplier", 1.0),
        "energy_discount":   d.get("energy_discount", 0),
        "boss_reward_bonus": d.get("boss_reward_bonus", 0),
        "duel_reward_bonus": d.get("duel_reward_bonus", 0),
        "global_luck_bonus": d.get("global_luck_bonus", 0),
    }

def apply_energy_discount(cost: int) -> int:
    discount = get_event_extra().get("energy_discount", 0)
    return max(1, int(cost * (1 - discount / 100)))

def get_event_multipliers() -> tuple[float, float, int, int]:
    """Возвращает (coins_mult, xp_mult, lucky_boost, shop_discount)."""
    ev = get_active_event()
    if not ev:
        return 1.0, 1.0, 0, 0
    d = ev["data"]
    return (
        d["multiplier_coins"],
        d["multiplier_xp"],
        d["lucky_boost"],
        d["shop_discount"],
    )


async def broadcast_event_start(event_key: str):
    """Рассылает объявление об ивенте всем чатам и пользователям."""
    ev   = get_active_event()
    if not ev:
        return
    data = ev["data"]
    ends = ev["ends_at"]
    from datetime import datetime
    ends_str = datetime.fromtimestamp(ends).strftime("%H:%M %d.%m")

    text = (
        f"🎉 <b>НОВЫЙ ИВЕНТ!</b>\n\n"
        f"{data['emoji']} <b>{data['name']}</b>\n"
        f"{data['description']}\n\n"
        f"⏳ До конца: <b>{data['duration_hours']} ч.</b> (до {ends_str})\n\n"
        f"Успей воспользоваться!"
    )

    # Рассылка в группы
    for chat_id in list(registered_chats):
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            pass

    # Рассылка всем пользователям в личку
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users")
                rows = cur.fetchall()
        for row in rows:
            try:
                await bot.send_message(row[0], text)
                await asyncio.sleep(0.05)  # антифлуд
            except Exception:
                pass
    except Exception:
        pass


async def broadcast_event_end(event_name: str):
    """Рассылает объявление о конце ивента."""
    text = f"⏰ <b>Ивент завершён!</b>\n\n«{event_name}» закончился.\nСледи за новыми событиями!"

    for chat_id in list(registered_chats):
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            pass


# ── Автоматические ивенты по расписанию ──────────────────────────────
# Каждый понедельник — день карьериста
# Каждую пятницу — золотая лихорадка
# Случайно раз в 8-24 часа с шансом 25%

async def auto_event_scheduler():
    """Запускается при старте бота и периодически проверяет расписание."""
    from datetime import datetime
    await asyncio.sleep(10)  # ждём старта бота

    while True:
        now     = datetime.now()
        weekday = now.weekday()  # 0=пн, 4=пт, 5=сб, 6=вс

        ev = get_active_event()

        if not ev:
            # Понедельник → двойной XP
            if weekday == 0 and now.hour == 9:
                event_key = "double_xp"
                start_event(event_key)
                await broadcast_event_start(event_key)

            # Пятница → золотая лихорадка
            elif weekday == 4 and now.hour == 18:
                event_key = "double_coins"
                start_event(event_key)
                await broadcast_event_start(event_key)

            # Выходные → золотые выходные
            elif weekday == 5 and now.hour == 10:
                event_key = "golden_weekend"
                start_event(event_key)
                await broadcast_event_start(event_key)

            # Случайный ивент с шансом 20% каждые 6 часов
            elif now.hour in (0, 6, 12, 18) and now.minute < 5:
                if random.random() < 0.20:
                    random_events = ["lucky_hour", "discount", "exam_week", "manasday"]
                    event_key     = random.choice(random_events)
                    start_event(event_key)
                    await broadcast_event_start(event_key)

        await asyncio.sleep(300)  # проверяем каждые 5 минут


# ── Команды ивентов ───────────────────────────────────────────────────
@dp.message(Command("start_event"))
async def cmd_start_event(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        keys = "\n".join(f"  <code>{k}</code> — {v['name']}" for k, v in EVENTS.items())
        await message.answer(
            f"❌ Укажи ключ ивента:\n{keys}\n\n"
            f"Пример: <code>/start_event double_xp</code>"
        )
        return

    event_key = parts[1].lower()
    if event_key not in EVENTS:
        await message.answer(f"❌ Ивент <code>{event_key}</code> не найден.")
        return

    ev = get_active_event()
    if ev:
        await message.answer(
            f"⚠️ Уже идёт ивент: <b>{ev['data']['name']}</b>\n"
            f"Сначала завершите его: /end_event"
        )
        return

    start_event(event_key)
    await message.answer(f"✅ Ивент <b>{EVENTS[event_key]['name']}</b> запущен! Рассылаю...")
    await broadcast_event_start(event_key)


@dp.message(Command("end_event"))
async def cmd_end_event(message: Message):
    global current_event
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    ev = get_active_event()
    if not ev:
        await message.answer("❌ Нет активного ивента.")
        return

    name = ev["data"]["name"]
    current_event = None
    await message.answer(f"✅ Ивент <b>{name}</b> завершён.")
    await broadcast_event_end(name)


@dp.message(Command("current_event"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("ивент", "событие", "event")))
async def cmd_current_event(message: Message):
    ev = get_active_event()
    if not ev:
        await message.answer(
            "😴 Сейчас активных ивентов нет.\n"
            "Следи за объявлениями!"
        )
        return

    from datetime import datetime
    data     = ev["data"]
    ends_str = datetime.fromtimestamp(ev["ends_at"]).strftime("%H:%M %d.%m")
    remaining = max(0, ev["ends_at"] - int(time.time()))
    hours     = remaining // 3600
    minutes   = (remaining % 3600) // 60

    bonuses = []
    if data["multiplier_coins"] != 1.0:
        bonuses.append(f"💰 Монеты с работы: x{data['multiplier_coins']}")
    if data["multiplier_xp"] != 1.0:
        bonuses.append(f"✨ Опыт с работы: x{data['multiplier_xp']}")
    if data["lucky_boost"] > 0:
        bonuses.append(f"🍀 Шанс удачи на работе: {data['lucky_boost']}%")
    if data["shop_discount"] > 0:
        bonuses.append(f"🛒 Скидка в магазине: -{data['shop_discount']}%")

    bonuses_text = "\n".join(f"  • {b}" for b in bonuses)

    await message.answer(
        f"🎉 <b>Активный ивент!</b>\n\n"
        f"{data['emoji']} <b>{data['name']}</b>\n"
        f"{data['description']}\n\n"
        f"🎁 <b>Бонусы:</b>\n{bonuses_text}\n\n"
        f"⏳ Осталось: <b>{hours}ч {minutes}мин</b> (до {ends_str})"
    )
# =====================================================================
# БЛЕКДЖЕК
# =====================================================================
BJ_MIN_BET = 50
bj_games: dict[int, dict] = {}  # user_id -> game state

BJ_DECK_TEMPLATE = (
    [str(r) for r in range(2, 11)] + ["J", "Q", "K", "A"]
) * 4

def bj_card_value(card: str) -> int:
    if card in ("J", "Q", "K"):
        return 10
    if card == "A":
        return 11
    return int(card)

def bj_hand_value(hand: list[str]) -> int:
    total = sum(bj_card_value(c) for c in hand)
    aces  = hand.count("A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def bj_hand_str(hand: list[str]) -> str:
    return "  ".join(f"[{c}]" for c in hand)

def bj_new_game(user_id: int, bet: int, balance: int) -> dict:
    deck = list(BJ_DECK_TEMPLATE)
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    return {
        "user_id": user_id,
        "bet": bet,
        "balance": balance,
        "deck": deck,
        "player": player,
        "dealer": dealer,
        "done": False,
    }

def bj_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🃏 Ещё карту", callback_data=f"bj_hit:{user_id}")
    builder.button(text="✋ Хватит",    callback_data=f"bj_stand:{user_id}")
    builder.button(text="⚡ Удвоить",   callback_data=f"bj_double:{user_id}")
    builder.adjust(3)
    return builder.as_markup()

def bj_status_text(game: dict, reveal_dealer: bool = False) -> str:
    p_val = bj_hand_value(game["player"])
    d_val = bj_hand_value(game["dealer"])

    if reveal_dealer:
        dealer_str = f"{bj_hand_str(game['dealer'])}  (сумма: {d_val})"
    else:
        dealer_str = f"[{game['dealer'][0]}]  [?]"

    return (
        f"🃏 <b>Блекджек</b>\n\n"
        f"🏦 Дилер: {dealer_str}\n\n"
        f"👤 Ты: {bj_hand_str(game['player'])}  (сумма: <b>{p_val}</b>)\n\n"
        f"💰 Ставка: <b>{game['bet']}</b> монет"
    )

async def bj_finish(message_or_callback, game: dict, reason: str):
    user_id   = game["user_id"]
    user_data = get_user(user_id) or {}
    p_val   = bj_hand_value(game["player"])
    d_val   = bj_hand_value(game["dealer"])
    bet     = game["bet"]
    balance = game["balance"]

    while bj_hand_value(game["dealer"]) < 17:
        game["dealer"].append(game["deck"].pop())
    d_val = bj_hand_value(game["dealer"])

    p_bj = (len(game["player"]) == 2 and p_val == 21)
    d_bj = (len(game["dealer"]) == 2 and d_val == 21)

    if p_bj and not d_bj:
        prize  = apply_full_coin_bonus(user_data, int(bet * 1.5))
        result = f"🃏 <b>БЛЕКДЖЕК!</b> +{prize} монет"
        net = bet + prize
        change_reputation(user_id, +2)
    elif p_val > 21:
        prize = 0
        result = f"💥 <b>Перебор ({p_val})!</b> Проигрыш -{bet} монет"
        net = 0
        change_reputation(user_id, -1)
    elif d_val > 21:
        prize  = apply_full_coin_bonus(user_data, bet)
        result = f"🎉 <b>Дилер перебрал ({d_val})!</b> +{prize} монет"
        net = bet + prize
        change_reputation(user_id, +1)
    elif p_val > d_val:
        prize  = apply_full_coin_bonus(user_data, bet)
        result = f"🏆 <b>Победа! ({p_val} vs {d_val})</b> +{prize} монет"
        net = bet + prize
        change_reputation(user_id, +1)
    elif p_val < d_val:
        prize = 0
        result = f"😢 <b>Проигрыш ({p_val} vs {d_val})</b> -{bet} монет"
        net = 0
        change_reputation(user_id, -1)
    else:
        prize = 0
        result = f"🤝 <b>Ничья ({p_val})</b> — ставка возвращена"
        net = bet
    new_balance = balance + net
    if net > bet or (p_bj and not d_bj) or d_val > 21 or p_val > d_val:
        bump_stat(user_id, "stat_blackjack_wins")
    elif p_val > 21 or p_val < d_val:
        bump_stat(user_id, "stat_blackjack_losses")
    update_user(user_id, balance=new_balance)


    if game["user_id"] in bj_games:
        del bj_games[game["user_id"]]

    text = (
        f"🃏 <b>Блекджек — итог</b>\n\n"
        f"🏦 Дилер: {bj_hand_str(game['dealer'])}  (сумма: {d_val})\n"
        f"👤 Ты:    {bj_hand_str(game['player'])}  (сумма: {p_val})\n\n"
        f"{result}\n"
        f"💳 Баланс: <b>{new_balance}</b> монет"
    )

    if hasattr(message_or_callback, "message"):
        await message_or_callback.answer()
        await message_or_callback.message.answer(text)
    else:
        await message_or_callback.answer(text)

    # Квест и ачивки
    updated = get_user(user_id)
    if updated:
        check_and_grant_achievements(updated)


@dp.message(F.text.func(lambda t: t and t.strip().lower().startswith("блекджек ")))
async def cmd_blackjack(message: Message):
    uid   = message.from_user.id
    user  = get_user_safe(uid, message.from_user.username or message.from_user.full_name)

    if uid in bj_games:
        await message.answer("⚠️ У тебя уже идёт партия! Доиграй сначала.")
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ Формат: <code>блекджек 200</code>")
        return

    bet = int(parts[1])
    if bet < BJ_MIN_BET:
        await message.answer(f"❌ Мин. ставка: <b>{BJ_MIN_BET}</b> монет.")
        return
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно монет. Баланс: <b>{user['balance']}</b>")
        return

    update_user(uid, balance=user["balance"] - bet)
    game = bj_new_game(uid, bet, user["balance"] - bet)
    bj_games[uid] = game

    p_val = bj_hand_value(game["player"])

    # Мгновенный блекджек
    if p_val == 21:
        await message.answer(bj_status_text(game, reveal_dealer=False))
        await bj_finish(message, game, "blackjack")
        return

    await message.answer(bj_status_text(game), reply_markup=bj_keyboard(uid))


@dp.callback_query(F.data.startswith("bj_hit:"))
async def bj_hit(callback: CallbackQuery):
    uid  = int(callback.data.split(":")[1])
    if callback.from_user.id != uid:
        await callback.answer("Это не твоя игра!", show_alert=True)
        return

    game = bj_games.get(uid)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    game["player"].append(game["deck"].pop())
    p_val = bj_hand_value(game["player"])

    if p_val >= 21:
        await callback.answer()
        await callback.message.edit_text(bj_status_text(game, reveal_dealer=False))
        await bj_finish(callback, game, "bust" if p_val > 21 else "21")
    else:
        await callback.answer()
        await callback.message.edit_text(bj_status_text(game), reply_markup=bj_keyboard(uid))


@dp.callback_query(F.data.startswith("bj_stand:"))
async def bj_stand(callback: CallbackQuery):
    uid  = int(callback.data.split(":")[1])
    if callback.from_user.id != uid:
        await callback.answer("Это не твоя игра!", show_alert=True)
        return

    game = bj_games.get(uid)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    await callback.answer()
    await bj_finish(callback, game, "stand")


@dp.callback_query(F.data.startswith("bj_double:"))
async def bj_double(callback: CallbackQuery):
    uid  = int(callback.data.split(":")[1])
    if callback.from_user.id != uid:
        await callback.answer("Это не твоя игра!", show_alert=True)
        return

    game = bj_games.get(uid)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    # Проверяем баланс на удвоение
    user = get_user(uid)
    if not user or user["balance"] < game["bet"]:
        await callback.answer("❌ Недостаточно монет для удвоения!", show_alert=True)
        return

    update_user(uid, balance=user["balance"] - game["bet"])
    game["balance"] = user["balance"] - game["bet"]
    game["bet"] *= 2

    # Берём ровно одну карту
    game["player"].append(game["deck"].pop())
    await callback.answer()
    await bj_finish(callback, game, "double")
import json as _json_boss

def get_boss_cooldowns(user: dict) -> dict:
    raw = user.get("boss_cooldowns", "") or "{}"
    try:
        return _json_boss.loads(raw)
    except Exception:
        return {}

def save_boss_cooldowns(user_id: int, cds: dict):
    update_user(user_id, boss_cooldowns=_json_boss.dumps(cds))

def get_boss_items(user: dict) -> dict:
    raw = user.get("boss_items", "") or "{}"
    try:
        return _json_boss.loads(raw)
    except Exception:
        return {}

def save_boss_items(user_id: int, items: dict):
    update_user(user_id, boss_items=_json_boss.dumps(items))


def check_boss_cooldown(user: dict, boss_key: str) -> tuple[bool, int]:
    boss = BOSSES.get(boss_key)
    if not boss:
        return False, 0
    cds = get_boss_cooldowns(user)
    last = cds.get(boss_key, 0)
    cooldown_sec = boss["cooldown_hours"] * 3600
    now = int(time.time())
    remaining = cooldown_sec - (now - last)
    return remaining <= 0, max(0, remaining)


def get_total_luck(user: dict) -> int:
    _, _, combined_luck = get_combined_bonus(user)
    return user.get("luck", 1) + combined_luck + get_event_extra().get("global_luck_bonus", 0)


def roll_boss_item(user: dict) -> str | None:
    """Возвращает ключ предмета или None. Шанс дропа и редкость зависят от удачи."""
    luck = get_total_luck(user)
    drop_chance = min(85, 20 + luck)  # % шанс получить хоть что-то
    if random.randint(1, 100) > drop_chance:
        return None

    # Веса редкости, смещаемые удачей в сторону эпика/леги
    weights = {
        "common":    max(10, 55 - luck * 1.2),
        "rare":      30 + luck * 0.6,
        "epic":      12 + luck * 0.9,
        "legendary": 2  + luck * 0.35,
    }
    rarities = list(weights.keys())
    rarity = random.choices(rarities, weights=[weights[r] for r in rarities], k=1)[0]

    pool = [k for k, v in BOSS_ITEMS.items() if v["rarity"] == rarity]
    if not pool:
        return None
    item_weights = [BOSS_ITEMS[k]["weight"] for k in pool]
    return random.choices(pool, weights=item_weights, k=1)[0]


def calc_boss_power(user: dict) -> int:
    base = (
        user.get("agility", 1)   +
        user.get("endurance", 1) +
        user.get("charisma", 1)  +
        user.get("intellect", 1)
    )
    luck_bonus = get_total_luck(user) * 2
    roll = random.randint(1, 50)
    return base + luck_bonus + roll


def do_fight_boss(user: dict, boss_key: str) -> tuple[bool, str]:
    if is_incapacitated(user):
        return False, get_incapacitated_message(user)

    boss = BOSSES.get(boss_key)
    if not boss:
        return False, "❌ Такого босса нет."
    if user["level"] < boss["min_level"]:
        return False, f"❌ Нужен уровень <b>{boss['min_level']}</b> (у тебя {user['level']})."

    can, remaining = check_boss_cooldown(user, boss_key)
    if not can:
        h = remaining // 3600
        m = (remaining % 3600) // 60
        return False, f"⏳ <b>{boss['name']}</b> ещё не восстановился.\nПодожди: <b>{h}ч {m}мин</b>."

    energy_cost = apply_energy_discount(boss["energy_cost"])
    if user["energy"] < energy_cost:
        return False, (
            f"😴 Недостаточно энергии! Нужно {energy_cost} ⚡, "
            f"есть {user['energy']} ⚡."
        )

    # Тратим энергию и ставим кулдаун СРАЗУ — не даём фармить спамом попыток
    new_energy = max(0, user["energy"] - energy_cost)
    cds = get_boss_cooldowns(user)
    cds[boss_key] = int(time.time())
    update_user(user["user_id"], energy=new_energy)
    save_boss_cooldowns(user["user_id"], cds)
    user = {**user, "energy": new_energy}

    user_power = calc_boss_power(user)
    boss_power = boss["power_threshold"] + random.randint(0, int(boss["power_threshold"] * 0.3))
    won = user_power > boss_power

    if not won:
        new_hp, lost_hp = apply_hp_damage(user["user_id"], user, 10, 20)
        return True, (
            f"⚔️ <b>{boss['name']}</b>\n\n"
            f"💪 Твоя сила: <b>{user_power}</b> vs 👹 Сила босса: <b>{boss_power}</b>\n\n"
            f"❌ <b>Поражение...</b>\n<i>{boss['lose_text']}</i>\n\n"
            f"⚡ Энергия: <b>{new_energy}</b> (-{boss['energy_cost']})\n"
            f"❤️ HP: <b>-{lost_hp}</b> → {new_hp} / {get_max_hp(user)}\n"
            f"🔁 Следующая попытка через {boss['cooldown_hours']}ч."
        )

    boss_bonus = get_event_extra().get("boss_reward_bonus", 0)
    shards = random.randint(boss["reward_shards_min"], boss["reward_shards_max"])
    shards = int(shards * (1 + boss_bonus / 100))
    new_shards = user.get("shards", 0) + shards
    base_coins = int(boss["power_threshold"] * random.uniform(1.8, 2.8))
    base_exp = int(boss["power_threshold"] * random.uniform(2.5, 4.0))
    ev_coins_mult, ev_xp_mult, _, _ = get_event_multipliers()
    earned_coins = apply_full_coin_bonus(user, base_coins)  # уже учитывает ивент-монеты
    earned_exp = int(apply_combined_xp_bonus(user, base_exp) * ev_xp_mult)

    fresh = get_user(user["user_id"])
    new_balance = fresh["balance"] + earned_coins
    new_exp = fresh["exp"] + earned_exp
    update_user(user["user_id"], balance=new_balance, exp=new_exp)
    user = {**fresh, "balance": new_balance, "exp": new_exp}
    user, level_msgs = auto_level_up(user)
    level_block = "".join(level_msgs)
    if random.random() < 0.15:  # 15% шанс капнуть кристалл с обычного босса
        update_user(user["user_id"], ascension_crystals=user.get("ascension_crystals", 0) + 1)
    update_user(user["user_id"], shards=new_shards)
    bump_stat(user["user_id"], "stat_boss_kills")
    contribute_faculty_points(user["user_id"], 15)
    change_reputation(user["user_id"], +2)

    item_line = ""
    dropped_key = roll_boss_item(user)
    if dropped_key:
        items = get_boss_items(user)
        item = BOSS_ITEMS[dropped_key]
        if dropped_key in items:
            items[dropped_key] += 1
            bonus_text = get_boss_item_bonus_text(dropped_key, items[dropped_key])
            item_line = (
                f"\n\n🎁 Дубликат: <b>{item['name']}</b> {item['rarity_label']}\n"
                f"Уровень предмета: <b>{items[dropped_key]}</b> (даёт {bonus_text})"
            )
        else:
            items[dropped_key] = 1
            bonus_text = get_boss_item_bonus_text(dropped_key, 1)
            item_line = (
                f"\n\n🎁 <b>НОВЫЙ ПРЕДМЕТ!</b>\n{item['name']} {item['rarity_label']}\n"
                f"🎁 Даёт: <b>{bonus_text}</b>\n"
                f"<i>{item['description']}</i>"
            )
            if not user.get("equipped_boss_item"):
                update_user(user["user_id"], equipped_boss_item=dropped_key)
                item_line += "\n🔧 Автоматически экипирован (первый предмет)."
        save_boss_items(user["user_id"], items)

    updated = get_user(user["user_id"])
    ach_msgs = check_and_grant_achievements(updated) if updated else []
    title_msgs = check_and_grant_titles(updated) if updated else []
    extra = ("\n\n" + "\n".join(ach_msgs + title_msgs)) if (ach_msgs or title_msgs) else ""

    return True, (
        f"⚔️ <b>{boss['name']}</b>\n\n"
        f"💪 Твоя сила: <b>{user_power}</b> vs 👹 Сила босса: <b>{boss_power}</b>\n\n"
        f"🏆 <b>ПОБЕДА!</b>\n<i>{boss['win_text']}</i>\n\n"
        f"🔶 Осколков получено: <b>+{shards}</b> (всего: {new_shards})\n"
        f"💰 Монет: <b>+{earned_coins}</b>\n"
        f"✨ Опыта: <b>+{earned_exp}</b>\n"
        f"{level_block}"
        f"⚡ Энергия: <b>{new_energy}</b> (-{boss['energy_cost']})\n"
        f"🔁 Следующая попытка через {boss['cooldown_hours']}ч."
        f"{item_line}{extra}"
    )
def do_upgrade_boss_item(user: dict, item_key: str) -> tuple[bool, str]:
    item = BOSS_ITEMS.get(item_key)
    if not item:
        return False, "❌ Неизвестный предмет."
    items = get_boss_items(user)
    if item_key not in items:
        return False, "❌ У тебя нет этого предмета."

    level = items[item_key]
    cost  = item["upgrade_cost_base"] * level
    if user.get("shards", 0) < cost:
        return False, f"❌ Нужно <b>{cost}</b> 🔶 осколков, есть <b>{user.get('shards', 0)}</b>."

    items[item_key] += 1
    save_boss_items(user["user_id"], items)
    update_user(user["user_id"], shards=user.get("shards", 0) - cost)
    return True, (
        f"✅ <b>{item['name']}</b> улучшен до уровня <b>{items[item_key]}</b>!\n"
        f"🔶 Потрачено: {cost} осколков."
    )
def build_bosses_text(user: dict) -> str:
    lines = ["👹 <b>Боссы КТУ «Манас»</b>\n", f"🔶 Осколков: <b>{user.get('shards', 0)}</b>\n"]
    for key, boss in BOSSES.items():
        can, remaining = check_boss_cooldown(user, key)
        if user["level"] < boss["min_level"]:
            status = f"🔒 нужен {boss['min_level']} ур."
        elif can:
            status = "✅ доступен"
        else:
            h, m = remaining // 3600, (remaining % 3600) // 60
            status = f"⏳ {h}ч {m}мин"
        lines.append(
            f"<b>{boss['name']}</b> — {status}\n"
            f"  <i>{boss['description']}</i>\n"
            f"  ⚡ {boss['energy_cost']} | 🔁 КД {boss['cooldown_hours']}ч | "
            f"🔶 {boss['reward_shards_min']}-{boss['reward_shards_max']}"
        )
    return "\n\n".join(lines)


def get_bosses_keyboard(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, boss in BOSSES.items():
        can, _ = check_boss_cooldown(user, key)
        if user["level"] >= boss["min_level"] and can:
            builder.button(text=f"⚔️ {boss['name']}", callback_data=f"boss_fight:{key}")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(Command("bosses"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("боссы", "босс", "bosses")))
async def cmd_bosses(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_bosses_text(user), reply_markup=get_bosses_keyboard(user))


@dp.callback_query(F.data.startswith("boss_fight:"))
async def callback_boss_fight(callback: CallbackQuery):
    boss_key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    await callback.answer()
    _, text = do_fight_boss(user, boss_key)
    await callback.message.answer(text)
    updated = get_user(callback.from_user.id)
    await callback.message.edit_text(build_bosses_text(updated), reply_markup=get_bosses_keyboard(updated))


def build_inventory_text(user: dict) -> str:
    items = get_boss_items(user)
    equipped = user.get("equipped_boss_item", "")
    lines = ["🎒 <b>Трофеи с боссов</b>\n", f"🔶 Осколков: <b>{user.get('shards', 0)}</b>\n"]
    if not items:
        lines.append("Пусто. Побеждай боссов, чтобы получить предметы!")
    for key, level in items.items():
        if key not in BOSS_ITEMS:
            continue
        item = BOSS_ITEMS[key]
        mark = " ◀ экипирован" if key == equipped else ""
        cost = item["upgrade_cost_base"] * level
        bonus_text = get_boss_item_bonus_text(key, level)
        lines.append(
            f"{'✅' if key == equipped else '•'} <b>{item['name']}</b> {item['rarity_label']}{mark}\n"
            f"  🎁 Даёт: <b>{bonus_text}</b>\n"
            f"  <i>{item['description']}</i>\n"
            f"  Уровень: {level} | Улучшение: {cost} 🔶"
        )
    lines.append(
        "\n<i>Экипировать можно только ОДИН предмет одновременно — "
        "выбирай тот, чей бонус тебе нужнее.</i>"
    )
    return "\n\n".join(lines)


def get_inventory_keyboard(user: dict) -> InlineKeyboardMarkup:
    items = get_boss_items(user)
    builder = InlineKeyboardBuilder()
    for key in items:
        if key not in BOSS_ITEMS:
            continue
        item = BOSS_ITEMS[key]
        builder.button(text=f"🔧 Экипировать {item['name'][:20]}", callback_data=f"boss_equip:{key}")
        builder.button(text=f"⬆️ Улучшить {item['name'][:20]}", callback_data=f"boss_upgrade:{key}")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(Command("inventory"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("рюкзак", "трофеи", "инвентарь боссов")))
async def cmd_boss_inventory(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_inventory_text(user), reply_markup=get_inventory_keyboard(user))


@dp.callback_query(F.data.startswith("boss_equip:"))
async def callback_boss_equip(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    items = get_boss_items(user)
    if key not in items:
        await callback.answer("У тебя нет этого предмета!", show_alert=True)
        return
    update_user(callback.from_user.id, equipped_boss_item=key)
    await callback.answer(f"✅ Экипирован: {BOSS_ITEMS[key]['name']}!", show_alert=True)
    updated = get_user(callback.from_user.id)
    await callback.message.edit_text(build_inventory_text(updated), reply_markup=get_inventory_keyboard(updated))


@dp.callback_query(F.data.startswith("boss_upgrade:"))
async def callback_boss_upgrade(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_upgrade_boss_item(user, key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_inventory_text(updated), reply_markup=get_inventory_keyboard(updated))

@dp.message(Command("balance"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("баланс", "balance", "монеты")))
async def cmd_balance(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(
        f"💰 Монеты: <b>{user['balance']}</b>\n"
        f"🔶 Осколки: <b>{user.get('shards', 0)}</b>"
    )
@dp.message(F.text == "🔗 Пригласить друзей", F.chat.type == "private")
async def btn_referral_private(message: Message):
    await cmd_referral(message)


async def _get_all_user_ids() -> list[int]:
    """Возвращает список всех user_id из таблицы users."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            rows = cur.fetchall()
    return [r[0] for r in rows]


async def _broadcast_text(admin_message: Message, content: str):
    """Рассылает текстовое объявление всем пользователям и группам."""
    status_msg = await admin_message.answer("📢 Начинаю рассылку...")

    text = f"📢 <b>Объявление от администрации</b>\n\n{content}"

    user_ids = await _get_all_user_ids()
    sent_users, failed_users = 0, 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent_users += 1
        except Exception:
            failed_users += 1
        await asyncio.sleep(0.05)  # антифлуд, ~20 сообщений/сек

    sent_chats, failed_chats = 0, 0
    for chat_id in list(registered_chats):
        try:
            await bot.send_message(chat_id, text)
            sent_chats += 1
        except Exception:
            failed_chats += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"👤 Личные сообщения: <b>{sent_users}</b> успешно, <b>{failed_users}</b> ошибок\n"
        f"👥 Группы: <b>{sent_chats}</b> успешно, <b>{failed_chats}</b> ошибок"
    )


async def _broadcast_copy(admin_message: Message, source_chat_id: int, source_msg_id: int):
    """Рассылает копию сообщения (текст/фото/видео/документ) всем пользователям и группам."""
    status_msg = await admin_message.answer("📢 Начинаю рассылку (копия сообщения)...")

    user_ids = await _get_all_user_ids()
    sent_users, failed_users = 0, 0
    for uid in user_ids:
        try:
            await bot.copy_message(uid, source_chat_id, source_msg_id)
            sent_users += 1
        except Exception:
            failed_users += 1
        await asyncio.sleep(0.05)

    sent_chats, failed_chats = 0, 0
    for chat_id in list(registered_chats):
        try:
            await bot.copy_message(chat_id, source_chat_id, source_msg_id)
            sent_chats += 1
        except Exception:
            failed_chats += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"👤 Личные сообщения: <b>{sent_users}</b> успешно, <b>{failed_users}</b> ошибок\n"
        f"👥 Группы: <b>{sent_chats}</b> успешно, <b>{failed_chats}</b> ошибок"
    )


@dp.message(Command("announce"))
@dp.message(F.text.func(lambda t: t and t.strip().lower().startswith("объявление")))
async def cmd_announce(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    # Режим 1: ответ на сообщение -> рассылаем копию (работает с фото/видео/текстом)
    if message.reply_to_message:
        await _broadcast_copy(
            message,
            message.reply_to_message.chat.id,
            message.reply_to_message.message_id,
        )
        return

    # Режим 2: обычный текст после команды
    raw = message.text.strip()
    if raw.lower().startswith("/announce"):
        content = raw[len("/announce"):].strip()
    else:
        content = raw[len("объявление"):].strip()

    if not content:
        await message.answer(
            "❌ Формат:\n"
            "<code>объявление Текст объявления</code>\n"
            "или <code>/announce Текст объявления</code>\n\n"
            "Либо ответь словом <code>объявление</code> на сообщение "
            "(в том числе с фото/видео) — разошлю точную копию."
        )
        return

    await _broadcast_text(message, content)

# =====================================================================
# РЕСУРСЫ
# =====================================================================
import json as _json_gather
RESOURCES = {
    # ══════════ ОХОТА ══════════
    "fur":            {"name": "🦫 Шкура",              "sell_price": 12,  "rarity": "common",    "loc": "hunting"},
    "meat":           {"name": "🍖 Мясо",                "sell_price": 15,  "rarity": "common",    "loc": "hunting"},
    "bone":           {"name": "🦴 Кость",               "sell_price": 22,  "rarity": "uncommon",  "loc": "hunting"},
    "leather_hide":   {"name": "🟫 Дублёная шкура",      "sell_price": 30,  "rarity": "uncommon",  "loc": "hunting"},
    "wolf_fang":      {"name": "🐺 Клык волка",          "sell_price": 45,  "rarity": "rare",      "loc": "hunting"},
    "eagle_feather":  {"name": "🦅 Перо беркута",        "sell_price": 55,  "rarity": "rare",      "loc": "hunting"},
    "ibex_horn":      {"name": "🐐 Рог тэке",            "sell_price": 90,  "rarity": "epic",      "loc": "hunting"},
    "snow_pelt":      {"name": "❄️ Шкура барса",         "sell_price": 130, "rarity": "epic",      "loc": "hunting"},
    "golden_antler":  {"name": "🦌✨ Золотые рога",       "sell_price": 220, "rarity": "legendary", "loc": "hunting"},
    "manas_essence":  {"name": "🐎 Эссенция духа Манаса","sell_price": 400, "rarity": "mythic",    "loc": "hunting"},

    # ══════════ РЫБАЛКА ══════════
    "small_fish":     {"name": "🐟 Мелкая рыба",         "sell_price": 10,  "rarity": "common",    "loc": "fishing"},
    "carp":           {"name": "🐠 Карп",                "sell_price": 18,  "rarity": "common",    "loc": "fishing"},
    "trout":          {"name": "🐟 Форель",              "sell_price": 24,  "rarity": "uncommon",  "loc": "fishing"},
    "pearl":          {"name": "🦪 Жемчужина",           "sell_price": 35,  "rarity": "uncommon",  "loc": "fishing"},
    "big_catfish":    {"name": "🐡 Сом-гигант",          "sell_price": 60,  "rarity": "rare",      "loc": "fishing"},
    "river_crystal":  {"name": "🔷 Речной кристалл",     "sell_price": 75,  "rarity": "rare",      "loc": "fishing"},
    "turtle_shell":   {"name": "🐢 Панцирь черепахи",    "sell_price": 110, "rarity": "epic",      "loc": "fishing"},
    "golden_fish":    {"name": "🐟✨ Золотая рыбка",      "sell_price": 150, "rarity": "epic",      "loc": "fishing"},
    "kraken_scale":   {"name": "🐙 Чешуя кракена",       "sell_price": 240, "rarity": "legendary", "loc": "fishing"},
    "issykkul_pearl": {"name": "🌊✨ Жемчужина Иссык-Куля","sell_price": 420, "rarity": "mythic",    "loc": "fishing"},

    # ══════════ ШАХТА ══════════
    "stone":          {"name": "🪨 Камень",              "sell_price": 8,   "rarity": "common",    "loc": "mining"},
    "coal":           {"name": "⚫ Уголь",                "sell_price": 14,  "rarity": "common",    "loc": "mining"},
    "iron_ore":       {"name": "⛓ Железная руда",        "sell_price": 25,  "rarity": "uncommon",  "loc": "mining"},
    "copper_ore":     {"name": "🟠 Медная руда",         "sell_price": 32,  "rarity": "uncommon",  "loc": "mining"},
    "silver_ore":     {"name": "🔗 Серебряная руда",     "sell_price": 50,  "rarity": "rare",      "loc": "mining"},
    "gold_ore":       {"name": "🟡 Золотая руда",        "sell_price": 70,  "rarity": "rare",      "loc": "mining"},
    "platinum_ore":   {"name": "⚪ Платиновая руда",     "sell_price": 110, "rarity": "epic",      "loc": "mining"},
    "diamond":        {"name": "💎 Алмаз",               "sell_price": 130, "rarity": "epic",      "loc": "mining"},
    "mythril_shard":  {"name": "🔮 Осколок мифрила",     "sell_price": 250, "rarity": "legendary", "loc": "mining"},
    "star_core":      {"name": "🌌 Ядро звезды",         "sell_price": 450, "rarity": "mythic",    "loc": "mining"},
}

RESOURCE_RARITY_WEIGHTS = {"common": 55, "uncommon": 38, "rare": 30, "epic": 12, "legendary": 3, "mythic": 1}

GATHER_NODES = {
    "hunting": {
        "label":       "🏹 Охота",
        "skill_key":   "hunting_level",
        "tool_type":   "hunting",
        "energy_cost": 20,
        "cooldown":    180,
        "min_level":   1,
        "yield_min":   1, "yield_max": 2,
    },
    "fishing": {
        "label":       "🎣 Рыбалка",
        "skill_key":   "fishing_level",
        "tool_type":   "fishing",
        "energy_cost": 15,
        "cooldown":    150,
        "min_level":   1,
        "yield_min":   1, "yield_max": 2,
    },
    "mining": {
        "label":       "⛏ Шахта",
        "skill_key":   "mining_level",
        "tool_type":   "mining",
        "energy_cost": 25,
        "cooldown":    200,
        "min_level":   1,
        "yield_min":   1, "yield_max": 2,
    },
}

ZONES = {
    "hunting": {
        "forest_edge": {
            "name": "🌳 Опушка леса", "min_skill": 0,
            "pool": {"fur": 40, "meat": 40, "bone": 15, "leather_hide": 4, "wolf_fang": 1},
            "yield_mult": 1.0, "energy_mult": 1.0,
            "flavor": "Обычный лес рядом с Джалом.",
        },
        "dense_thicket": {
            "name": "🌲 Густая чаща", "min_skill": 5,
            "pool": {"fur": 25, "meat": 30, "bone": 22, "leather_hide": 13, "wolf_fang": 8, "eagle_feather": 2},
            "yield_mult": 1.3, "energy_mult": 1.2,
            "flavor": "Гуще заросли — опаснее звери, но добыча богаче.",
        },
        "mountain_pass": {
            "name": "🏔 Горный перевал", "min_skill": 12,
            "pool": {"bone": 20, "leather_hide": 22, "wolf_fang": 20, "eagle_feather": 18, "ibex_horn": 15, "snow_pelt": 5},
            "yield_mult": 1.7, "energy_mult": 1.5,
            "flavor": "Здесь бродят волчьи стаи и снежные барсы.",
        },
        "tian_shan_peaks": {
            "name": "⛰ Вершины Тянь-Шаня", "min_skill": 20,
            "pool": {"wolf_fang": 18, "eagle_feather": 20, "ibex_horn": 25, "snow_pelt": 25, "golden_antler": 10, "manas_essence": 2},
            "yield_mult": 2.2, "energy_mult": 1.8,
            "flavor": "Царство редчайших зверей. Только для мастеров.",
        },
        "legendary_steppe": {
            "name": "🐎 Легендарная степь", "min_skill": 35,
            "pool": {"ibex_horn": 20, "snow_pelt": 25, "golden_antler": 35, "manas_essence": 20},
            "yield_mult": 3.0, "energy_mult": 2.3,
            "flavor": "Место, где, по легенде, охотился сам Манас.",
        },
    },
    "fishing": {
        "shallow_creek": {
            "name": "🏞 Мелкий ручей", "min_skill": 0,
            "pool": {"small_fish": 45, "carp": 35, "trout": 15, "pearl": 4, "big_catfish": 1},
            "yield_mult": 1.0, "energy_mult": 1.0,
            "flavor": "Спокойное место для новичков.",
        },
        "jal_river": {
            "name": "🌊 Река у Джала", "min_skill": 5,
            "pool": {"small_fish": 25, "carp": 30, "trout": 22, "pearl": 13, "big_catfish": 8, "river_crystal": 2},
            "yield_mult": 1.3, "energy_mult": 1.2,
            "flavor": "Течение сильнее, рыба крупнее.",
        },
        "issyk_kul_shore": {
            "name": "🏔 Побережье Иссык-Куля", "min_skill": 12,
            "pool": {"trout": 20, "pearl": 22, "big_catfish": 20, "river_crystal": 18, "turtle_shell": 15, "golden_fish": 5},
            "yield_mult": 1.7, "energy_mult": 1.5,
            "flavor": "Легендарное озеро хранит немало сокровищ.",
        },
        "abyss_depths": {
            "name": "🌌 Глубины бездны", "min_skill": 20,
            "pool": {"big_catfish": 18, "river_crystal": 20, "turtle_shell": 25, "golden_fish": 25, "kraken_scale": 10, "issykkul_pearl": 2},
            "yield_mult": 2.2, "energy_mult": 1.8,
            "flavor": "Только опытные рыбаки решаются заплыть так далеко.",
        },
        "sacred_waters": {
            "name": "🌊✨ Священные воды", "min_skill": 35,
            "pool": {"turtle_shell": 20, "golden_fish": 25, "kraken_scale": 35, "issykkul_pearl": 20},
            "yield_mult": 3.0, "energy_mult": 2.3,
            "flavor": "Место, куда заплывают только легенды рыбалки.",
        },
    },
    "mining": {
        "old_quarry": {
            "name": "🪨 Старый карьер", "min_skill": 0,
            "pool": {"stone": 45, "coal": 35, "iron_ore": 15, "copper_ore": 4, "silver_ore": 1},
            "yield_mult": 1.0, "energy_mult": 1.0,
            "flavor": "Заброшенный карьер рядом с КТУ.",
        },
        "coal_tunnels": {
            "name": "⛏ Угольные туннели", "min_skill": 5,
            "pool": {"stone": 25, "coal": 30, "iron_ore": 22, "copper_ore": 13, "silver_ore": 8, "gold_ore": 2},
            "yield_mult": 1.3, "energy_mult": 1.2,
            "flavor": "Глубже под землёй — больше руды.",
        },
        "silver_caverns": {
            "name": "🕳 Серебряные пещеры", "min_skill": 12,
            "pool": {"iron_ore": 20, "copper_ore": 22, "silver_ore": 20, "gold_ore": 18, "platinum_ore": 15, "diamond": 5},
            "yield_mult": 1.7, "energy_mult": 1.5,
            "flavor": "Опасные обвалы, но богатая жила.",
        },
        "diamond_abyss": {
            "name": "💎 Алмазная бездна", "min_skill": 20,
            "pool": {"silver_ore": 18, "gold_ore": 20, "platinum_ore": 25, "diamond": 25, "mythril_shard": 10, "star_core": 2},
            "yield_mult": 2.2, "energy_mult": 1.8,
            "flavor": "Самая глубокая точка штольни Тянь-Шаня.",
        },
        "core_of_tianshan": {
            "name": "🌌 Ядро Тянь-Шаня", "min_skill": 35,
            "pool": {"platinum_ore": 20, "diamond": 25, "mythril_shard": 35, "star_core": 20},
            "yield_mult": 3.0, "energy_mult": 2.3,
            "flavor": "Геологи считают, что глубже уже некуда.",
        },
    },
}

MASTERY_RANKS = [
    (10,  "🥉 Подмастерье",      5,  {"shards": 30}),
    (20,  "🥈 Умелец",           10, {"shards": 60, "ascension_crystals": 1}),
    (35,  "🥇 Мастер",           18, {"shards": 120, "ascension_crystals": 2}),
    (50,  "💠 Грандмастер",      28, {"shards": 250, "ascension_crystals": 4}),
    (75,  "👑 Легенда промысла", 40, {"shards": 500, "ascension_crystals": 8}),
    (100, "🌌 Владыка стихий",   60, {"shards": 1000, "ascension_crystals": 15}),
]

def get_mastery_rank(skill_val: int) -> tuple[str, int]:
    name, bonus = "", 0
    for threshold, rank_name, pct, _ in MASTERY_RANKS:
        if skill_val >= threshold:
            name, bonus = rank_name, pct
    return name, bonus

def get_mastery_claimed(user: dict) -> set:
    import json
    raw = user.get("mastery_claimed", "") or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    return set(data.get("claimed", []))

def save_mastery_claimed(user_id: int, claimed: set):
    import json
    update_user(user_id, mastery_claimed=json.dumps({"claimed": list(claimed)}))

def check_and_grant_mastery(user_id: int, skill_key: str, skill_val: int) -> list[str]:
    user = get_user(user_id)
    if not user:
        return []
    claimed = get_mastery_claimed(user)
    messages = []
    for threshold, rank_name, pct, rewards in MASTERY_RANKS:
        tag = f"{skill_key}:{threshold}"
        if skill_val >= threshold and tag not in claimed:
            claimed.add(tag)
            extra = {}
            for field, amount in rewards.items():
                extra[field] = user.get(field, 0) + amount
            update_user(user_id, **extra)
            reward_str = ", ".join(f"+{v} {k}" for k, v in rewards.items())
            messages.append(
                f"🏆 <b>Новый ранг мастерства!</b> {rank_name} (ур. {threshold})\n"
                f"🎁 Награда: {reward_str}\n"
                f"📈 Постоянный бонус к добыче: +{pct}%"
            )
    if messages:
        save_mastery_claimed(user_id, claimed)
    return messages

def get_active_zone_key(user: dict, node_key: str) -> str:
    field = f"active_zone_{node_key}"
    zk = user.get(field, "") or ""
    zones = ZONES[node_key]
    if zk in zones:
        skill_val = user.get(GATHER_NODES[node_key]["skill_key"], 0)
        if skill_val >= zones[zk]["min_skill"]:
            return zk
    return list(zones.keys())[0]

def _luck_weight_boost(rarity: str, luck_bonus: int) -> int:
    if rarity == "mythic":
        return luck_bonus * 3
    if rarity == "legendary":
        return luck_bonus * 2
    if rarity == "epic":
        return luck_bonus
    return 0

def roll_resource_from_pool(pool: dict, luck_bonus: int) -> str:
    keys = list(pool.keys())
    weights = []
    for k in keys:
        rarity = RESOURCES[k]["rarity"]
        w = pool[k] + _luck_weight_boost(rarity, luck_bonus)
        weights.append(max(1, w))
    return random.choices(keys, weights=weights, k=1)[0]

def roll_resource(loc: str, luck_bonus: int) -> str:
    pool = [k for k, v in RESOURCES.items() if v["loc"] == loc]
    weights = []
    for k in pool:
        rarity = RESOURCES[k]["rarity"]
        base_w = RESOURCE_RARITY_WEIGHTS[rarity]
        weights.append(max(1, base_w + _luck_weight_boost(rarity, luck_bonus)))
    return random.choices(pool, weights=weights, k=1)[0]

def build_zone_text(user: dict, node_key: str) -> str:
    zones = ZONES[node_key]
    skill_val = user.get(GATHER_NODES[node_key]["skill_key"], 0)
    current = get_active_zone_key(user, node_key)
    lines = [f"🗺 <b>Зоны — {GATHER_NODES[node_key]['label']}</b>\n"]
    for k, z in zones.items():
        locked = skill_val < z["min_skill"]
        mark = " ✅ активна" if k == current else ""
        status = f"🔒 нужен навык {z['min_skill']}" if locked else "🔓 доступна"
        lines.append(
            f"<b>{z['name']}</b> — {status}{mark}\n"
            f"  <i>{z['flavor']}</i>\n"
            f"  Бонус добычи: x{z['yield_mult']} | Энергозатраты: x{z['energy_mult']}"
        )
    return "\n\n".join(lines)

def get_zone_keyboard(user: dict, node_key: str) -> InlineKeyboardMarkup:
    zones = ZONES[node_key]
    skill_val = user.get(GATHER_NODES[node_key]["skill_key"], 0)
    builder = InlineKeyboardBuilder()
    for k, z in zones.items():
        if skill_val >= z["min_skill"]:
            builder.button(text=f"🗺 {z['name']}", callback_data=f"zone_set:{node_key}:{k}")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("зона охота", "зона рыбалка", "зона шахта")))
async def txt_zone_menu(message: Message):
    mapping = {"зона охота": "hunting", "зона рыбалка": "fishing", "зона шахта": "mining"}
    node_key = mapping[message.text.strip().lower()]
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_zone_text(user, node_key), reply_markup=get_zone_keyboard(user, node_key))

@dp.callback_query(F.data.startswith("zone_set:"))
async def cb_zone_set(callback: CallbackQuery):
    _, node_key, zone_key = callback.data.split(":")
    user = get_user_safe(callback.from_user.id)
    skill_val = user.get(GATHER_NODES[node_key]["skill_key"], 0)
    zone = ZONES[node_key].get(zone_key)
    if not zone or skill_val < zone["min_skill"]:
        await callback.answer("Зона недоступна!", show_alert=True)
        return
    update_user(callback.from_user.id, **{f"active_zone_{node_key}": zone_key})
    await callback.answer(f"✅ Зона установлена: {zone['name']}!", show_alert=True)
    updated = get_user(callback.from_user.id)
    await callback.message.edit_text(build_zone_text(updated, node_key), reply_markup=get_zone_keyboard(updated, node_key))

# =====================================================================
# ИНСТРУМЕНТЫ (крафт из ресурсов + монет). Дают:
#   - yield_bonus_pct: % к количеству добычи
#   - luck_bonus: смещает шансы в сторону редких ресурсов
#   - req_level: игровой уровень для крафта/использования
# =====================================================================

# =====================================================================
# ЛОКАЦИОННЫЕ БОССЫ (отдельно от BOSSES — своя механика и КД)
# Сила считается от gather-скилла + инструмента, а не от общих характеристик
# =====================================================================
LOCATION_BOSSES = {
    "forest_predator": {
        "name": "🐗 Секач из леса у Джала", "loc": "hunting",
        "min_level": 8, "cooldown_hours": 5, "energy_cost": 30,
        "power_threshold": 60,
        "reward_res_min": 3, "reward_res_max": 6,
        "description": "Гигантский кабан гоняет студентов, забредших в лес по грибы.",
        "win_text": "Ты выследил и одолел секача. Трофей достанется тебе.",
        "lose_text": "Секач оказался быстрее. Пришлось ретироваться.",
    },
    "lake_monster": {
        "name": "🐊 Чудище озера у Джала", "loc": "fishing",
        "min_level": 12, "cooldown_hours": 6, "energy_cost": 32,
        "power_threshold": 80,
        "reward_res_min": 3, "reward_res_max": 6,
        "description": "По слухам, в озере живёт нечто больше, чем сом-гигант.",
        "win_text": "Чудище всплыло брюхом кверху. Легенда подтвердилась — трофей твой!",
        "lose_text": "Леска лопнула в последний момент. Чудище ушло на глубину.",
    },
    "cave_golem": {
        "name": "🗿 Голем заброшенной штольни", "loc": "mining",
        "min_level": 18, "cooldown_hours": 8, "energy_cost": 35,
        "power_threshold": 110,
        "reward_res_min": 4, "reward_res_max": 8,
        "description": "Каменный страж старой шахты под корпусом Джал.",
        "win_text": "Голем рассыпался в щебень. Среди обломков — редкая порода.",
        "lose_text": "Голем отбросил тебя к выходу из штольни.",
    },
    "alpha_wolf": {
        "name": "🐺 Вожак стаи Тянь-Шаня", "loc": "hunting",
        "min_level": 35, "cooldown_hours": 14, "energy_cost": 42,
        "power_threshold": 220,
        "reward_res_min": 6, "reward_res_max": 12,
        "description": "Матёрый волк, водящий стаю в предгорьях.",
        "win_text": "Стая отступила, признав в тебе более сильного хищника.",
        "lose_text": "Стая обошла тебя с флангов. Пришлось спасаться бегством.",
    },
    "river_dragon": {
        "name": "🐉 Речной дракон Чуйской долины", "loc": "fishing",
        "min_level": 45, "cooldown_hours": 16, "energy_cost": 45,
        "power_threshold": 260,
        "reward_res_min": 6, "reward_res_max": 12,
        "description": "Мифическое существо, охраняющее исток реки.",
        "win_text": "Дракон нырнул в глубину, оставив на берегу чешую.",
        "lose_text": "Волна от хвоста дракона смыла тебя на берег.",
    },
    "mountain_titan": {
        "name": "🏔 Титан горной породы", "loc": "mining",
        "min_level": 60, "cooldown_hours": 20, "energy_cost": 50,
        "power_threshold": 340,
        "reward_res_min": 8, "reward_res_max": 15,
        "description": "Финальный страж самой глубокой штольни Тянь-Шаня.",
        "win_text": "Титан рассыпался в алмазную пыль. Величайшая добыча в твоих руках.",
        "lose_text": "Титан оказался крепче гранита. Отступление.",
    },
}

# Трофеи с локационных боссов — отдельный слот equipped_location_item,
# бонусы касаются ТОЛЬКО сбора ресурсов (yield/luck), никак не пересекаются
# с equipped_boss_item (тот даёт монеты/опыт/удачу с работы)
LOCATION_BOSS_ITEMS = {
    "boar_tusk_charm": {
        "name": "🦷 Амулет клыка секача", "rarity_label": "🔵 Редкий",
        "yield_bonus_pct": 8, "luck_bonus": 4,
        "description": "Выпадает с 🐗 Секача. Небольшой бонус к добыче на охоте.",
        "boss_only": "forest_predator", "upgrade_cost_base": 250,
    },
    "monster_scale": {
        "name": "🐊 Чешуя озёрного чудища", "rarity_label": "🔵 Редкий",
        "yield_bonus_pct": 8, "luck_bonus": 4,
        "description": "Выпадает с 🐊 Чудища озера. Бонус к рыбалке.",
        "boss_only": "lake_monster", "upgrade_cost_base": 250,
    },
    "golem_core": {
        "name": "🗿 Ядро голема", "rarity_label": "🟣 Эпик",
        "yield_bonus_pct": 14, "luck_bonus": 8,
        "description": "Выпадает с 🗿 Голема штольни. Заметный бонус к добыче в шахте.",
        "boss_only": "cave_golem", "upgrade_cost_base": 500,
    },
    "alpha_fang_necklace": {
        "name": "🐺 Ожерелье клыка вожака", "rarity_label": "🟣 Эпик",
        "yield_bonus_pct": 16, "luck_bonus": 10,
        "description": "Выпадает с 🐺 Вожака стаи. Сильный бонус к охоте.",
        "boss_only": "alpha_wolf", "upgrade_cost_base": 600,
    },
    "dragon_scale_amulet": {
        "name": "🐉 Амулет чешуи дракона", "rarity_label": "🟡 Легендарный",
        "yield_bonus_pct": 25, "luck_bonus": 15,
        "description": "Выпадает с 🐉 Речного дракона. Топовый бонус к рыбалке.",
        "boss_only": "river_dragon", "upgrade_cost_base": 900,
    },
    "titan_heart": {
        "name": "🏔 Сердце титана", "rarity_label": "🟡 Легендарный",
        "yield_bonus_pct": 30, "luck_bonus": 20,
        "description": "Выпадает с 🏔 Титана горной породы. Максимальный бонус к шахте.",
        "boss_only": "mountain_titan", "upgrade_cost_base": 1200,
    },
}


# =====================================================================
# ХЕЛПЕРЫ
# =====================================================================
def get_resources(user: dict) -> dict:
    raw = user.get("resources", "") or "{}"
    try:
        return _json_gather.loads(raw)
    except Exception:
        return {}

def _sum_resources(u: dict) -> int:
    return sum(get_resources(u).values())

def save_resources(user_id: int, res: dict):
    update_user(user_id, resources=_json_gather.dumps(res))


@dp.message(Command("mastery"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() == "мастерство"))
async def cmd_mastery(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    lines = ["🎖 <b>Мастерство промыслов</b>\n"]
    for skill_key, cfg in GATHER_SKILL_CONFIG.items():
        val = user.get(skill_key, 0)
        rank_name, pct = get_mastery_rank(val)
        next_threshold = next((t for t, *_ in MASTERY_RANKS if t > val), None)
        next_line = f"\nСледующий ранг на ур. {next_threshold}" if next_threshold else "\nМаксимальный ранг!"
        lines.append(f"<b>{cfg['label']}</b>: ур. {val}\n  Ранг: {rank_name or '—'} (+{pct}%){next_line}")
    await message.answer("\n\n".join(lines))


def get_location_items(user: dict) -> dict:
    raw = user.get("location_items", "") or "{}"
    try:
        return _json_gather.loads(raw)
    except Exception:
        return {}


def save_location_items(user_id: int, items: dict):
    update_user(user_id, location_items=_json_gather.dumps(items))


def get_location_boss_cooldowns(user: dict) -> dict:
    raw = user.get("location_boss_cooldowns", "") or "{}"
    try:
        return _json_gather.loads(raw)
    except Exception:
        return {}


def save_location_boss_cooldowns(user_id: int, cds: dict):
    update_user(user_id, location_boss_cooldowns=_json_gather.dumps(cds))

def get_gather_yield_bonus(user: dict, tool_type: str) -> tuple[int, int]:
    """tool_type здесь = node_key: "hunting" / "fishing" / "mining" """
    yield_pct, luck = 0, 0

    level = get_tool_level(user, tool_type)
    current_tool = get_current_tool(tool_type, level)
    if current_tool:
        yield_pct += current_tool["yield_bonus_pct"]
        luck += current_tool["luck_bonus"]

    loc_key = user.get("equipped_location_item", "")
    if loc_key and loc_key in LOCATION_BOSS_ITEMS:
        item = LOCATION_BOSS_ITEMS[loc_key]
        boss_loc = LOCATION_BOSSES.get(item["boss_only"], {}).get("loc")
        if boss_loc == tool_type:
            items_owned = get_location_items(user)
            item_level = items_owned.get(loc_key, 1)
            yield_pct += item["yield_bonus_pct"] + (item_level - 1) * 3
            luck += item["luck_bonus"] + (item_level - 1) * 2

    skill_key = GATHER_NODES[tool_type]["skill_key"]
    _, mastery_pct = get_mastery_rank(user.get(skill_key, 0))
    yield_pct += mastery_pct

    return yield_pct, luck


def get_gather_cooldown(user: dict, node_key: str) -> int:
    node = GATHER_NODES[node_key]
    agility = user.get("agility", 1)
    reduction = min(90, agility // 4)
    return max(30, node["cooldown"] - reduction)

GATHER_BATCH_SIZES = [1, 5, 20]

def do_gather(user: dict, node_key: str, times: int = 1) -> tuple[bool, str]:
    if is_incapacitated(user):
        return False, get_incapacitated_message(user)
    node = GATHER_NODES.get(node_key)
    if not node:
        return False, "❌ Неизвестная локация."
    if user["level"] < node["min_level"]:
        return False, f"❌ Нужен уровень <b>{node['min_level']}</b>."

    times = max(1, min(times, 20))

    time_field = {"hunting": "last_hunt_time", "fishing": "last_fish_time", "mining": "last_mine_time"}[node_key]
    now = int(time.time())
    cooldown = get_gather_cooldown(user, node_key)
    elapsed = now - user.get(time_field, 0)
    if elapsed < cooldown:
        return False, f"⏳ Подожди ещё <b>{cooldown - elapsed}</b> сек."

    zone_key = get_active_zone_key(user, node_key)
    zone = ZONES[node_key][zone_key]

    energy_cost_unit = apply_energy_discount(int(node["energy_cost"] * zone["energy_mult"]))
    total_energy_cost = energy_cost_unit * times
    if user["energy"] < total_energy_cost:
        max_times = max(1, user["energy"] // max(1, energy_cost_unit))
        return False, (
            f"😴 Недостаточно энергии на x{times}! Нужно {total_energy_cost} ⚡, "
            f"есть {user['energy']} ⚡.\n<i>Хватит максимум на x{max_times}.</i>"
        )

    skill_val = user.get(node["skill_key"], 0)
    yield_pct, luck_bonus = get_gather_yield_bonus(user, node["tool_type"])
    total_luck = get_total_luck(user) + luck_bonus
    gather_mult = get_event_extra().get("gather_multiplier", 1.0)

    gained: dict[str, int] = {}
    treasure_coins = 0
    treasure_shards = 0
    treasure_hits = 0

    for _ in range(times):
        base_amount = random.randint(node["yield_min"], node["yield_max"]) + skill_val // 5
        amount = max(1, int(base_amount * (1 + yield_pct / 100) * zone["yield_mult"] * gather_mult))
        for _ in range(amount):
            res_key = roll_resource_from_pool(zone["pool"], total_luck)
            gained[res_key] = gained.get(res_key, 0) + 1

        if random.random() < min(0.25, 0.05 + total_luck / 200):
            treasure_hits += 1
            treasure_coins += random.randint(30, 90) * (1 + skill_val // 20)
            treasure_shards += random.randint(1, 3)

    resources = get_resources(user)
    for k, v in gained.items():
        resources[k] = resources.get(k, 0) + v
    save_resources(user["user_id"], resources)

    import json as _js_coll
    try:
        coll = _js_coll.loads(user.get("gather_collection", "") or "{}")
    except Exception:
        coll = {}
    for k, v in gained.items():
        coll[k] = coll.get(k, 0) + v
    update_user(user["user_id"], gather_collection=_js_coll.dumps(coll))

    new_energy = max(0, user["energy"] - total_energy_cost)
    extra_fields = {"energy": new_energy, time_field: now}
    if treasure_coins:
        extra_fields["balance"] = user["balance"] + apply_full_coin_bonus(user, treasure_coins)
    if treasure_shards:
        extra_fields["shards"] = user.get("shards", 0) + treasure_shards
    update_user(user["user_id"], **extra_fields)

    hunt_count_field = {"hunting": "stat_hunt_count", "fishing": "stat_fish_count", "mining": "stat_mine_count"}[node_key]
    bump_stat(user["user_id"], hunt_count_field, times)

    injury_line = ""
    if random.random() < 0.20:
        fresh_user = get_user(user["user_id"])
        new_hp, lost_hp = apply_hp_damage(user["user_id"], fresh_user, 4, 9)
        injury_line = f"\n\n🩹 Травма во время добычи! ❤️ -{lost_hp} HP → {new_hp}/{get_max_hp(fresh_user)}"

    lines_res = "\n".join(f"  {RESOURCES[k]['name']} x{v}" for k, v in sorted(gained.items(), key=lambda x: -x[1]))
    treasure_line = ""
    if treasure_hits:
        treasure_line = f"\n\n💰 <b>Найден клад x{treasure_hits}!</b>\n  +{treasure_coins} монет, +{treasure_shards} 🔶 осколков"

    updated = get_user(user["user_id"])
    ach_msgs = check_and_grant_achievements(updated) if updated else []
    title_msgs = check_and_grant_titles(updated) if updated else []
    extra_msgs = ("\n\n" + "\n".join(ach_msgs + title_msgs)) if (ach_msgs or title_msgs) else ""

    rank_name, rank_pct = get_mastery_rank(skill_val)
    rank_line = f"\n🎖 Мастерство: <b>{rank_name or '—'}</b> (+{rank_pct}%)" if rank_name else ""
    contribute_faculty_points(user["user_id"], times * 2)


    return True, (
        f"{node['label']} ×{times} — зона: <b>{zone['name']}</b>\n\n"
        f"📦 <b>Добыча:</b>\n{lines_res}\n\n"
        f"⚡ Энергия: <b>{new_energy}</b> (-{total_energy_cost}){rank_line}"
        f"{treasure_line}{injury_line}{extra_msgs}"
    )


def build_gather_text(user: dict, node_key: str) -> str:
    node = GATHER_NODES[node_key]
    skill_val = user.get(node["skill_key"], 0)
    yield_pct, luck_bonus = get_gather_yield_bonus(user, node["tool_type"])

    tool_level = get_tool_level(user, node["tool_type"])
    current_tool = get_current_tool(node["tool_type"], tool_level)
    tool_name = current_tool["name"] if current_tool else "нет"

    cooldown = get_gather_cooldown(user, node_key)

    return (
        f"{node['label']}\n\n"
        f"🧠 Навык: <b>{skill_val}</b>\n"
        f"🛠 Инструмент: <b>{tool_name}</b>\n"
        f"📈 Бонус к добыче: +{yield_pct}% | 🍀 удача: +{luck_bonus}\n"
        f"⚡ Стоимость: {node['energy_cost']} | ⏳ КД: {cooldown}с\n\n"
        f"<i>Прокачивай навык в 🧭 Навыки сбора и крафти инструменты в 🛠 Мастерской.</i>"
    )


def do_upgrade_gather_skill(user: dict, skill_key: str) -> tuple[bool, str]:
    cfg = GATHER_SKILL_CONFIG.get(skill_key)
    if not cfg:
        return False, "❌ Неизвестный навык."
    val = user.get(skill_key, 0)
    cost = max(cfg["cost_base"], val * cfg["cost_base"])
    if user["balance"] < cost:
        return False, f"❌ Нужно <b>{cost}</b> монет, есть <b>{user['balance']}</b>."
    new_val = val + 1
    update_user(user["user_id"], **{skill_key: new_val, "balance": user["balance"] - cost})
    text = f"✅ <b>{cfg['label']}</b> прокачан до уровня <b>{new_val}</b>! Потрачено {cost} монет."
    mastery_msgs = check_and_grant_mastery(user["user_id"], skill_key, new_val)
    if mastery_msgs:
        text += "\n\n" + "\n".join(mastery_msgs)
    return True, text


def build_gather_skills_text(user: dict) -> tuple[str, "InlineKeyboardMarkup"]:
    builder = InlineKeyboardBuilder()
    lines = ["🧭 <b>Навыки сбора</b>\n"]
    for key, cfg in GATHER_SKILL_CONFIG.items():
        val = user.get(key, 0)
        cost = max(cfg["cost_base"], val * cfg["cost_base"])
        lines.append(f"{cfg['label']}: <b>{val} ур.</b>\n  <i>{cfg['description']}</i>\n  Апгрейд: {cost} монет")
        builder.button(text=f"⬆️ {cfg['label']} ({cost} мон.)", callback_data=f"upgrade_gskill:{key}")
    builder.adjust(1)
    return "\n\n".join(lines), builder.as_markup()


def do_sell_resource(user: dict, res_key: str, quantity: int) -> tuple[bool, str]:
    res = RESOURCES.get(res_key)
    if not res:
        return False, "❌ Неизвестный ресурс."
    resources = get_resources(user)
    have = resources.get(res_key, 0)
    quantity = max(1, min(quantity, have))
    if quantity <= 0 or have <= 0:
        return False, "❌ У тебя нет этого ресурса."

    total = res["sell_price"] * quantity
    resources[res_key] = have - quantity
    if resources[res_key] <= 0:
        del resources[res_key]
    save_resources(user["user_id"], resources)

    new_balance = user["balance"] + total
    update_user(user["user_id"], balance=new_balance)
    return True, f"✅ Продано {res['name']} x{quantity} за <b>{total}</b> монет.\n💰 Баланс: <b>{new_balance}</b>"

def do_sell_all_resources(user: dict) -> tuple[bool, str]:
    resources = get_resources(user)
    if not resources:
        return False, "❌ У тебя нет ресурсов для продажи."

    total = 0
    lines = []
    for k, qty in list(resources.items()):
        if k not in RESOURCES or qty <= 0:
            continue
        price = RESOURCES[k]["sell_price"] * qty
        total += price
        lines.append(f"  {RESOURCES[k]['name']} x{qty} — {price} мон.")

    if total == 0:
        return False, "❌ Нечего продавать."

    save_resources(user["user_id"], {})
    new_balance = user["balance"] + total
    update_user(user["user_id"], balance=new_balance)

    return True, (
        f"✅ <b>Продано всё!</b>\n\n" + "\n".join(lines) +
        f"\n\n💰 Итого получено: <b>{total}</b> монет\n"
        f"📊 Баланс: <b>{new_balance}</b> монет"
    )

@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("продать всё", "продать все", "sell all")))
async def txt_sell_all(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    success, text = do_sell_all_resources(user)
    await message.answer(text)

def get_sell_keyboard(user: dict) -> "InlineKeyboardMarkup":
    resources = get_resources(user)
    builder = InlineKeyboardBuilder()
    if resources:
        builder.button(text="💰 Продать ВСЁ", callback_data="sell_all_res")
    for k, v in resources.items():
        if k not in RESOURCES or v <= 0:
            continue
        r = RESOURCES[k]
        builder.button(text=f"💰 Продать {r['name']} x{v}", callback_data=f"sell_res:{k}:{v}")
    builder.adjust(1)
    return builder.as_markup()

@dp.callback_query(F.data == "sell_all_res")
async def cb_sell_all(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    success, text = do_sell_all_resources(user)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_resources_text(updated), reply_markup=get_sell_keyboard(updated))

def build_resources_text(user: dict) -> str:
    resources = get_resources(user)
    if not resources:
        return "🎒 <b>Ресурсы</b>\n\nПусто. Иди на охоту/рыбалку/в шахту!"
    lines = ["🎒 <b>Твои ресурсы</b>\n"]
    for k, v in resources.items():
        if k not in RESOURCES:
            continue
        r = RESOURCES[k]
        lines.append(f"{r['name']} x<b>{v}</b> — цена продажи {r['sell_price']} мон./шт.")
    return "\n".join(lines)


def get_sell_keyboard(user: dict) -> "InlineKeyboardMarkup":
    resources = get_resources(user)
    builder = InlineKeyboardBuilder()
    for k, v in resources.items():
        if k not in RESOURCES or v <= 0:
            continue
        r = RESOURCES[k]
        builder.button(text=f"💰 Продать {r['name']} x{v}", callback_data=f"sell_res:{k}:{v}")
    builder.adjust(1)
    return builder.as_markup()

# =====================================================================
# ЛОКАЦИОННЫЕ БОССЫ — логика
# =====================================================================
def check_location_boss_cooldown(user: dict, boss_key: str) -> tuple[bool, int]:
    boss = LOCATION_BOSSES.get(boss_key)
    if not boss:
        return False, 0
    cds = get_location_boss_cooldowns(user)
    last = cds.get(boss_key, 0)
    cooldown_sec = boss["cooldown_hours"] * 3600
    now = int(time.time())
    remaining = cooldown_sec - (now - last)
    return remaining <= 0, max(0, remaining)


def calc_location_boss_power(user: dict, loc: str) -> int:
    node = GATHER_NODES[loc]
    skill_val = user.get(node["skill_key"], 0)
    yield_pct, luck_bonus = get_gather_yield_bonus(user, node["tool_type"])
    base = skill_val * 4 + int(yield_pct * 0.8) + luck_bonus * 2
    roll = random.randint(1, 60)
    return base + roll


def roll_location_boss_item(user: dict, boss_key: str) -> str | None:
    pool = [k for k, v in LOCATION_BOSS_ITEMS.items() if v["boss_only"] == boss_key]
    if not pool:
        return None
    _, luck_bonus = get_gather_yield_bonus(user, LOCATION_BOSSES[boss_key]["loc"])
    drop_chance = min(70, 25 + luck_bonus)
    if random.randint(1, 100) > drop_chance:
        return None
    return random.choice(pool)


def do_fight_location_boss(user: dict, boss_key: str) -> tuple[bool, str]:
    if is_incapacitated(user):
        return False, get_incapacitated_message(user)

    boss = LOCATION_BOSSES.get(boss_key)
    if not boss:
        return False, "❌ Такого босса нет."
    if user["level"] < boss["min_level"]:
        return False, f"❌ Нужен уровень <b>{boss['min_level']}</b>."

    can, remaining = check_location_boss_cooldown(user, boss_key)
    if not can:
        h, m = remaining // 3600, (remaining % 3600) // 60
        return False, f"⏳ Босс ещё не восстановился: <b>{h}ч {m}мин</b>."

    energy_cost = apply_energy_discount(boss["energy_cost"])
    if user["energy"] < energy_cost:
        return False, (
            f"😴 Недостаточно энергии! Нужно {energy_cost} ⚡, "
            f"есть {user['energy']} ⚡."
        )

    new_energy = max(0, user["energy"] - energy_cost)
    cds = get_location_boss_cooldowns(user)
    cds[boss_key] = int(time.time())
    update_user(user["user_id"], energy=new_energy)
    save_location_boss_cooldowns(user["user_id"], cds)
    user = {**user, "energy": new_energy}

    power = calc_location_boss_power(user, boss["loc"])
    boss_power = boss["power_threshold"] + random.randint(0, int(boss["power_threshold"] * 0.3))
    won = power > boss_power

    if not won:
        new_hp, lost_hp = apply_hp_damage(user["user_id"], user, 10, 20)
        return True, (
            f"⚔️ <b>{boss['name']}</b>\n\n"
            f"💪 Сила: <b>{power}</b> vs 👹 <b>{boss_power}</b>\n\n"
            f"❌ <b>Поражение...</b>\n<i>{boss['lose_text']}</i>\n"
            f"⚡ -{boss['energy_cost']} | ❤️ HP -{lost_hp} → {new_hp} / {get_max_hp(user)}\n"
            f"🔁 КД {boss['cooldown_hours']}ч"
        )

    node = GATHER_NODES[boss["loc"]]
    boss_bonus = get_event_extra().get("boss_reward_bonus", 0)
    amount = int(random.randint(boss["reward_res_min"], boss["reward_res_max"]) * (1 + boss_bonus / 100))
    resources = get_resources(user)
    gained = {}
    for _ in range(amount):
        rk = roll_resource(boss["loc"], 10)
        gained[rk] = gained.get(rk, 0) + 1
        resources[rk] = resources.get(rk, 0) + 1
    save_resources(user["user_id"], resources)
    bump_stat(user["user_id"], "stat_location_boss_kills")
    base_coins = int(boss["power_threshold"] * random.uniform(1.8, 2.8))
    base_exp = int(boss["power_threshold"] * random.uniform(2.5, 4.0))
    ev_coins_mult, ev_xp_mult, _, _ = get_event_multipliers()
    earned_coins = apply_full_coin_bonus(user, base_coins)  # уже учитывает ивент-монеты
    earned_exp = int(apply_combined_xp_bonus(user, base_exp) * ev_xp_mult)

    fresh = get_user(user["user_id"])
    new_balance = fresh["balance"] + earned_coins
    new_exp = fresh["exp"] + earned_exp
    update_user(user["user_id"], balance=new_balance, exp=new_exp)
    user = {**fresh, "balance": new_balance, "exp": new_exp}
    user, level_msgs = auto_level_up(user)
    level_block = "".join(level_msgs)
    contribute_faculty_points(user["user_id"], 15)
    change_reputation(user["user_id"], +2)

    item_line = ""
    dropped = roll_location_boss_item(user, boss_key)
    if dropped:
        items = get_location_items(user)
        it = LOCATION_BOSS_ITEMS[dropped]
        if dropped in items:
            items[dropped] += 1
            item_line = f"\n\n🎁 Дубликат: <b>{it['name']}</b> {it['rarity_label']} (уровень {items[dropped]})"
        else:
            items[dropped] = 1
            item_line = f"\n\n🎁 <b>НОВЫЙ ТРОФЕЙ!</b>\n{it['name']} {it['rarity_label']}\n<i>{it['description']}</i>"
            if not user.get("equipped_location_item"):
                update_user(user["user_id"], equipped_location_item=dropped)
                item_line += "\n🔧 Автоматически экипирован."
        save_location_items(user["user_id"], items)

    res_lines = "\n".join(f"  {RESOURCES[k]['name']} x{v}" for k, v in gained.items())

    updated = get_user(user["user_id"])
    ach_msgs = check_and_grant_achievements(updated) if updated else []
    title_msgs = check_and_grant_titles(updated) if updated else []
    extra = ("\n\n" + "\n".join(ach_msgs + title_msgs)) if (ach_msgs or title_msgs) else ""

    return True, (
        f"⚔️ <b>{boss['name']}</b>\n\n"
        f"💪 Сила: <b>{power}</b> vs 👹 <b>{boss_power}</b>\n\n"
        f"🏆 <b>ПОБЕДА!</b>\n<i>{boss['win_text']}</i>\n\n"
        f"📦 Добыча:\n{res_lines}\n"
        f"💰 Монет: <b>+{earned_coins}</b>\n"
        f"✨ Опыта: <b>+{earned_exp}</b>\n"
        f"{level_block}"
        f"⚡ -{boss['energy_cost']} | 🔁 КД {boss['cooldown_hours']}ч"
        f"{item_line}{extra}"
    )


def do_upgrade_location_item(user: dict, item_key: str) -> tuple[bool, str]:
    item = LOCATION_BOSS_ITEMS.get(item_key)
    if not item:
        return False, "❌ Неизвестный трофей."
    items = get_location_items(user)
    if item_key not in items:
        return False, "❌ У тебя нет этого трофея."
    level = items[item_key]
    cost = item["upgrade_cost_base"] * level
    if user.get("shards", 0) < cost:
        return False, f"❌ Нужно <b>{cost}</b> 🔶 осколков (общих, как с обычных боссов)."
    items[item_key] += 1
    save_location_items(user["user_id"], items)
    update_user(user["user_id"], shards=user.get("shards", 0) - cost)
    return True, f"✅ <b>{item['name']}</b> улучшен до уровня <b>{items[item_key]}</b>!"

def _gather_full_collection(user: dict, loc: str) -> bool:
    import json
    try:
        coll = json.loads(user.get("gather_collection", "") or "{}")
    except Exception:
        coll = {}
    needed = [k for k, v in RESOURCES.items() if v["loc"] == loc]
    return all(coll.get(k, 0) > 0 for k in needed)

def build_location_bosses_text(user: dict) -> str:
    lines = ["👹 <b>Боссы локаций</b>\n"]
    for key, boss in LOCATION_BOSSES.items():
        can, remaining = check_location_boss_cooldown(user, key)
        if user["level"] < boss["min_level"]:
            status = f"🔒 нужен {boss['min_level']} ур."
        elif can:
            status = "✅ доступен"
        else:
            h, m = remaining // 3600, (remaining % 3600) // 60
            status = f"⏳ {h}ч {m}мин"
        lines.append(
            f"<b>{boss['name']}</b> — {status}\n"
            f"  <i>{boss['description']}</i>\n"
            f"  ⚡ {boss['energy_cost']} | 🔁 {boss['cooldown_hours']}ч"
        )
    return "\n\n".join(lines)


def get_location_bosses_keyboard(user: dict) -> "InlineKeyboardMarkup":
    builder = InlineKeyboardBuilder()
    for key, boss in LOCATION_BOSSES.items():
        can, _ = check_location_boss_cooldown(user, key)
        if user["level"] >= boss["min_level"] and can:
            builder.button(text=f"⚔️ {boss['name']}", callback_data=f"locboss_fight:{key}")
    builder.adjust(1)
    return builder.as_markup()

def get_location_item_bonus_text(item_key: str, level: int = 1) -> str:
    item = LOCATION_BOSS_ITEMS.get(item_key)
    if not item:
        return ""
    yield_pct = item["yield_bonus_pct"] + (level - 1) * 3
    luck = item["luck_bonus"] + (level - 1) * 2
    return f"+{yield_pct}% к добыче, +{luck} удачи (только в своей стихии)"


# =====================================================================
# ХЕНДЛЕРЫ
# =====================================================================
def _gather_cmd_match(t: str, keyword: str) -> bool:
    if not t:
        return False
    parts = t.strip().lower().split()
    if not parts or parts[0] != keyword:
        return False
    if len(parts) == 1:
        return True
    if len(parts) == 2 and parts[1].lstrip("x").isdigit():
        return True
    return False

def get_gather_repeat_keyboard(node_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in GATHER_BATCH_SIZES:
        builder.button(text=f"🔁 Ещё x{n}", callback_data=f"gather_do:{node_key}:{n}")
    builder.adjust(3)
    return builder.as_markup()

@dp.message(F.text.func(lambda t: _gather_cmd_match(t, "охота") or _gather_cmd_match(t, "hunt")))
async def txt_hunt(message: Message):
    parts = message.text.strip().lower().split()
    times = int(parts[1].lstrip("x")) if len(parts) == 2 else 1
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    _, text = do_gather(user, "hunting", times)
    await message.answer(text, reply_markup=get_gather_repeat_keyboard("hunting"))

@dp.message(F.text.func(lambda t: _gather_cmd_match(t, "рыбалка") or _gather_cmd_match(t, "fish")))
async def txt_fish(message: Message):
    parts = message.text.strip().lower().split()
    times = int(parts[1].lstrip("x")) if len(parts) == 2 else 1
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    _, text = do_gather(user, "fishing", times)
    await message.answer(text, reply_markup=get_gather_repeat_keyboard("fishing"))

@dp.message(F.text.func(lambda t: _gather_cmd_match(t, "шахта") or _gather_cmd_match(t, "mine")))
async def txt_mine(message: Message):
    parts = message.text.strip().lower().split()
    times = int(parts[1].lstrip("x")) if len(parts) == 2 else 1
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    _, text = do_gather(user, "mining", times)
    await message.answer(text, reply_markup=get_gather_repeat_keyboard("mining"))

@dp.callback_query(F.data.startswith("gather_do:"))
async def cb_gather_do(callback: CallbackQuery):
    _, node_key, times = callback.data.split(":")
    user = get_user_safe(callback.from_user.id)
    await callback.answer()
    _, text = do_gather(user, node_key, int(times))
    await callback.message.answer(text, reply_markup=get_gather_repeat_keyboard(node_key))


@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("навыки сбора", "gskills")))
async def txt_gather_skills(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    text, kb = build_gather_skills_text(user)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("upgrade_gskill:"))
async def cb_upgrade_gskill(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_upgrade_gather_skill(user, key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        new_text, new_kb = build_gather_skills_text(updated)
        await callback.message.edit_text(new_text, reply_markup=new_kb)


@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("ресурсы", "рюкзак сбора")))
async def txt_resources(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_resources_text(user))


@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("продать ресурсы", "продать")))
async def txt_sell_resources(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_resources_text(user), reply_markup=get_sell_keyboard(user))


@dp.callback_query(F.data.startswith("sell_res:"))
async def cb_sell_res(callback: CallbackQuery):
    _, key, qty = callback.data.split(":")
    user = get_user_safe(callback.from_user.id)
    success, text = do_sell_resource(user, key, int(qty))
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_resources_text(updated), reply_markup=get_sell_keyboard(updated))

@dp.message(Command("loc_bosses"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("лок боссы", "боссы локаций")))
async def cmd_location_bosses(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_location_bosses_text(user), reply_markup=get_location_bosses_keyboard(user))


@dp.callback_query(F.data.startswith("locboss_fight:"))
async def cb_location_boss_fight(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    await callback.answer()
    _, text = do_fight_location_boss(user, key)
    await callback.message.answer(text)
    updated = get_user(callback.from_user.id)
    await callback.message.edit_text(build_location_bosses_text(updated), reply_markup=get_location_bosses_keyboard(updated))


@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("трофеи локаций", "трофеи природы")))
async def txt_location_items(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    items = get_location_items(user)
    equipped = user.get("equipped_location_item", "")
    if not items:
        await message.answer("🎒 Трофеев с боссов локаций пока нет. Побеждай их в «лок боссы»!")
        return
    lines = ["🎒 <b>Трофеи локаций</b>\n"]
    builder = InlineKeyboardBuilder()
    for k, level in items.items():
        if k not in LOCATION_BOSS_ITEMS:
            continue
        it = LOCATION_BOSS_ITEMS[k]
        mark = " ◀ экипирован" if k == equipped else ""
        cost = it["upgrade_cost_base"] * level
        bonus_text = get_location_item_bonus_text(k, level)
        lines.append(
            f"{'✅' if k == equipped else '•'} {it['name']} {it['rarity_label']}{mark}\n"
            f"  🎁 Даёт: {bonus_text}\n"
            f"  Уровень {level} | Апгрейд: {cost} 🔶"
        )
        builder.button(text=f"🔧 {it['name'][:20]}", callback_data=f"equip_locitem:{k}")
        builder.button(text=f"⬆️ Улучшить {it['name'][:15]}", callback_data=f"upgrade_locitem:{k}")
    builder.adjust(1)
    await message.answer("\n\n".join(lines), reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("equip_locitem:"))
async def cb_equip_locitem(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    items = get_location_items(user)
    if key not in items:
        await callback.answer("Нет такого трофея!", show_alert=True)
        return
    update_user(callback.from_user.id, equipped_location_item=key)
    await callback.answer(f"✅ Экипирован: {LOCATION_BOSS_ITEMS[key]['name']}!", show_alert=True)


@dp.callback_query(F.data.startswith("upgrade_locitem:"))
async def cb_upgrade_locitem(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_upgrade_location_item(user, key)
    await callback.answer()
    await callback.message.answer(text)

@dp.message(F.text == "🏹 Промыслы")
async def btn_gathering_menu(message: Message):
    await message.answer(
        "🌲 <b>Промыслы</b>\n\n"
        "Напиши: <b>охота</b> / <b>рыбалка</b> / <b>шахта</b>\n"
        "<b>навыки сбора</b> — прокачка\n"
        "<b>мастерская</b> — крафт инструментов\n"
        "<b>инструменты</b> — экипировка\n"
        "<b>ресурсы</b> / <b>продать</b> — инвентарь\n"
        "<b>лок боссы</b> — боссы локаций\n"
        "<b>трофеи локаций</b> — трофеи с боссов локаций"
    )

RESET_ON_REBIRTH = {
    "level": 1, "exp": 0,
    "job": "Безработный", "job_rank": 1,
    "agility": 1, "endurance": 1, "charisma": 1, "intellect": 1,
    "communication_level": 1, "driving_level": 0, "service_level": 0,
    "organization_level": 0, "management_level": 0,
    "has_scooter": 0, "has_shaker": 0, "has_laptop": 0,
    "has_professor_badge": 0, "has_logistics_license": 0,
    "has_import_license": 0, "has_dean_seal": 0,
    "has_business_plan": 0, "has_franchise_contract": 0,
    "has_psychology_book": 0, "has_driving_license": 0, "has_suit": 0,
    "hp": 100, "energy": 100,
    "last_work_time": 0, "last_regen_time": 0,
    "reputation": 0,
    "properties": "{}", "last_income_collect": 0,
    "last_daily_claim": 0, "daily_streak": 0,
    "shards": 0, "boss_items": "{}", "equipped_boss_item": "", "boss_cooldowns": "{}",
    "hunting_level": 0, "fishing_level": 0, "mining_level": 0,
    "last_hunt_time": 0, "last_fish_time": 0, "last_mine_time": 0,
    "resources": "{}", "tools": "{}",
    "equipped_tool_mining": "", "equipped_tool_fishing": "", "equipped_tool_hunting": "",
    "location_items": "{}", "equipped_location_item": "", "location_boss_cooldowns": "{}",
}
# Важно: pet_collection, active_pet, titles, active_title, achievements
# сюда НЕ входят — они сохраняются.


def get_rebirth_status(user: dict) -> tuple[bool, str]:
    if user["level"] < REBIRTH_MIN_LEVEL:
        return False, (
            f"❌ Нужен <b>{REBIRTH_MIN_LEVEL}</b> уровень для перерождения "
            f"(у тебя {user['level']})."
        )
    return True, "✅ Готов к перерождению!"


def do_rebirth(user: dict) -> tuple[bool, str]:
    can, why = get_rebirth_status(user)
    if not can:
        return False, why

    old_rebirths = user.get("rebirths", 0)
    new_rebirths = old_rebirths + 1
    new_luck     = random.randint(1, 10)
    start_bonus = (REBIRTH_START_COINS + old_rebirths * REBIRTH_START_COINS_PER
                   + get_ascension_upgrade_bonus(user, "start_capital"))
    crystals_earned = ASCENSION_CRYSTALS_BASE + old_rebirths * ASCENSION_CRYSTALS_PER
    new_crystals = user.get("ascension_crystals", 0) + crystals_earned

    reset_fields = dict(RESET_ON_REBIRTH)
    reset_fields["luck"]     = new_luck
    reset_fields["rebirths"] = new_rebirths
    reset_fields["balance"]  = start_bonus
    reset_fields["ascension_crystals"] = new_crystals

    spouse_id = user.get("spouse_id")
    if spouse_id:
        update_user(spouse_id, spouse_id=None, married_at=0)
        reset_fields["spouse_id"]  = None
        reset_fields["married_at"] = 0

    update_user(user["user_id"], **reset_fields)

    unlocked_line = ""
    if new_rebirths in REBIRTH_STARTER_JOBS:
        job_key = REBIRTH_STARTER_JOBS[new_rebirths]
        unlocked_line = (
            f"\n\n🔓 <b>Открыта новая ветка профессий!</b>\n"
            f"«{JOBS[job_key]['name']}» теперь доступна при выборе профессии."
        )

    coin_bonus = new_rebirths * REBIRTH_COIN_BONUS_PER
    xp_bonus   = new_rebirths * REBIRTH_XP_BONUS_PER

    updated = get_user(user["user_id"])
    if updated:
        check_and_grant_achievements(updated)
        check_and_grant_titles(updated)

    return True, (
        f"✨ <b>ПЕРЕРОЖДЕНИЕ!</b> ✨\n\n"
        f"🔄 Ты переродился <b>{new_rebirths}</b> раз(а)!\n"
        f"📉 Уровень, опыт, баланс, характеристики, навыки, снаряжение, "
        f"недвижимость, репутация и прогресс промыслов сброшены.\n"
        f"🐾 Питомцы, 🎖 титулы и 🏅 достижения — сохранены!\n\n"
        f"💰 Стартовый капитал: <b>{start_bonus}</b> монет\n"
        f"🌌 Получено кристаллов Вознесения: <b>+{crystals_earned}</b> (всего: {new_crystals})\n"
        f"📈 Постоянный бонус: <b>+{coin_bonus}%</b> монет, <b>+{xp_bonus}%</b> опыта\n"
        f"🍀 Новая удача: <b>{new_luck}</b>"
        f"{unlocked_line}"
    )

@dp.message(Command("rebirth"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in
                                  ("переродиться", "перерождение", "rebirth")))
async def cmd_rebirth(message: Message):
    user      = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    can, why  = get_rebirth_status(user)
    rebirths  = user.get("rebirths", 0)
    coin_bonus = rebirths * REBIRTH_COIN_BONUS_PER
    xp_bonus   = rebirths * REBIRTH_XP_BONUS_PER

    lines = [
        "🔄 <b>Перерождение</b>\n",
        f"Ты перерождался: <b>{rebirths}</b> раз(а)",
        f"Текущий бонус: +{coin_bonus}% монет, +{xp_bonus}% опыта\n",
        f"📌 Условие: уровень <b>{REBIRTH_MIN_LEVEL}</b>+ (у тебя {user['level']})\n",
        "⚠️ При перерождении сбрасываются: уровень, опыт, баланс, характеристики, "
        "навыки, снаряжение, недвижимость, репутация, промыслы и профессия.",
        "✅ Сохраняются: 🐾 питомцы, 🎖 титулы, 🏅 достижения.\n",
    ]

    if REBIRTH_STARTER_JOBS:
        lines.append("🔓 <b>Ветки, открываемые перерождениями:</b>")
        for req, job_key in sorted(REBIRTH_STARTER_JOBS.items()):
            mark = "✅" if rebirths >= req else "🔒"
            lines.append(f"  {mark} {req} перер. — «{JOBS[job_key]['name']}»")

    text = "\n".join(lines)

    if can:
        builder = InlineKeyboardBuilder()
        builder.button(text="✨ Переродиться!", callback_data="rebirth_confirm")
        await message.answer(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text + f"\n\n{why}")


@dp.callback_query(F.data == "rebirth_confirm")
async def cb_rebirth_confirm(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    await callback.answer()
    success, text = do_rebirth(user)
    await callback.message.edit_text(text)

ASCENSION_ITEMS = {
    "shard_of_time": {
        "name": "⏳ Осколок Времени", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "xp", "base_bonus": 8,
        "description": "Замедляет время вокруг тебя, ускоряя обучение.",
        "weight": 35,
    },
    "coin_of_eternity": {
        "name": "🪙 Монета Вечности", "rarity": "rare", "rarity_label": "🔵 Редкий",
        "bonus_type": "coins", "base_bonus": 8,
        "description": "Никогда не тускнеет и не заканчивается.",
        "weight": 35,
    },
    "eye_of_fate": {
        "name": "👁 Око Судьбы", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "luck", "base_bonus": 14,
        "description": "Видит все возможные исходы одновременно.",
        "weight": 18,
    },
    "heart_of_star": {
        "name": "⭐ Сердце Звезды", "rarity": "epic", "rarity_label": "🟣 Эпик",
        "bonus_type": "both", "base_bonus": 12,
        "description": "Осколок погасшей сверхновой.",
        "weight": 15,
    },
    "crown_of_ascension": {
        "name": "👑 Корона Вознесения", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "base_bonus": 25,
        "description": "Носят только те, кто прошёл цикл перерождений много раз.",
        "weight": 4,
    },
    "core_of_infinity": {
        "name": "♾ Ядро Бесконечности", "rarity": "legendary", "rarity_label": "🟡 Легендарный",
        "bonus_type": "both", "base_bonus": 30,
        "description": "Абсолютный артефакт цикла перерождений.",
        "weight": 2,
    },
}
ASCENSION_RARITY_WEIGHTS_SUM = sum(v["weight"] for v in ASCENSION_ITEMS.values())


def get_ascension_items(user: dict) -> dict:
    import json
    raw = user.get("ascension_items", "") or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def save_ascension_items(user_id: int, items: dict):
    import json
    update_user(user_id, ascension_items=json.dumps(items))


def ascension_gacha_pull(user: dict) -> tuple[str, dict, bool]:
    keys = list(ASCENSION_ITEMS.keys())
    weights = [ASCENSION_ITEMS[k]["weight"] for k in keys]
    chosen_key = random.choices(keys, weights=weights, k=1)[0]
    chosen = ASCENSION_ITEMS[chosen_key]

    items = get_ascension_items(user)
    is_dup = chosen_key in items
    if is_dup:
        items[chosen_key] += 1
    else:
        items[chosen_key] = 1
        if not user.get("equipped_ascension_item"):
            update_user(user["user_id"], equipped_ascension_item=chosen_key)
    save_ascension_items(user["user_id"], items)
    return chosen_key, chosen, is_dup


def get_equipped_ascension_item_bonus(user: dict) -> tuple[int, int, int]:
    key = user.get("equipped_ascension_item", "")
    if not key or key not in ASCENSION_ITEMS:
        return 0, 0, 0
    item = ASCENSION_ITEMS[key]
    level = get_ascension_items(user).get(key, 1)
    bonus = item["base_bonus"] + (level - 1) * 2   # +2 за каждый дубликат

    if item["bonus_type"] == "coins":
        return bonus, 0, 0
    elif item["bonus_type"] == "xp":
        return 0, bonus, 0
    elif item["bonus_type"] == "luck":
        return 0, 0, bonus
    elif item["bonus_type"] == "both":
        return bonus, bonus, 0
    return 0, 0, 0


def build_ascension_gacha_text(user: dict) -> str:
    items = get_ascension_items(user)
    equipped = user.get("equipped_ascension_item", "")
    lines = [
        "🌌 <b>Гача Вознесения</b>\n",
        f"🌌 Кристаллов: <b>{user.get('ascension_crystals', 0)}</b>",
        f"💠 Цена крутки: <b>{ASCENSION_GACHA_PRICE}</b> кристаллов\n",
    ]
    if equipped and equipped in ASCENSION_ITEMS:
        it = ASCENSION_ITEMS[equipped]
        lvl = items.get(equipped, 1)
        lines.append(f"🔧 Экипирован: <b>{it['name']}</b> {it['rarity_label']} (ур. {lvl})\n")
    else:
        lines.append("🔧 Артефакт не экипирован.\n")
    lines.append("<i>Артефакты и кристаллы НЕ сбрасываются перерождением!</i>")
    return "\n".join(lines)


def get_ascension_gacha_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🌌 Крутить ({ASCENSION_GACHA_PRICE} 🌌)", callback_data="asc_gacha_pull")
    builder.button(text="📦 Мои артефакты", callback_data="asc_gacha_collection")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("asc_gacha"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in
                                  ("гача вознесения", "гача кристаллов", "гача кристалл")))
async def cmd_ascension_gacha(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_ascension_gacha_text(user), reply_markup=get_ascension_gacha_keyboard())


@dp.callback_query(F.data == "asc_gacha_pull")
async def cb_ascension_gacha_pull(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    if user.get("ascension_crystals", 0) < ASCENSION_GACHA_PRICE:
        await callback.answer(
            f"❌ Нужно {ASCENSION_GACHA_PRICE} кристаллов, есть {user.get('ascension_crystals', 0)}",
            show_alert=True
        )
        return

    update_user(callback.from_user.id, ascension_crystals=user["ascension_crystals"] - ASCENSION_GACHA_PRICE)
    key, item, is_dup = ascension_gacha_pull(user)
    updated = get_user(callback.from_user.id)
    level = get_ascension_items(updated).get(key, 1)

    await callback.answer()
    if is_dup:
        text = (
            f"🌌 Крутка!\n\n"
            f"🔄 Дубликат: <b>{item['name']}</b> {item['rarity_label']}\n"
            f"Уровень вырос до <b>{level}</b>!\n\n"
            f"🌌 Осталось кристаллов: <b>{updated['ascension_crystals']}</b>"
        )
    else:
        text = (
            f"🌌 Крутка!\n\n"
            f"🎉 <b>НОВЫЙ АРТЕФАКТ!</b>\n{item['name']} {item['rarity_label']}\n"
            f"<i>{item['description']}</i>\n\n"
            f"🌌 Осталось кристаллов: <b>{updated['ascension_crystals']}</b>"
        )
    await callback.message.answer(text)


@dp.callback_query(F.data == "asc_gacha_collection")
async def cb_ascension_collection(callback: CallbackQuery):
    user = get_user_safe(callback.from_user.id)
    items = get_ascension_items(user)
    equipped = user.get("equipped_ascension_item", "")

    if not items:
        await callback.answer()
        await callback.message.answer("📦 У тебя пока нет артефактов Вознесения.")
        return

    lines = ["📦 <b>Артефакты Вознесения</b>\n"]
    builder = InlineKeyboardBuilder()
    for key, level in items.items():
        if key not in ASCENSION_ITEMS:
            continue
        it = ASCENSION_ITEMS[key]
        mark = " ◀ экипирован" if key == equipped else ""
        lines.append(f"{'✅' if key == equipped else '•'} {it['name']} {it['rarity_label']}{mark} (ур. {level})")
        builder.button(text=f"🔧 {it['name'][:20]}", callback_data=f"asc_equip:{key}")
    builder.adjust(1)

    await callback.answer()
    await callback.message.answer("\n\n".join(lines), reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("asc_equip:"))
async def cb_ascension_equip(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    items = get_ascension_items(user)
    if key not in items:
        await callback.answer("У тебя нет этого артефакта!", show_alert=True)
        return
    update_user(callback.from_user.id, equipped_ascension_item=key)
    await callback.answer(f"✅ Экипирован: {ASCENSION_ITEMS[key]['name']}!", show_alert=True)

@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("коллекция", "альбом")))
async def cmd_collection(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    import json
    try:
        coll = json.loads(user.get("gather_collection", "") or "{}")
    except Exception:
        coll = {}
    lines = ["📦 <b>Коллекция ресурсов</b>\n"]
    for loc, label in (("hunting", "🏹 Охота"), ("fishing", "🎣 Рыбалка"), ("mining", "⛏ Шахта")):
        lines.append(f"━━━ {label} ━━━")
        for k, r in RESOURCES.items():
            if r["loc"] != loc:
                continue
            have = coll.get(k, 0)
            icon = "✅" if have > 0 else "❔"
            lines.append(f"{icon} {r['name']} — добыто всего: {have}")
    await message.answer("\n".join(lines))

TOOL_TIERS = {
    "mining": [
        {"name": "🪓 Деревянная кирка", "yield_bonus_pct": 10, "luck_bonus": 2, "req_level": 1,
         "recipe_coins": 200, "recipe_resources": {"stone": 5}},
        {"name": "🪨 Каменная кирка", "yield_bonus_pct": 18, "luck_bonus": 4, "req_level": 8,
         "recipe_coins": 500, "recipe_resources": {"stone": 15, "coal": 5}},
        {"name": "⛏ Железная кирка", "yield_bonus_pct": 28, "luck_bonus": 7, "req_level": 15,
         "recipe_coins": 1200, "recipe_resources": {"iron_ore": 10, "coal": 8}},
        {"name": "🟠 Медная кирка+", "yield_bonus_pct": 38, "luck_bonus": 10, "req_level": 25,
         "recipe_coins": 2500, "recipe_resources": {"copper_ore": 12, "iron_ore": 8}},
        {"name": "🔗 Серебряная кирка", "yield_bonus_pct": 50, "luck_bonus": 15, "req_level": 35,
         "recipe_coins": 4500, "recipe_resources": {"silver_ore": 12, "copper_ore": 10}},
        {"name": "🟡 Золотая кирка", "yield_bonus_pct": 65, "luck_bonus": 20, "req_level": 50,
         "recipe_coins": 8000, "recipe_resources": {"gold_ore": 12, "silver_ore": 10}},
        {"name": "⚪ Платиновая кирка", "yield_bonus_pct": 85, "luck_bonus": 30, "req_level": 70,
         "recipe_coins": 15000, "recipe_resources": {"platinum_ore": 10, "diamond": 5}},
        {"name": "💎 Алмазная кирка", "yield_bonus_pct": 110, "luck_bonus": 45, "req_level": 90,
         "recipe_coins": 30000, "recipe_resources": {"mythril_shard": 8, "diamond": 8}},
        {"name": "🌌 Звёздная кирка", "yield_bonus_pct": 140, "luck_bonus": 60, "req_level": 100,
         "recipe_coins": 60000, "recipe_resources": {"star_core": 5, "mythril_shard": 10}},
    ],
    "fishing": [
        {"name": "🎣 Деревянная удочка", "yield_bonus_pct": 10, "luck_bonus": 2, "req_level": 1,
         "recipe_coins": 180, "recipe_resources": {"small_fish": 5}},
        {"name": "🎣 Простая леска+", "yield_bonus_pct": 18, "luck_bonus": 4, "req_level": 8,
         "recipe_coins": 480, "recipe_resources": {"carp": 12, "trout": 4}},
        {"name": "🎣 Укреплённая удочка", "yield_bonus_pct": 28, "luck_bonus": 7, "req_level": 15,
         "recipe_coins": 1100, "recipe_resources": {"trout": 10, "pearl": 5}},
        {"name": "🎣 Карбоновый спиннинг", "yield_bonus_pct": 38, "luck_bonus": 10, "req_level": 25,
         "recipe_coins": 2400, "recipe_resources": {"big_catfish": 8, "pearl": 6}},
        {"name": "🎣 Спиннинг мастера", "yield_bonus_pct": 50, "luck_bonus": 15, "req_level": 35,
         "recipe_coins": 4400, "recipe_resources": {"river_crystal": 10, "big_catfish": 6}},
        {"name": "🎣 Кристальная удочка", "yield_bonus_pct": 65, "luck_bonus": 20, "req_level": 50,
         "recipe_coins": 7800, "recipe_resources": {"turtle_shell": 8, "river_crystal": 10}},
        {"name": "🎣 Легендарный спиннинг", "yield_bonus_pct": 85, "luck_bonus": 30, "req_level": 70,
         "recipe_coins": 14500, "recipe_resources": {"golden_fish": 8, "turtle_shell": 8}},
        {"name": "🎣 Удочка кракена", "yield_bonus_pct": 110, "luck_bonus": 45, "req_level": 90,
         "recipe_coins": 29000, "recipe_resources": {"kraken_scale": 8, "golden_fish": 8}},
        {"name": "🌊✨ Священная удочка", "yield_bonus_pct": 140, "luck_bonus": 60, "req_level": 100,
         "recipe_coins": 58000, "recipe_resources": {"issykkul_pearl": 5, "kraken_scale": 10}},
    ],
    "hunting": [
        {"name": "🗡 Деревянный меч", "yield_bonus_pct": 10, "luck_bonus": 2, "req_level": 1,
         "recipe_coins": 200, "recipe_resources": {"bone": 3}},
        {"name": "🗡 Костяное копьё", "yield_bonus_pct": 18, "luck_bonus": 4, "req_level": 8,
         "recipe_coins": 500, "recipe_resources": {"bone": 12, "leather_hide": 4}},
        {"name": "⚔️ Железный меч", "yield_bonus_pct": 28, "luck_bonus": 7, "req_level": 15,
         "recipe_coins": 1200, "recipe_resources": {"leather_hide": 10, "wolf_fang": 3}},
        {"name": "🏹 Составной лук", "yield_bonus_pct": 38, "luck_bonus": 10, "req_level": 25,
         "recipe_coins": 2500, "recipe_resources": {"wolf_fang": 10, "eagle_feather": 6}},
        {"name": "⚔️ Клинок кочевника", "yield_bonus_pct": 50, "luck_bonus": 15, "req_level": 35,
         "recipe_coins": 4500, "recipe_resources": {"eagle_feather": 12, "ibex_horn": 5}},
        {"name": "🏹 Лук горного стрелка", "yield_bonus_pct": 65, "luck_bonus": 20, "req_level": 50,
         "recipe_coins": 8000, "recipe_resources": {"ibex_horn": 10, "snow_pelt": 5}},
        {"name": "⚔️ Клинок снежного барса", "yield_bonus_pct": 85, "luck_bonus": 30, "req_level": 70,
         "recipe_coins": 15000, "recipe_resources": {"snow_pelt": 10, "golden_antler": 4}},
        {"name": "🏹 Лук золотого оленя", "yield_bonus_pct": 110, "luck_bonus": 45, "req_level": 90,
         "recipe_coins": 30000, "recipe_resources": {"golden_antler": 8, "manas_essence": 4}},
        {"name": "🐎✨ Клинок духа Манаса", "yield_bonus_pct": 140, "luck_bonus": 60, "req_level": 100,
         "recipe_coins": 60000, "recipe_resources": {"manas_essence": 8, "golden_antler": 10}},
    ],
}

def get_tool_level(user: dict, tool_type: str) -> int:
    return user.get(f"tool_level_{tool_type}", 0)

def get_current_tool(tool_type: str, level: int) -> dict | None:
    tiers = TOOL_TIERS[tool_type]
    if level <= 0 or level > len(tiers):
        return None
    return tiers[level - 1]

def do_upgrade_tool(user: dict, tool_type: str) -> tuple[bool, str]:
    if tool_type not in TOOL_TIERS:
        return False, "❌ Неизвестный тип инструмента."
    level = get_tool_level(user, tool_type)
    tiers = TOOL_TIERS[tool_type]
    if level >= len(tiers):
        return False, "✅ Инструмент уже максимального уровня!"

    next_tier = tiers[level]  # tiers[level] = уровень (level+1), т.к. индекс с 0
    if user["level"] < next_tier["req_level"]:
        return False, f"❌ Нужен игровой уровень <b>{next_tier['req_level']}</b>."
    if user["balance"] < next_tier["recipe_coins"]:
        return False, f"❌ Нужно <b>{next_tier['recipe_coins']}</b> монет."

    resources = get_resources(user)
    for res_key, need in next_tier["recipe_resources"].items():
        have = resources.get(res_key, 0)
        if have < need:
            res_name = RESOURCES.get(res_key, {}).get("name", res_key)
            return False, f"❌ Не хватает: {res_name} ({have}/{need})"

    for res_key, need in next_tier["recipe_resources"].items():
        resources[res_key] -= need
        if resources[res_key] <= 0:
            del resources[res_key]
    save_resources(user["user_id"], resources)

    new_level = level + 1
    update_user(
        user["user_id"],
        balance=user["balance"] - next_tier["recipe_coins"],
        **{f"tool_level_{tool_type}": new_level},
    )
    return True, (
        f"✅ Инструмент улучшен: <b>{next_tier['name']}</b> (ур. {new_level}/{len(tiers)})!\n"
        f"📈 Бонус добычи: +{next_tier['yield_bonus_pct']}% | 🍀 удача: +{next_tier['luck_bonus']}"
    )

def build_tools_text(user: dict) -> str:
    labels = {"mining": "⛏ Шахта", "fishing": "🎣 Рыбалка", "hunting": "🏹 Охота"}
    lines = ["🛠 <b>Мастерская — инструменты</b>\n"]
    for ttype, label in labels.items():
        level = get_tool_level(user, ttype)
        tiers = TOOL_TIERS[ttype]
        current = get_current_tool(ttype, level)
        lines.append(f"━━━ {label} ━━━")
        if current:
            lines.append(f"Текущий: <b>{current['name']}</b> (ур. {level}/{len(tiers)})\n"
                         f"  Бонус: +{current['yield_bonus_pct']}% добычи, +{current['luck_bonus']} удачи")
        else:
            lines.append("Инструмента пока нет.")
        if level < len(tiers):
            nxt = tiers[level]
            res_str = ", ".join(f"{RESOURCES[r]['name']} x{n}" for r, n in nxt["recipe_resources"].items())
            lock = "" if user["level"] >= nxt["req_level"] else f" 🔒 (нужен {nxt['req_level']} ур.)"
            lines.append(f"Следующий: <b>{nxt['name']}</b>{lock}\n  Цена: {nxt['recipe_coins']} мон. + {res_str}")
        else:
            lines.append("🏆 Максимальный уровень достигнут!")
        lines.append("")
    return "\n".join(lines)

def get_tools_keyboard(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {"mining": "⛏ Кирку", "fishing": "🎣 Удочку", "hunting": "🏹 Оружие"}
    for ttype, label in labels.items():
        level = get_tool_level(user, ttype)
        if level < len(TOOL_TIERS[ttype]):
            builder.button(text=f"⬆️ Улучшить {label}", callback_data=f"tool_upgrade:{ttype}")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("мастерская", "крафт", "craft", "инструменты", "мои инструменты")))
async def txt_tools_menu(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_tools_text(user), reply_markup=get_tools_keyboard(user))

@dp.callback_query(F.data.startswith("tool_upgrade:"))
async def cb_tool_upgrade(callback: CallbackQuery):
    ttype = callback.data.split(":")[1]
    user = get_user_safe(callback.from_user.id)
    success, text = do_upgrade_tool(user, ttype)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(build_tools_text(updated), reply_markup=get_tools_keyboard(updated))

# =====================================================================
# ТОЧКА ВХОДА
# =====================================================================
async def main():
    init_db()
    load_chats_from_db()
    ensure_faculty_rows()
    asyncio.create_task(auto_event_scheduler())
    asyncio.create_task(auto_world_boss_scheduler())
    print("✅ PostgreSQL БД инициализирована. Бот КТУ Манас запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())