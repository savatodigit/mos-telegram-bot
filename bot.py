import asyncio
import logging
import re
import random
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ИМПОРТ БАЗЫ ДАННЫХ ТЕСТОВ ====================
try:
    from database_lab import LabTestsDB
    lab_tests_db = LabTestsDB()
    TESTS_AVAILABLE = True
    logger.info("✅ База данных тестов подключена")
except ImportError:
    lab_tests_db = None
    TESTS_AVAILABLE = False
    logger.warning("⚠️ database_lab.py не найден, тестирование будет недоступно")

# ==================== КОНФИГУРАЦИЯ ТЕСТОВ ====================
# Настройки для каждой лабораторной работы
TEST_SETTINGS = {
    1:  {"num_questions": 50, "threshold": 40},
    2:  {"num_questions": 50, "threshold": 40},
    7:  {"num_questions": 70, "threshold": 60},
    8:  {"num_questions": 40, "threshold": 35},
    9:  {"num_questions": 40, "threshold": 35},
    10: {"num_questions": 40, "threshold": 35},
    11: {"num_questions": 50, "threshold": 40}, 
    12: {"num_questions": 50, "threshold": 40},
    13: {"num_questions": 50, "threshold": 40},
    14: {"num_questions": 50, "threshold": 40},  
    15: {"num_questions": 30, "threshold": 25},  
    17: {"num_questions": 30, "threshold": 25},
}

# ==================== ИМПОРТ ВСЕХ ТЕСТОВ ====================
TESTS_CONFIG = {}
LAB_NUMBERS = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]

for lr_num in LAB_NUMBERS:
    try:
        module = __import__(f'tests.test_lr{lr_num}', fromlist=['get_test_questions_lr{lr_num}', 'check_answer', 'calculate_result'])
        
        # Получаем настройки из TEST_SETTINGS
        settings = TEST_SETTINGS.get(lr_num, {"num_questions": 50, "threshold": 40})
        
        TESTS_CONFIG[lr_num] = {
            'available': True,
            'get_questions': getattr(module, f'get_test_questions_lr{lr_num}'),
            'check_answer': getattr(module, 'check_answer'),
            'calculate_result': getattr(module, 'calculate_result'),
            'num_questions': settings['num_questions'],
            'threshold': settings['threshold']
        }
        logger.info(f"✅ Тест ЛР №{lr_num} загружен ({settings['num_questions']} вопросов, порог {settings['threshold']})")
    except Exception as e:
        TESTS_CONFIG[lr_num] = {
            'available': False,
            'get_questions': lambda n=50: [],
            'check_answer': lambda q, a: False,
            'calculate_result': lambda c, t=50: {"correct": c, "total": t, "percentage": 0, "passed": False, "threshold": 40},
            'num_questions': 50,
            'threshold': 40
        }
        logger.warning(f"⚠️ Тест ЛР №{lr_num} не загружен: {e}")
# ==================== СОСТОЯНИЯ FSM ====================
class StudentForm(StatesGroup):
    main_menu = State()
    waiting_for_surname = State()
    select_variant = State()
    has_dbk = State()
    lat_start = State()
    lon_start = State()
    lat_end = State()
    lon_end = State()
    confirm = State()
    enter_variant_for_labs = State()
    enter_variant_for_course = State()
    # Состояния для тестирования
    test_enter_variant = State()
    test_select_lab = State()
    test_question_current = State()

# ==================== КЛАВИАТУРЫ ====================
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧭 Сбор данных ДБК")],
        [KeyboardButton(text="🔢 Узнать номер варианта")],
        [KeyboardButton(text="📋 Задание: лабораторные")],
        [KeyboardButton(text="📚 Задание: курсовой")],
        [KeyboardButton(text="📄 Бланки лабораторных")],
        [KeyboardButton(text="📖 Методические материалы")],
        [KeyboardButton(text="📝 Пройти тест по ЛР")],
        [KeyboardButton(text="🏠 В начало")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

yes_no_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Есть ДБК"), KeyboardButton(text="❌ Нет ДБК")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

empty_kb = ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)

