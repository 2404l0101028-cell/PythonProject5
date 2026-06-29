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
WORK_COOLDOWN     = 60
WORK_ENERGY_COST  = 15
TRAIN_ENERGY_COST = 50

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ БОТА И ДИСПЕТЧЕРА
# =====================================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

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
        "min_reward":  30, "max_reward":  48,
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
        "req_skill":   ("charisma_level", 2),
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
        "req_skill":   ("charisma_level", 3),
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
        "req_skill":   ("charisma_level", 5),
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
}

STARTER_JOB_KEYS = ["intel_1", "balance_1", "money_1"]
JOB_NAME_TO_KEY = {data["name"]: key for key, data in JOBS.items()}

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

class UpgradeJobCallback(CallbackData, prefix="upjob"):
    job_key: str

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
        "skill_bonus": ("charisma_level", 1),
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
    "charisma_level": {
        "label":       "✨ Харизма",
        "cost_base":   500,
        "description": "Нужна для ветки Деньги. Требует 🍹 Шейкер.",
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
}


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
                    user_id               BIGINT PRIMARY KEY,
                    username              TEXT    DEFAULT '',
                    balance               INTEGER DEFAULT 0,
                    level                 INTEGER DEFAULT 1,
                    exp                   INTEGER DEFAULT 0,
                    job                   TEXT    DEFAULT 'Безработный',
                    last_work_time        INTEGER DEFAULT 0,

                    agility               INTEGER DEFAULT 1,
                    endurance             INTEGER DEFAULT 1,
                    charisma              INTEGER DEFAULT 1,
                    intellect             INTEGER DEFAULT 1,
                    luck                  INTEGER DEFAULT 1,

                    communication_level   INTEGER DEFAULT 1,
                    driving_level         INTEGER DEFAULT 0,
                    charisma_level        INTEGER DEFAULT 0,
                    organization_level    INTEGER DEFAULT 0,
                    management_level      INTEGER DEFAULT 0,

                    job_rank              INTEGER DEFAULT 1,

                    has_scooter            INTEGER DEFAULT 0,
                    has_shaker             INTEGER DEFAULT 0,
                    has_laptop             INTEGER DEFAULT 0,
                    has_professor_badge    INTEGER DEFAULT 0,
                    has_logistics_license  INTEGER DEFAULT 0,
                    has_import_license     INTEGER DEFAULT 0,
                    has_dean_seal          INTEGER DEFAULT 0,
                    has_business_plan      INTEGER DEFAULT 0,
                    has_franchise_contract INTEGER DEFAULT 0,

                    hp                    INTEGER DEFAULT 100,
                    energy                INTEGER DEFAULT 100,

                    has_psychology_book   INTEGER DEFAULT 0,
                    has_driving_license   INTEGER DEFAULT 0,
                    last_regen_time       INTEGER DEFAULT 0,
                    has_suit              INTEGER DEFAULT 0,

                    achievements          TEXT    DEFAULT ''
                )
            """)
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

            # Добавляем колонки если их нет (для старых БД)
            for col, definition in [
                ("username",     "TEXT DEFAULT ''"),
                ("achievements", "TEXT DEFAULT ''"),
                ("pet_id", "TEXT DEFAULT ''"),
                ("pet_bonus", "INTEGER DEFAULT 0"),
                ("reputation", "INTEGER DEFAULT 0"),
                ("active_event", "TEXT DEFAULT ''"),
                ("event_ends_at", "INTEGER DEFAULT 0"),
                ("pet_collection", "TEXT DEFAULT ''"),  # JSON строка {pet_id: bonus, ...}
                ("active_pet", "TEXT DEFAULT ''"),  # ключ активного пета
            ]:
                try:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                except Exception:
                    pass
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
    return 100 + user["endurance"] * 10

def get_max_energy(user: dict) -> int:
    return 100 + user["intellect"] * 10

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
        for key in STARTER_JOB_KEYS:
            d = JOBS[key]
            lines.append(
                f"🔹 <b>{d['name']}</b>\n"
                f"   💰 {d['min_reward']}–{d['max_reward']} мон. | "
                f"✨ {d['min_exp']}–{d['max_exp']} XP\n"
                f"   <i>{d['description']}</i>"
            )
        return "\n".join(lines)

    job_key = get_job_key(user)
    if not job_key:
        update_user(user["user_id"], job="Безработный")
        lines = ["⚠️ <b>Профессия сброшена</b> из-за обновления игры. Выбери заново:\n"]
        for key in STARTER_JOB_KEYS:
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
        for key in STARTER_JOB_KEYS:
            builder.button(
                text=JOBS[key]["name"][:50],
                callback_data=JobCallback(job_key=key).pack()
            )
        builder.adjust(1)
        return builder.as_markup()

    job_key = get_job_key(user)
    if not job_key:
        update_user(user["user_id"], job="Безработный")
        for key in STARTER_JOB_KEYS:
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
    if user["job"] == "Безработный":
        return False, "❌ Сначала выбери профессию через <b>💼 Профессии</b>!"

    now     = int(time.time())
    elapsed = now - user["last_work_time"]
    if elapsed < WORK_COOLDOWN:
        remaining = WORK_COOLDOWN - elapsed
        return False, f"⏳ Подожди ещё <b>{remaining}</b> сек."

    if user["energy"] < WORK_ENERGY_COST:
        max_e = get_max_energy(user)
        return False, (
            f"😴 Недостаточно энергии!\n"
            f"Нужно: <b>{WORK_ENERGY_COST} ⚡</b>, есть: <b>{user['energy']} ⚡</b> / {max_e}.\n"
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
        luck = user.get("luck", 1) + pet_luck
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
    new_energy  = max(0, user["energy"] - WORK_ENERGY_COST)

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

    quest_msgs = update_quest_progress(user["user_id"], "work")
    quest_msgs += update_quest_progress(user["user_id"], "earn", earned_coins)
    quest_block = ("\n\n" + "\n".join(quest_msgs)) if quest_msgs else ""

    if event_line:
        if "🔥" in event_line:
            change_reputation(user["user_id"], +1)
        elif "⚠️" in event_line:
            change_reputation(user["user_id"], -1)
    change_reputation(user["user_id"], +1)  # за работу всегда +1
    event_block = f"\n\n{event_prefix}{event_line}" if event_line else ""
    max_energy  = get_max_energy(user)

    return True, (
        f"🛠 Ты поработал как <b>{user['job']}</b>!"
        f"{event_block}\n\n"
        f"💰 Получено: <b>+{earned_coins}</b> монет\n"
        f"✨ Опыт: <b>+{earned_exp}</b>  (всего: {user['exp']} / {xp_needed(user['level'])})\n"
        f"⚡ Энергия: <b>{new_energy}</b> / {max_energy}  (-{WORK_ENERGY_COST})\n"
        f"📊 Итого монет: <b>{user['balance']}</b>"
        f"{level_block}"
        f"{ach_block}"
        f"{quest_block}"
    )

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
    "agility":   {"name": "🤸 Акробатика",            "stat_label": "🏃 Ловкость",     "active": False},
    "charisma":  {"name": "🎤 Публичное выступление", "stat_label": "✨ Харизма",       "active": False},
}

def build_training_text(user: dict) -> str:
    max_energy = get_max_energy(user)
    return (
        f"🏋️ <b>Тренировки</b>\n\n"
        f"⚡ Энергия: <b>{user['energy']}</b> / {max_energy}\n\n"
        f"Тренировки тратят <b>{TRAIN_ENERGY_COST} ⚡</b> и прокачивают характеристики.\n"
        f"<i>⚡ Энергия восстанавливается только расходниками из Магазина!</i>"
    )

def get_training_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"📖 Почитать книгу  (-{TRAIN_ENERGY_COST} ⚡) → +1 🧠 Интеллект",
        callback_data=TrainCallback(stat="intellect").pack()
    )
    builder.button(
        text=f"🏃 Пробежка  (-{TRAIN_ENERGY_COST} ⚡) → +1 💪 Выносливость",
        callback_data=TrainCallback(stat="endurance").pack()
    )
    builder.button(
        text="🤸 Акробатика  (-50 ⚡) → +1 🏃 Ловкость  [Скоро]",
        callback_data=TrainCallback(stat="agility").pack()
    )
    builder.button(
        text="🎤 Выступление  (-50 ⚡) → +1 ✨ Харизма  [Скоро]",
        callback_data=TrainCallback(stat="charisma").pack()
    )
    builder.adjust(1)
    return builder.as_markup()

def do_train(user: dict, stat: str) -> tuple[bool, str]:
    cfg = TRAIN_CONFIG.get(stat)
    if not cfg:
        return False, "❌ Неизвестная тренировка."
    if not cfg["active"]:
        return False, f"🚧 <b>{cfg['name']}</b> пока в разработке. Скоро появится!"
    if user["energy"] < TRAIN_ENERGY_COST:
        return False, (
            f"😴 Недостаточно энергии!\n"
            f"Нужно: <b>{TRAIN_ENERGY_COST} ⚡</b>, есть: <b>{user['energy']} ⚡</b>.\n"
            f"Купи расходник в 🛒 Магазине."
        )
    new_energy = max(0, user["energy"] - TRAIN_ENERGY_COST)
    new_stat   = user[stat] + 1
    update_user(user["user_id"], energy=new_energy, **{stat: new_stat})
    quest_msgs = update_quest_progress(user["user_id"], "train")
    updated    = {**user, stat: new_stat, "energy": new_energy}
    max_energy = get_max_energy(updated)
    return True, (
        f"✅ <b>{cfg['name']}</b> завершена!\n\n"
        f"{cfg['stat_label']}: <b>+1</b> → {new_stat}\n"
        f"⚡ Энергия: <b>{new_energy}</b> / {max_energy}  (-{TRAIN_ENERGY_COST})"
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

def get_shop_food_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, item in CONSUMABLES.items():
        builder.button(text=f"{item['name']} — {item['price']} монет", callback_data=f"consume:{key}")
    builder.button(text="◀ Назад", callback_data="shop_back")
    builder.adjust(1)
    return builder.as_markup()


def do_buy_item(user: dict, item_key: str) -> tuple[bool, str]:
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return False, "❌ Такого товара нет."
    if user.get(item["flag"]):
        return False, f"У тебя уже есть {item['name']}!"
    _, _, _, ev_discount = get_event_multipliers()
    base_price = int(item["price"] * (1 - ev_discount / 100))
    actual_price = apply_rep_to_price(user, base_price)
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


def do_use_consumable(user: dict, item_key: str) -> tuple[bool, str]:
    item = CONSUMABLES.get(item_key)
    if not item:
        return False, "❌ Такого предмета нет."
    _, _, _, ev_discount = get_event_multipliers()
    base_price = int(item["price"] * (1 - ev_discount / 100))
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
    new_hp     = min(max_hp,     old_hp     + item["hp"])
    new_energy = min(max_energy, old_energy + item["energy"])
    new_balance = user["balance"] - actual_price
    update_user(user["user_id"], hp=new_hp, energy=new_energy, balance=new_balance)
    update_quest_progress(user["user_id"], "spend", item["price"])

    gained_hp     = new_hp     - old_hp
    gained_energy = new_energy - old_energy
    lines = [f"✅ Использован {item['name']}!"]
    if gained_hp     > 0: lines.append(f"❤️ HP:     +{gained_hp} → {new_hp} / {max_hp}")
    if gained_energy > 0: lines.append(f"⚡ Энергия: +{gained_energy} → {new_energy} / {max_energy}")
    if gained_hp == 0 and gained_energy == 0:
        lines.append("ℹ️ Ресурсы уже на максимуме — предмет потрачен впустую!")
    lines.append(f"💰 Потрачено: {item['price']} монет")
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
        f"⭐ Уровень: <b>{lvl}</b>\n"
        f"⭐ Репутация:     <b>{rep}</b> ({rep_title})\n"                                                               
        f"✨ Опыт: <b>{user['exp']}</b> / {needed_xp}\n"
        f"💰 Баланс: <b>{user['balance']}</b> монет\n\n"
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
        ],
        resize_keyboard=True,
        persistent=True,
    )

# =====================================================================
# БИРЖА
# =====================================================================
STOCK_MIN_BET = 100
STOCK_OUTCOMES = ["ап"] * 18 + ["давн"] * 18 + ["нейтрал"] * 2

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
        new_balance = user["balance"] + bet
        update_user(user["user_id"], balance=new_balance)
        change_reputation(user["user_id"], +1)
        update_quest_progress(user["user_id"], "stock")
        updated = get_user(user["user_id"])
        if updated:
            check_and_grant_achievements(updated)
        phrase = random.choice(STOCK_WIN_PHRASES)
        text = (
            f"📊 <b>Рынок пришёл в движение!</b>\n"
            f"График пошёл: <b>{market_label}</b>\n\n"
            f"🎉 <b>Вы угадали тренд!</b>\n"
            f"{phrase}\n\n"
            f"💰 Выигрыш: <b>+{bet}</b> монет\n"
            f"📈 Баланс: <b>{new_balance}</b> монет"
        )
    else:
        new_balance = user["balance"] - bet
        update_user(user["user_id"], balance=new_balance)
        change_reputation(user["user_id"], -1)
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
            "<b>Тренировки</b> — прокачать Интеллект/Выносливость\n"
            "<b>Навыки</b> — Коммуникация, Вождение, Харизма и др.\n"
            "<b>Магазин</b> — снаряжение и еда\n"
            "<b>Работа</b> — отработать смену (+монеты, +XP)\n\n"
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
            "/top — топ-10 богачей\n"
            "/my_place — твоё место в рейтинге"
        ),
    },
    "games": {
        "label": "🎮 Игры и дуэли",
        "text": (
            "🎮 <b>Игры</b>\n\n"
            "<b>дуэль @username 500</b> — дуэль на монеты\n"
            "<b>кости @username 500</b> — бросок кубиков\n"
            f"<b>слоты [сумма]</b> — слоты (мин. 50 монет)\n"
            f"<b>блекджек [сумма]</b> — блекджек (мин. 50 монет)\n"
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
            f"  Обычная: 2000 монет\n"
            f"  Премиум: 3500 монет (выше шанс редких)\n"
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
    update_user(winner_id, balance=new_bal)

    await message.answer(
        f"🏆 Все остальные сбросили карты!\n\n"
        f"🥇 Победитель: <b>{winner['name']}</b>\n"
        f"💰 Выигрыш: <b>{game.pot}</b> монет\n"
        f"💳 Новый баланс: <b>{new_bal}</b> монет"
    )
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
            winners_text.append(
                f"🥇 <b>{game.players[uid]['name']}</b> "
                f"выигрывает <b>{prize}</b> монет! "
                f"(баланс: {new_bal})"
            )

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
@dp.message(Command("start"), F.chat.type == "private")
async def cmd_start_private(message: Message):
    get_user_safe(message.from_user.id)
    await message.answer(
        f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
        "Добро пожаловать в игру «МанасWorker»! Используй меню ниже.",
        reply_markup=get_main_menu()
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
    await message.answer(build_training_text(user), reply_markup=get_training_keyboard())

@dp.message(F.text == "🧠 Навыки", F.chat.type == "private")
async def btn_skills_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    text, kb = build_skills_text(user)
    await message.answer(text, reply_markup=kb)

@dp.message(F.text == "🛒 Магазин", F.chat.type == "private")
async def btn_shop_private(message: Message):
    user = get_user_safe(message.from_user.id, message.from_user.username or message.from_user.full_name)
    await message.answer(build_shop_text(user), reply_markup=get_shop_keyboard())


def _is(text: str, *variants: str) -> bool:
    if not text:
        return False
    return text.strip().lower() in {v.lower() for v in variants}


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
            F.text.func(lambda t: t and _is(t, "профиль", "profile")))
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
        reply_markup=get_training_keyboard()
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
    if job_key not in STARTER_JOB_KEYS:
        await callback.answer("❌ Нельзя начать с этой профессии.", show_alert=True)
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
    user  = get_user_safe(callback.from_user.id)
    lines = ["🍔 <b>Еда и расходники</b>\n"]
    for item in CONSUMABLES.values():
        effects = []
        if item["hp"] > 0: effects.append(f"+{min(item['hp'],9999)} HP")
        if item["energy"] > 0: effects.append(f"+{min(item['energy'],9999)} ⚡")
        if item["hp"] >= 9999 and item["energy"] >= 9999: effects = ["полное восстановление"]
        lines.append(f"{item['name']} — <b>{item['price']} монет</b>  ({', '.join(effects)})\n  <i>{item['description']}</i>")
    lines.append(f"\n💰 Баланс: <b>{user['balance']}</b> монет")
    await callback.answer()
    await callback.message.edit_text("\n".join(lines), reply_markup=get_shop_food_keyboard())

@dp.callback_query(F.data.startswith("consume:"))
async def callback_use_consumable(callback: CallbackQuery):
    item_key = callback.data.split(":")[1]
    user     = get_user_safe(callback.from_user.id)
    success, text = do_use_consumable(user, item_key)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(
            build_shop_text(updated),
            reply_markup=get_shop_keyboard()
        )


@dp.callback_query(TrainCallback.filter())
async def callback_train(callback: CallbackQuery, callback_data: TrainCallback):
    user    = get_user_safe(callback.from_user.id)
    success, text = do_train(user, callback_data.stat)
    await callback.answer()
    await callback.message.answer(text)
    if success:
        updated = get_user(callback.from_user.id)
        await callback.message.edit_text(
            build_training_text(updated),
            reply_markup=get_training_keyboard()
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
        "communication_level", "driving_level", "charisma_level",
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

    new_winner_bal = winner_user["balance"] + bet
    new_loser_bal  = max(0, loser_user["balance"] - bet)
    update_user(winner_id, balance=new_winner_bal)
    update_user(loser_id,  balance=new_loser_bal)
    change_reputation(winner_id, +3)
    change_reputation(loser_id, -2)

    del active_duels[chat_id]

    # Проверяем ачивки победителя
    updated_winner = get_user(winner_id)
    check_and_grant_achievements(updated_winner)
    update_quest_progress(winner_id, "duel_win")

    await bot.send_message(chat_id,
        f"🏆 <b>ПОБЕДИТЕЛЬ — {winner_name}!</b>\n\n"
        f"⚔️ {c_power} vs {t_power}\n\n"
        f"💰 {winner_name} получает <b>+{bet}</b> монет → {new_winner_bal}\n"
        f"💸 {loser_name} теряет <b>-{bet}</b> монет → {new_loser_bal}"
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


@dp.message(Command("gacha"))
@dp.message(F.text.func(lambda t: t and t.strip().lower() in ("гача", "питомец", "gacha")))
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
    price = PET_GACHA_PREMIUM_PRICE if is_premium else PET_GACHA_PRICE

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

def change_reputation(user_id: int, amount: int) -> tuple[int, int]:
    user = get_user(user_id)
    if not user:
        return 0, 0
    old_rep = user.get("reputation", 0)
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
        f"━━━ Как растёт репутация ━━━\n"
        f"✅ Работа: +1\n"
        f"✅ Победа в дуэли: +3\n"
        f"✅ Выполнение квеста: +2\n"
        f"❌ Поражение в дуэли: -2\n"
        f"❌ Проигрыш на бирже: -1\n"
        f"❌ Негативное событие на работе: -1"
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
        loser_id,  loser_name  = t_id, t_name
        winner_bal = challenger["balance"]
        loser_bal  = target["balance"]
    else:
        winner_id, winner_name = t_id, t_name
        loser_id,  loser_name  = c_id, c_name
        winner_bal = target["balance"]
        loser_bal  = challenger["balance"]

    new_winner_bal = winner_bal + bet
    new_loser_bal  = max(0, loser_bal - bet)
    update_user(winner_id, balance=new_winner_bal)
    update_user(loser_id,  balance=new_loser_bal)

    change_reputation(winner_id, +2)
    change_reputation(loser_id,  -1)

    await bot.send_message(chat_id,
        f"🏆 <b>ПОБЕДИТЕЛЬ — {winner_name}!</b>\n\n"
        f"💰 +{bet} монет → баланс: {new_winner_bal}\n"
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

    winnings    = bet * multiplier
    profit      = winnings - bet
    new_balance = user["balance"] - bet + winnings
    update_user(uid, balance=new_balance)

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
    user_id = game["user_id"]
    p_val   = bj_hand_value(game["player"])
    d_val   = bj_hand_value(game["dealer"])
    bet     = game["bet"]
    balance = game["balance"]

    # Добиваем дилера до 17+
    while bj_hand_value(game["dealer"]) < 17:
        game["dealer"].append(game["deck"].pop())
    d_val = bj_hand_value(game["dealer"])

    p_bj = (len(game["player"]) == 2 and p_val == 21)
    d_bj = (len(game["dealer"]) == 2 and d_val == 21)

    if p_bj and not d_bj:
        prize   = int(bet * 1.5)
        result  = f"🃏 <b>БЛЕКДЖЕК!</b> +{prize} монет"
        net     = prize
        change_reputation(user_id, +2)
    elif p_val > 21:
        prize   = 0
        result  = f"💥 <b>Перебор ({p_val})!</b> Проигрыш -{bet} монет"
        net     = -bet
        change_reputation(user_id, -1)
    elif d_val > 21:
        prize   = bet
        result  = f"🎉 <b>Дилер перебрал ({d_val})!</b> +{bet} монет"
        net     = prize
        change_reputation(user_id, +1)
    elif p_val > d_val:
        prize   = bet
        result  = f"🏆 <b>Победа! ({p_val} vs {d_val})</b> +{bet} монет"
        net     = prize
        change_reputation(user_id, +1)
    elif p_val < d_val:
        prize   = 0
        result  = f"😢 <b>Проигрыш ({p_val} vs {d_val})</b> -{bet} монет"
        net     = -bet
        change_reputation(user_id, -1)
    else:
        prize   = 0
        result  = f"🤝 <b>Ничья ({p_val})</b> — ставка возвращена"
        net     = 0

    new_balance = balance + net
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
# =====================================================================
# ТОЧКА ВХОДА
# =====================================================================
async def main():
    init_db()
    load_chats_from_db()
    asyncio.create_task(auto_event_scheduler())
    print("✅ PostgreSQL БД инициализирована. Бот КТУ Манас запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())