lab_select_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="ЛР №1"), KeyboardButton(text="ЛР №2")],
        [KeyboardButton(text="ЛР №7"), KeyboardButton(text="ЛР №8")],
        [KeyboardButton(text="ЛР №9"), KeyboardButton(text="ЛР №10")],
        [KeyboardButton(text="ЛР №11"), KeyboardButton(text="ЛР №12")],
        [KeyboardButton(text="ЛР №13"), KeyboardButton(text="ЛР №14")],
        [KeyboardButton(text="ЛР №15"), KeyboardButton(text="ЛР №17")],
        [KeyboardButton(text="🏠 В меню")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# ==================== БАЗА ДАННЫХ СТУДЕНТОВ ====================
async def init_database():
    async with aiosqlite.connect("students.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surname TEXT NOT NULL,
            variant INTEGER NOT NULL,
            has_dbk BOOLEAN NOT NULL DEFAULT 0,
            lat_start TEXT,
            lon_start TEXT,
            lat_end TEXT,
            lon_end TEXT,
            timestamp TEXT NOT NULL
        )
        """)
        cursor = await db.execute("SELECT COUNT(*) FROM students")
        count = await cursor.fetchone()
        if count[0] == 0 and os.path.exists("students.txt"):
            with open("students.txt", "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    surname = parts[0].strip()
                    try:
                        variant = int(parts[1])
                        await db.execute(
                            "INSERT INTO students (surname, variant, has_dbk, timestamp) VALUES (?, ?, ?, ?)",
                            (surname, variant, False, datetime.now().isoformat())
                        )
                    except ValueError:
                        continue
            await db.commit()
            logger.info(f"✅ Загружено {len(lines)} студентов из students.txt")
        await db.commit()

async def save_coordinates(data: dict):
    async with aiosqlite.connect("students.db") as db:
        await db.execute("""
        UPDATE students
        SET has_dbk = 1, lat_start = ?, lon_start = ?, lat_end = ?, lon_end = ?, timestamp = ?
        WHERE surname = ? AND variant = ?
        """, (
            data['lat_start'], data['lon_start'],
            data['lat_end'], data['lon_end'],
            datetime.now().isoformat(),
            data['surname'],
            data['variant']
        ))
        await db.commit()

async def save_no_dbk(surname: str, variant: int):
    async with aiosqlite.connect("students.db") as db:
        await db.execute(
            "UPDATE students SET has_dbk = 1, lat_start = NULL, lon_start = NULL, lat_end = NULL, lon_end = NULL, timestamp = ? WHERE surname = ? AND variant = ?",
            (datetime.now().isoformat(), surname, variant)
        )
        await db.commit()

async def get_all_students():
    async with aiosqlite.connect("students.db") as db:
        cursor = await db.execute("""
        SELECT surname, variant FROM students ORDER BY variant ASC
        """)
        return await cursor.fetchall()

# ==================== ВАЛИДАЦИЯ КООРДИНАТ ====================
def validate_latitude(s: str):
    m = re.fullmatch(r'(\d{1,2})°(\d{1,2}(?:\.\d+)?)\'\s*([NSns])', s.strip())
    if not m:
        return False, "❌ Неверный формат. Пример: `59°56.0' N`"
    deg, minutes, hem = int(m[1]), float(m[2]), m[3].upper()
    if not (0 <= deg <= 90):
        return False, "❌ Градусы широты должны быть 0–90"
    if not (0 <= minutes < 60):
        return False, "❌ Минуты должны быть 0.0–59.9"
    if deg == 90 and minutes > 0:
        return False, "❌ На 90° минуты должны быть 0.0"
    return True, f"{deg}°{minutes:.1f}' {hem}"

def validate_longitude(s: str):
    m = re.fullmatch(r'(\d{1,3})°(\d{1,2}(?:\.\d+)?)\'\s*([EWew])', s.strip())
    if not m:
        return False, "❌ Неверный формат. Пример: `030°15.5' E`"
    deg, minutes, hem = int(m[1]), float(m[2]), m[3].upper()
    if not (0 <= deg <= 180):
        return False, "❌ Градусы долготы должны быть 0–180"
    if not (0 <= minutes < 60):
        return False, "❌ Минуты должны быть 0.0–59.9"
    if deg == 180 and minutes > 0:
        return False, "❌ На 180° минуты должны быть 0.0"
    return True, f"{deg}°{minutes:.1f}' {hem}"

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ==================== КОМАНДА /start — ГЛАВНОЕ МЕНЮ ====================
@router.message(Command("start"))
@router.message(F.text == "🏠 В начало")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎓 Бот-помощник по дисциплине МОС\n\n"
        "Выберите нужную опцию:",
        reply_markup=main_menu_kb
    )
    await state.set_state(StudentForm.main_menu)

# ==================== 1. СБОР ДАННЫХ ДБК ====================
@router.message(StudentForm.main_menu, F.text == "🧭 Сбор данных ДБК")
async def menu_dbk(message: Message, state: FSMContext):
    await message.answer(
        "🧭 Сбор данных ДБК для курсового проекта по МОС.\n\n"
        "Введите вашу фамилию (как в списке группы):"
    )
    await state.set_state(StudentForm.waiting_for_surname)

@router.message(StudentForm.waiting_for_surname)
async def process_surname(message: Message, state: FSMContext):
    surname = message.text.strip().capitalize()
    async with aiosqlite.connect("students.db") as db:
        cursor = await db.execute(
            "SELECT surname, variant FROM students WHERE surname = ? COLLATE NOCASE ORDER BY variant ASC",
            (surname,)
        )
        matches = await cursor.fetchall()

    if not matches:
        await message.answer(
            f"❌ Фамилия '{surname}' не найдена в списке.\n\n"
            "Проверьте правильность написания или обратитесь к преподавателю.\n"
            "Введите фамилию ещё раз:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🏠 В начало")]],
                resize_keyboard=True
            )
        )
        return

    if len(matches) == 1:
        surname_db, variant = matches[0]
        await state.update_data(surname=surname_db, variant=variant)
        await message.answer(
            f"👤 Фамилия: {surname_db}\n🎓 Вариант: {variant}\n\n"
            "Есть ли у вас данные ДБК из курсового по ГВП?",
            reply_markup=yes_no_kb
        )
        await state.set_state(StudentForm.has_dbk)
        return

    buttons = []
    row = []
    for surname_db, variant in matches:
        btn_text = f"{surname_db} (в.{variant})"
        row.append(KeyboardButton(text=btn_text))
        if len(row) >= 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    select_kb = ReplyKeyboardMarkup(
        keyboard=buttons + [[KeyboardButton(text="🏠 В начало")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await state.update_data(potential_matches=matches)
    await message.answer(
        f"👥 Найдено {len(matches)} студентов с фамилией '{surname}'.\n"
        "Выберите свой вариант:",
        reply_markup=select_kb
    )
    await state.set_state(StudentForm.select_variant)

@router.message(StudentForm.select_variant)
async def process_variant_selection(message: Message, state: FSMContext):
    if message.text == "🏠 В начало":
        await cmd_start(message, state)
        return
    data = await state.get_data()
    matches = data.get('potential_matches', [])
    selected_text = message.text.strip()

    for surname_db, variant in matches:
        expected_text = f"{surname_db} (в.{variant})"
        if selected_text == expected_text:
            await state.update_data(surname=surname_db, variant=variant)
            await message.answer(
                f"✅ Выбран: {surname_db} (вариант {variant})\n\n"
                "Есть ли у вас данные ДБК из курсового по ГВП?",
                reply_markup=yes_no_kb
            )
            await state.set_state(StudentForm.has_dbk)
            return

    buttons = []
    row = []
    for surname_db, variant in matches:
        btn_text = f"{surname_db} (в.{variant})"
        row.append(KeyboardButton(text=btn_text))
        if len(row) >= 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    select_kb = ReplyKeyboardMarkup(
        keyboard=buttons + [[KeyboardButton(text="🏠 В начало")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "⚠️ Не удалось определить выбор. Выберите вариант из списка:",
        reply_markup=select_kb
    )

@router.message(StudentForm.has_dbk, F.text == "✅ Есть ДБК")
async def process_has_dbk_yes(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(has_dbk=True)
    await message.answer(
        "📍 Широта НАЧАЛЬНОЙ точки:\nФормат: `00°00.0' N/S`\nПример: `59°56.0' N`",
        parse_mode="Markdown",
        reply_markup=empty_kb
    )
    await state.set_state(StudentForm.lat_start)

@router.message(StudentForm.has_dbk, F.text == "❌ Нет ДБК")
async def process_has_dbk_no(message: Message, state: FSMContext):
    data = await state.get_data()
    await save_no_dbk(data['surname'], data['variant'])
    await message.answer(
        f"✅ Сохранено: {data['surname']} (вариант {data['variant']}) — ❌ Нет ДБК",
        reply_markup=main_menu_kb
    )
    await bot.send_message(
        ADMIN_USER_ID,
        f"🆕 {data['surname']} (в.{data['variant']}) — НЕТ ДБК"
    )
    await state.set_state(StudentForm.main_menu)

@router.message(StudentForm.has_dbk)
async def process_has_dbk_invalid(message: Message, state: FSMContext):
    if message.text == "🏠 В начало":
        await cmd_start(message, state)
        return
    await message.answer(
        "⚠️ Используйте кнопки ниже для выбора!",
        reply_markup=yes_no_kb
    )

@router.message(StudentForm.lat_start)
async def process_lat_start(message: Message, state: FSMContext):
    if message.text == "🏠 В начало":
        await cmd_start(message, state)
        return
    ok, res = validate_latitude(message.text)
    if not ok:
        await message.answer(f"{res}\nПопробуйте ещё раз:")
        return
    await state.update_data(lat_start=res)
    await message.answer("📍 Долгота НАЧАЛЬНОЙ точки:\nФормат: `000°00.0' E/W`\nПример: `030°15.5' E`", parse_mode="Markdown")
    await state.set_state(StudentForm.lon_start)

@router.message(StudentForm.lon_start)
async def process_lon_start(message: Message, state: FSMContext):
    if message.text == "🏠 В начало":
        await cmd_start(message, state)
        return
    ok, res = validate_longitude(message.text)
    if not ok:
        await message.answer(f"{res}\nПопробуйте ещё раз:")
        return
    await state.update_data(lon_start=res)
    await message.answer("📍 Широта КОНЕЧНОЙ точки:\nФормат: `00°00.0' N/S`")
    await state.set_state(StudentForm.lat_end)

@router.message(StudentForm.lat_end)
async def process_lat_end(message: Message, state: FSMContext):
    if message.text == "🏠 В начало":
        await cmd_start(message, state)
        return
    ok, res = validate_latitude(message.text)
    if not ok:
        await message.answer(f"{res}\nПопробуйте ещё раз:")
        return
    await state.update_data(lat_end=res)
    await message.answer("📍 Долгота КОНЕЧНОЙ точки:\nФормат: `000°00.0' E/W`")
    await state.set_state(StudentForm.lon_end)

@router.message(StudentForm.lon_end)
async def process_lon_end(message: Message, state: FSMContext):
    if message.text == "🏠 В начало":
        await cmd_start(message, state)
        return
    ok, res = validate_longitude(message.text)
    if not ok:
        await message.answer(f"{res}\nПопробуйте ещё раз:")
        return
    await state.update_data(lon_end=res)
    data = await state.get_data()
    summary = (
        f"🔍 Проверьте данные:\n\n"
        f"👤 {data['surname']} (вариант {data['variant']})\n\n"
        f"🧭 Начало: {data['lat_start']}, {data['lon_start']}\n"
        f"🏁 Конец: {data['lat_end']}, {data['lon_end']}\n\n"
        f"Всё верно?"
    )
    await message.answer(
        summary,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Верно", callback_data="confirm_yes"),
             InlineKeyboardButton(text="🔄 Заново", callback_data="confirm_no")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="to_menu")]
        ])
    )
    await state.set_state(StudentForm.confirm)

@router.callback_query(StudentForm.confirm)
async def process_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "to_menu":
        await callback.message.edit_text("🏠 Возвращаемся в главное меню...")
        await cmd_start(callback.message, state)
        return

    if callback.data == "confirm_no":
        await callback.message.edit_text("🔄 Введите фамилию:")
        await state.set_state(StudentForm.waiting_for_surname)
        return

    data = await state.get_data()
    await save_coordinates(data)

    await callback.message.edit_text(
        f"✅ Данные сохранены!\n{data['surname']} (в.{data['variant']})\n"
        f"Начало: {data['lat_start']}, {data['lon_start']}\n"
        f"Конец: {data['lat_end']}, {data['lon_end']}"
    )

    await bot.send_message(
        ADMIN_USER_ID,
        f"✅ {data['surname']} (в.{data['variant']})\n"
        f"Н: {data['lat_start']}, {data['lon_start']}\n"
        f"К: {data['lat_end']}, {data['lon_end']}"
    )

    await asyncio.sleep(2)
    await cmd_start(callback.message, state)

# ==================== 2. УЗНАТЬ НОМЕР ВАРИАНТА ====================
@router.message(StudentForm.main_menu, F.text == "🔢 Узнать номер варианта")
async def menu_get_variant(message: Message, state: FSMContext):
    students = await get_all_students()
    if not students:
        await message.answer("📭 Список студентов пуст.", reply_markup=main_menu_kb)
        return
    report = "📋 Полный список студентов и вариантов:\n\n"
    for surname, variant in students:
        report += f"{variant:2d}. {surname}\n"

    chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML", reply_markup=main_menu_kb)
        else:
            await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML")

# ==================== 3. ЗАДАНИЕ НА ЛАБОРАТОРНЫЕ ====================
@router.message(StudentForm.main_menu, F.text == "📋 Задание: лабораторные")
async def menu_labs(message: Message, state: FSMContext):
    await message.answer("📋 Введите номер вашего варианта:")
    await state.set_state(StudentForm.enter_variant_for_labs)

@router.message(StudentForm.enter_variant_for_labs)
async def process_lab_variant(message: Message, state: FSMContext):
    if message.text in ["🏠 В начало", "🧭 Сбор данных ДБК", "🔢 Узнать номер варианта",
                        "📋 Задание: лабораторные", "📚 Задание: курсовой",
                        "📄 Бланки лабораторных", "📖 Методические материалы", "📝 Пройти тест по ЛР"]:
        await cmd_start(message, state)
        return
    try:
        variant = int(message.text.strip())
        if not (1 <= variant <= 99):
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число от 1 до 99:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🏠 В начало")]],
                resize_keyboard=True
            )
        )
        return

    labs_dir = "labs_tasks"
    filename = f"Вариант_{variant:02d}.pdf"
    filepath = os.path.join(labs_dir, filename)

    if not os.path.exists(filepath):
        available = []
        if os.path.exists(labs_dir):
            available = [f for f in os.listdir(labs_dir) if f.lower().endswith('.pdf')]
        await message.answer(
            f"❌ Файл '{filename}' не найден в папке 'labs_tasks'.\n"
            f"Доступные файлы: {', '.join(available) if available else 'нет файлов'}",
            reply_markup=main_menu_kb
        )
        return

    await message.answer(f"✅ Задание лабораторной работы для варианта {variant}:")
    await message.answer_document(FSInputFile(filepath))
    await message.answer("📄 Задание получено. Выберите следующую опцию:", reply_markup=main_menu_kb)
    await state.set_state(StudentForm.main_menu)

# ==================== 4. ЗАДАНИЕ НА КУРСОВОЙ ====================
@router.message(StudentForm.main_menu, F.text == "📚 Задание: курсовой")
async def menu_course(message: Message, state: FSMContext):
    await message.answer("📚 Введите номер вашего варианта:")
    await state.set_state(StudentForm.enter_variant_for_course)

@router.message(StudentForm.enter_variant_for_course)
async def process_course_variant(message: Message, state: FSMContext):
    if message.text in ["🏠 В начало", "🧭 Сбор данных ДБК", "🔢 Узнать номер варианта",
                        "📋 Задание: лабораторные", "📚 Задание: курсовой",
                        "📄 Бланки лабораторных", "📖 Методические материалы", "📝 Пройти тест по ЛР"]:
        await cmd_start(message, state)
        return
    try:
        variant = int(message.text.strip())
        if not (1 <= variant <= 99):
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число от 1 до 99:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🏠 В начало")]],
                resize_keyboard=True
            )
        )
        return

    kurs_dir = "kurs_tasks"
    filename = f"Вариант_{variant:02d}.pdf"
    filepath = os.path.join(kurs_dir, filename)

    if not os.path.exists(filepath):
        available = []
        if os.path.exists(kurs_dir):
            available = [f for f in os.listdir(kurs_dir) if f.lower().endswith('.pdf')]
        await message.answer(
            f"❌ Файл '{filename}' не найден в папке 'kurs_tasks'.\n"
            f"Доступные файлы: {', '.join(available) if available else 'нет файлов'}",
            reply_markup=main_menu_kb
        )
        return

    await message.answer(f"✅ Задание курсового проекта для варианта {variant}:")
    await message.answer_document(FSInputFile(filepath))
    await message.answer("📄 Задание получено. Выберите следующую опцию:", reply_markup=main_menu_kb)
    await state.set_state(StudentForm.main_menu)

# ==================== 5. БЛАНКИ ЛАБОРАТОРНЫХ ====================
@router.message(StudentForm.main_menu, F.text == "📄 Бланки лабораторных")
async def menu_blanks(message: Message, state: FSMContext):
    blanks_dir = "labs_blanks"
    if not os.path.exists(blanks_dir):
        await message.answer(
            "⚠️ Папка 'labs_blanks' не найдена.\n"
            "Создайте папку и поместите туда файлы бланков.",
            reply_markup=main_menu_kb
        )
        return
    files = [f for f in os.listdir(blanks_dir) if f.lower().endswith(('.pdf', '.doc', '.docx', '.xlsx'))]
    if not files:
        await message.answer(
            "📭 В папке 'labs_blanks' не найдено файлов (.pdf, .doc, .docx)",
            reply_markup=main_menu_kb
        )
        return

    await message.answer(f"📄 Отправляю {len(files)} бланк(ов) лабораторных работ...")
    for filename in files[:10]:
        try:
            filepath = os.path.join(blanks_dir, filename)
            await message.answer_document(FSInputFile(filepath))
        except Exception as e:
            await message.answer(f"❌ Ошибка отправки {filename}: {str(e)}")

    await message.answer("✅ Все доступные бланки отправлены.", reply_markup=main_menu_kb)

# ==================== 6. МЕТОДИЧЕСКИЕ МАТЕРИАЛЫ ====================
@router.message(StudentForm.main_menu, F.text == "📖 Методические материалы")
async def menu_methods(message: Message, state: FSMContext):
    methods_dir = "methods"
    if not os.path.exists(methods_dir):
        await message.answer(
            "⚠️ Папка 'methods' не найдена.\n"
            "Создайте папку и поместите туда методические материалы.",
            reply_markup=main_menu_kb
        )
        return
    files = [f for f in os.listdir(methods_dir) if f.lower().endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx'))]
    if not files:
        await message.answer(
            "📭 В папке 'methods' не найдено файлов",
            reply_markup=main_menu_kb
        )
        return

    await message.answer(f"📖 Отправляю {len(files)} методический(их) материал(ов)...")
    for filename in files[:10]:
        try:
            filepath = os.path.join(methods_dir, filename)
            await message.answer_document(FSInputFile(filepath))
        except Exception as e:
            await message.answer(f"❌ Ошибка отправки {filename}: {str(e)}")

    await message.answer("✅ Материалы отправлены.", reply_markup=main_menu_kb)

# ==================== 7. ПРОЙТИ ТЕСТ ПО ЛР ====================
@router.message(StudentForm.main_menu, F.text == "📝 Пройти тест по ЛР")
async def menu_tests(message: Message, state: FSMContext):
    if not TESTS_AVAILABLE:
        await message.answer(
            "⚠️ Тестирование временно недоступно.\n"
            "Обратитесь к преподавателю.",
            reply_markup=main_menu_kb
        )
        return
    
    if not lab_tests_db.is_tests_enabled():
        await message.answer(
            "⛔ Тестирование в настоящее время ЗАКРЫТО.\n\n"
            "Тесты доступны только по команде преподавателя.\n"
            "Обратитесь к преподавателю для уточнения времени тестирования.",
            reply_markup=main_menu_kb
        )
        return
    
    await message.answer(
        "📝 Тестирование по лабораторным работам\n\n"
        "Введите номер вашего варианта (1-67):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🏠 В меню")]],
            resize_keyboard=True
        )
    )
    await state.set_state(StudentForm.test_enter_variant)

@router.message(StudentForm.test_enter_variant)
async def process_test_variant(message: Message, state: FSMContext):
    if message.text == "🏠 В меню":
        await cmd_start(message, state)
        return
    
    try:
        variant = int(message.text.strip())
        if not (1 <= variant <= 67):
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число от 1 до 67:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🏠 В меню")]],
                resize_keyboard=True
            )
        )
        return

    student = lab_tests_db.get_student_by_variant(variant)
    if not student:
        await message.answer(
            f"❌ Курсант с вариантом {variant} не найден в базе.\n"
            "Обратитесь к преподавателю.",
            reply_markup=main_menu_kb
        )
        await state.set_state(StudentForm.main_menu)
        return

    await state.update_data(student_id=student['id'], surname=student['surname'], variant=variant)

    await message.answer(
        f"✅ Курсант: {student['surname']} (вариант {variant})\n\n"
        "Выберите номер лабораторной работы для тестирования:",
        reply_markup=lab_select_kb
    )
    await state.set_state(StudentForm.test_select_lab)

@router.message(StudentForm.test_select_lab)
async def process_lab_selection(message: Message, state: FSMContext):
    if message.text == "🏠 В меню":
        await cmd_start(message, state)
        return
    
    lab_map = {
        "ЛР №1": 1, "ЛР №2": 2, "ЛР №7": 7, "ЛР №8": 8,
        "ЛР №9": 9, "ЛР №10": 10, "ЛР №11": 11, "ЛР №12": 12,
        "ЛР №13": 13, "ЛР №14": 14, "ЛР №15": 15, "ЛР №17": 17
    }

    lab_number = lab_map.get(message.text.strip())
    if not lab_number:
        await message.answer(
            "⚠️ Выберите лабораторную работу из списка:",
            reply_markup=lab_select_kb
        )
        return

    data = await state.get_data()
    student_id = data['student_id']

    results = lab_tests_db.get_student_results(student_id)
    if results['results'].get(f'lr_{lab_number}', 0) == 1:
        await message.answer(
            f"✅ У вас уже есть зачет по ЛР №{lab_number}!\n\n"
            "Выберите другую лабораторную работу:",
            reply_markup=lab_select_kb
        )
        return
    
    # Проверяем доступность теста для выбранной ЛР
    if TESTS_CONFIG.get(lab_number, {}).get('available', False):
        test_config = TESTS_CONFIG[lab_number]
        num_questions = test_config['num_questions']
        threshold = test_config['threshold']

        questions = test_config['get_questions'](num_questions=num_questions)
        await state.update_data(
            lab_number=lab_number,
            questions=questions,
            current_question=0,
            correct_count=0,
            check_answer_func=test_config['check_answer'],
            calculate_result_func=test_config['calculate_result'],
            num_questions=num_questions,
            threshold=threshold
        )
        
        q = questions[0]
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(q['options'])])
        
        await message.answer(
            f"📝 Тест по ЛР №{lab_number}\n"
            f"Вопрос 1 из {num_questions}\n\n"
            f"{q['question']}\n\n"
            f"{options_text}\n\n"
            "Введите номер правильного ответа (1-5):"
        )
        await state.set_state(StudentForm.test_question_current)
    else:
        await message.answer(
            f"⚠️ Тест по ЛР №{lab_number} находится в разработке.\n"
            f"Доступны тесты: {[str(k) for k, v in TESTS_CONFIG.items() if v.get('available', False)]}",
            reply_markup=lab_select_kb
        )

@router.message(StudentForm.test_question_current)
async def process_test_question(message: Message, state: FSMContext):
    if message.text == "🏠 В меню":
        await cmd_start(message, state)
        return
    
    data = await state.get_data()
    current_q = data['current_question']
    questions = data['questions']
    correct_count = data['correct_count']
    
    # ✅ Получаем настройки из state
    num_questions = data.get('num_questions', len(questions))
    threshold = data.get('threshold', 40)
    
    check_answer_func = data.get('check_answer_func', lambda q, a: False)
    calculate_result_func = data.get('calculate_result_func', lambda c, t=50: {"correct": c, "total": t, "percentage": 0, "passed": False, "threshold": 40})
    
    try:
        answer = int(message.text.strip())
        if not (1 <= answer <= 5):
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 5:")
        return
    
    q = questions[current_q]
    is_correct = check_answer_func(q, answer - 1)
    
    if is_correct:
        correct_count += 1
        feedback = "✅ Верно!"
    else:
        feedback = f"❌ Неверно. Правильный ответ: {q['correct'] + 1}"
    
    current_q += 1
    await state.update_data(current_question=current_q, correct_count=correct_count)
    
    if current_q >= len(questions):
        # ✅ Вызываем calculate_result с правильными параметрами
        result = calculate_result_func(
            correct_count=correct_count,
            total_count=len(questions),
            threshold=threshold
        )
        
        if TESTS_AVAILABLE and lab_tests_db:
            try:
                lab_tests_db.update_test_result(
                    data['student_id'], 
                    data['lab_number'], 
                    result['passed']
                )
                lab_tests_db.log_attempt(
                    data['student_id'],
                    data['variant'],
                    data['lab_number'],
                    len(questions),
                    correct_count,
                    result['passed']
                )
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения результата теста: {e}")
        
        status = "🎉 ЗАЧЕТ" if result['passed'] else "😔 НЕЗАЧЕТ"
        await message.answer(
            f"📊 Результаты теста по ЛР №{data['lab_number']}\n\n"
            f"{status}\n"
            f"Правильных ответов: {result['correct']} из {result['total']}\n"
            f"Процент: {result['percentage']:.1f}%\n"
            f"Порог прохождения: {result['threshold']} правильных ответов",
            reply_markup=main_menu_kb
        )
        await state.set_state(StudentForm.main_menu)
    else:
        # ✅ Показываем следующий вопрос
        q = questions[current_q]
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(q['options'])])
        
        await message.answer(
            f"{feedback}\n\n"
            f"Вопрос {current_q + 1} из {num_questions}\n\n"
            f"{q['question']}\n\n"
            f"{options_text}\n\n"
            "Введите номер правильного ответа (1-5):"
        )# ==================== АДМИН-КОМАНДЫ ====================
@router.message(Command("export"))
async def cmd_export(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ запрещён")
        return
    async with aiosqlite.connect("students.db") as db:
        cursor = await db.execute("""
            SELECT surname, variant, has_dbk, lat_start, lon_start, lat_end, lon_end 
            FROM students ORDER BY variant ASC
        """)
        students = await cursor.fetchall()

    if not students:
        await message.answer("📭 Нет данных")
        return

    report = "📊 Студенты:\n\n"
    for s in students:
        surname, variant, has_dbk, lat1, lon1, lat2, lon2 = s
        status = "✅ ДБК" if has_dbk and lat1 else "❌ Нет ДБК"
        report += f"{variant:2d}. {surname:15s} — {status}\n"
        if has_dbk and lat1:
            report += f"      Н: {lat1}, {lon1}\n"
            report += f"      К: {lat2}, {lon2}\n"
        report += "\n"

    chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
    for chunk in chunks:
        await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML")

@router.message(Command("tests_enable"))
async def cmd_tests_enable(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ запрещён. Только для преподавателя.")
        return
    
    if not TESTS_AVAILABLE:
        await message.answer("⚠️ База тестов недоступна")
        return
    
    lab_tests_db.enable_tests(message.from_user.id)
    status = lab_tests_db.get_test_status()
    
    await message.answer(
        "✅ Тестирование ВКЛЮЧЕНО!\n\n"
        f"Преподаватель: ID {status['enabled_by']}\n"
        f"Время: {status['enabled_at']}\n\n"
        "Теперь курсанты могут проходить тесты.",
        reply_markup=main_menu_kb
    )
    
    logger.info(f"🔔 Тестирование включено преподавателем ID {message.from_user.id}")

@router.message(Command("tests_disable"))
async def cmd_tests_disable(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ запрещён. Только для преподавателя.")
        return
    
    if not TESTS_AVAILABLE:
        await message.answer("⚠️ База тестов недоступна")
        return
    
    lab_tests_db.disable_tests(message.from_user.id)
    status = lab_tests_db.get_test_status()
    
    await message.answer(
        "⛔ Тестирование ВЫКЛЮЧЕНО!\n\n"
        f"Преподаватель: ID {status['disabled_by']}\n"
        f"Время: {status['disabled_at']}\n\n"
        "Курсанты больше не могут проходить тесты.",
        reply_markup=main_menu_kb
    )
    
    logger.info(f"🔕 Тестирование выключено преподавателем ID {message.from_user.id}")

@router.message(Command("tests_status"))
async def cmd_tests_status(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ запрещён. Только для преподавателя.")
        return
    
    if not TESTS_AVAILABLE:
        await message.answer("⚠️ База тестов недоступна")
        return
    
    status = lab_tests_db.get_test_status()
    
    if status['enabled']:
        status_text = "✅ ВКЛЮЧЕНО"
        details = f"Включено преподавателем ID {status['enabled_by']}\nВремя: {status['enabled_at']}"
    else:
        status_text = "⛔ ВЫКЛЮЧЕНО"
        details = f"Выключено преподавателем ID {status['disabled_by']}\nВремя: {status['disabled_at']}"
    
    available_tests = [str(k) for k, v in TESTS_CONFIG.items() if v.get('available', False)]
    
    await message.answer(
        f"📊 Статус тестирования: {status_text}\n\n"
        f"{details}\n\n"
        f"Доступные тесты: {', '.join(available_tests) if available_tests else 'нет'}\n\n"
        "Команды управления:\n"
        "/tests_enable — включить тестирование\n"
        "/tests_disable — выключить тестирование\n"
        "/tests_status — проверить статус"
    )

@router.message(Command("test_results"))
async def cmd_test_results(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ запрещён")
        return
    
    if not TESTS_AVAILABLE:
        await message.answer("⚠️ База тестов недоступна")
        return
    
    status = lab_tests_db.get_test_status()
    status_line = "✅ Тестирование ВКЛЮЧЕНО" if status['enabled'] else "⛔ Тестирование ВЫКЛЮЧЕНО"
    
    results = lab_tests_db.get_all_results()
    
    report = f"📊 Результаты тестирования по ЛР:\n{status_line}\n\n"
    lab_numbers = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]
    
    report += f"{'Фамилия':<15} {'Вар':<4}"
    for lr in lab_numbers:
        report += f" ЛР{lr:<2}"
    report += "\n" + "—" * 60 + "\n"
    
    for r in results:
        report += f"{r['surname']:<15} {r['variant']:<4}"
        for lr in lab_numbers:
            status = "✅" if r.get(f'lr_{lr}', 0) == 1 else "❌"
            report += f" {status}"
        report += "\n"
    
    chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
    for chunk in chunks:
        await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML")

# ==================== ЗАПУСК БОТА ====================
async def main():
    await init_database()
    logger.info("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    
    for folder in ["labs_tasks", "kurs_tasks", "labs_blanks", "methods"]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            logger.info(f"📁 Создана папка {folder}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())