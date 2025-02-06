import asyncio
import logging
import aiohttp
import nest_asyncio
import matplotlib.pyplot as plt

from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message
from io import BytesIO

nest_asyncio.apply()

logging.basicConfig(
    level=logging.INFO,  
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            logging.info(f"Получено сообщение от {event.from_user.id}: {event.text}")
        return await handler(event, data)

TOKEN = "%"
API_WEATHER = "%"
API_FOOD_SEARCH = "https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={}&json=true"

bot = Bot(token=TOKEN)
dp = Dispatcher()

dp.update.middleware(LoggingMiddleware())

users = {}

class ProfileState(StatesGroup):
    weight = State()
    height = State()
    age = State()
    gender = State()
    activity = State()
    city = State()

class LogFoodState(StatesGroup):
    product = State()
    weight = State()
    method = State()

class LogWorkoutState(StatesGroup):
    type = State()
    duration = State()

def calculate_water(weight, activity, temp):
    water = weight * 30 + (activity // 30) * 500
    if temp > 25:
        water += 500
    return water

def calculate_calories(weight, height, age, activity, gender):
    if gender.lower() in ["мужской", "м", "male"]:
        base = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        base = 10 * weight + 6.25 * height - 5 * age - 161
    return base + activity * 5

def workout_calories(weight, duration, intensity):
    factor_table = {
        "бег": 0.14,
        "ходьба": 0.05,
        "плавание": 0.13,
        "велосипед": 0.12,
        "йога": 0.06,
        "силовая": 0.11,
        "футбол": 0.14,
        "баскетбол": 0.15,
        "танцы": 0.10,
        "аэробика": 0.09,
        "скандинавская ходьба": 0.07,
    }
    factor = factor_table.get(intensity, 0.1)
    return factor * weight * duration

async def get_weather(city):
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_WEATHER}&units=metric"
            async with session.get(url) as resp:
                data = await resp.json()
                return data["main"].get("temp", 20)
        except:
            return 20

async def get_food_info(product_name: str):
    async with aiohttp.ClientSession() as session:
        url = API_FOOD_SEARCH.format(product_name)
        async with session.get(url) as resp:
            data = await resp.json()
            products = data.get("products", [])
            if not products:
                return None
            first = products[0]
            nutr = first.get("nutriments", {})
            name = first.get("product_name", "Неизвестно")
            prot = nutr.get("proteins_100g", 0)
            fat = nutr.get("fat_100g", 0)
            carb = nutr.get("carbohydrates_100g", 0)
            manual_kcal_100g = 4 * prot + 9 * fat + 4 * carb
            official_kcal_100g = nutr.get("energy-kcal_100g", 0)
            if manual_kcal_100g < 1:
                final_kcal_100g = official_kcal_100g
            else:
                final_kcal_100g = manual_kcal_100g
            return {
                "name": name,
                "calories_100g": final_kcal_100g,
                "proteins_100g": prot,
                "fat_100g": fat,
                "carbs_100g": carb
            }

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я помогу тебе рассчитать дневные нормы воды и калорий.\n"
        "Для начала настрой профиль командой /set_profile.\n\n"
    )

@dp.message(Command("set_profile"))
async def set_profile(message: types.Message, state: FSMContext):
    await message.answer("Введите ваш вес (кг):")
    await state.set_state(ProfileState.weight)

@dp.message(ProfileState.weight)
async def profile_weight(message: types.Message, state: FSMContext):
    await state.update_data(weight=int(message.text))
    await message.answer("Введите ваш рост (см):")
    await state.set_state(ProfileState.height)

@dp.message(ProfileState.height)
async def profile_height(message: types.Message, state: FSMContext):
    await state.update_data(height=int(message.text))
    await message.answer("Введите ваш возраст:")
    await state.set_state(ProfileState.age)

@dp.message(ProfileState.age)
async def profile_age(message: types.Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await message.answer("Введите ваш пол (мужской/женский):")
    await state.set_state(ProfileState.gender)

@dp.message(ProfileState.gender)
async def profile_gender(message: types.Message, state: FSMContext):
    gender_text = message.text.lower().strip()
    if gender_text not in ["мужской", "женский"]:
        await message.answer("Укажите 'мужской' или 'женский'.")
        return
    await state.update_data(gender=gender_text)
    await message.answer("Сколько минут активности в день?")
    await state.set_state(ProfileState.activity)

@dp.message(ProfileState.activity)
async def profile_activity(message: types.Message, state: FSMContext):
    await state.update_data(activity=int(message.text))
    await message.answer("В каком городе вы находитесь?")
    await state.set_state(ProfileState.city)

@dp.message(ProfileState.city)
async def profile_city(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    temp = await get_weather(message.text)
    weight = data["weight"]
    height = data["height"]
    age = data["age"]
    gender = data["gender"]
    activity = data["activity"]
    water_goal = calculate_water(weight, activity, temp)
    calorie_goal = calculate_calories(weight, height, age, activity, gender)
    users[user_id] = {
        "weight": weight,
        "height": height,
        "age": age,
        "gender": gender,
        "activity": activity,
        "city": message.text,
        "water_goal": water_goal,
        "calorie_goal": calorie_goal,
        "logged_water": [],
        "logged_calories": [],
        "burned_calories": 0
    }
    await message.answer(
        f"Профиль сохранён!\n"
        f"Вода (цель): {water_goal:.0f} мл\n"
        f"Калории (цель): {calorie_goal:.0f} ккал\n"
        f"(Температура в {message.text}: {temp}°C)"
    )
    await state.clear()

@dp.message(Command("set_calorie_goal"))
async def set_calorie_goal_cmd(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль (/set_profile).")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /set_calorie_goal 2000")
        return
    try:
        new_goal = float(parts[1])
        users[user_id]["calorie_goal"] = new_goal
        await message.answer(f"Новая цель по калориям: {new_goal:.1f}")
    except ValueError:
        await message.answer("Некорректное число.")

@dp.message(Command("log_water"))
async def log_water(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль (/set_profile).")
        return
    try:
        amount = int(message.text.split()[1])
        users[user_id]["logged_water"].append(amount)
        total_water = sum(users[user_id]["logged_water"])
        left = users[user_id]["water_goal"] - total_water
        await message.answer(
            f"Записано {amount} мл воды.\n"
            f"Итого: {total_water} мл.\n"
            f"Осталось до цели: {left} мл."
        )
    except (IndexError, ValueError):
        await message.answer("Формат: /log_water 330")

@dp.message(Command("log_food"))
async def log_food_cmd(message: types.Message, state: FSMContext):
    await message.answer("Введите название продукта:")
    await state.set_state(LogFoodState.product)

@dp.message(LogFoodState.product)
async def process_food_product(message: types.Message, state: FSMContext):
    product_name = message.text.strip().lower()
    info = await get_food_info(product_name)
    if not info:
        await message.answer("Информация о продукте не найдена. Попробуйте ещё раз.")
        await state.clear()
        return
    await state.update_data(
        product_name=info["name"],
        calories_100g=info["calories_100g"],
    )
    await message.answer(
        f"{info['name']} содержит ~{info['calories_100g']:.1f} ккал на 100 г.\n"
        "Сколько граммов вы съели?"
    )
    await state.set_state(LogFoodState.weight)

@dp.message(LogFoodState.weight)
async def process_food_weight(message: types.Message, state: FSMContext):
    try:
        grams = float(message.text.strip())
        await state.update_data(grams=grams)
        await message.answer(
            "Продукт как приготовлен?\n"
            "- 'жареный'\n"
            "- 'отварной'\n"
            "- 'запечённый'\n"
            "'-' (если не предполагается готовки)"
        )
        await state.set_state(LogFoodState.method)
    except ValueError:
        await message.answer("Укажите число (сколько граммов).")

@dp.message(LogFoodState.method)
async def process_food_method(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль (/set_profile).")
        await state.clear()
        return
    data = await state.get_data()
    cooking = message.text.strip().lower()
    method_factor = {
        "жареный": 1.20,
        "отварной": 1.00,
        "запечённый": 1.10,
        "-": 1.00
    }.get(cooking, 1.00)
    base_cal_100g = data["calories_100g"]
    grams = data["grams"]
    base_cal = (base_cal_100g * grams) / 100.0
    final_cal = base_cal * method_factor
    users[user_id]["logged_calories"].append(final_cal)
    total_calories = sum(users[user_id]["logged_calories"])
    txt = (
        f"Продукт: {data['product_name']}\n"
        f"Вес: {grams:.1f} г\n"
        f"Баз. калорийность: {base_cal:.1f} ккал\n"
        f"Приготовление: {cooking} (x{method_factor:.2f})\n"
        f"Итого: {final_cal:.1f} ккал\n\n"
        f"Суммарно за сегодня: {total_calories:.1f} ккал."
    )
    await message.answer(txt)
    cal_goal = users[user_id]["calorie_goal"]
    if total_calories >= 0.8 * cal_goal:
        low_cal_foods = [
            "Огурцы 🥒 (~15 ккал / 100 г)",
            "Листья салата 🥬 (~17 ккал / 100 г)",
            "Капуста 🥦 (~25 ккал / 100 г)",
            "Куриная грудка 🐥😭 (~110 ккал / 100 г)"
        ]
        rec_text = (
            "Вы уже приблизились к дневной норме калорий.\n"
            "Вот несколько вариантов низкокалорийных продуктов:\n"
        )
        for item in low_cal_foods:
            rec_text += f"• {item}\n"
        await message.answer(rec_text)
    await state.clear()

@dp.message(Command("log_workout"))
async def log_workout_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id not in users:
        await message.answer("Сначала настройте профиль (/set_profile).")
        return
    await message.answer("Введите тип тренировки (бег, ходьба, плавание и т.д.):")
    await state.set_state(LogWorkoutState.type)

@dp.message(LogWorkoutState.type)
async def process_workout_type(message: types.Message, state: FSMContext):
    workout_type = message.text.lower().strip()
    await state.update_data(type=workout_type)
    await message.answer("Введите длительность тренировки (мин):")
    await state.set_state(LogWorkoutState.duration)

@dp.message(LogWorkoutState.duration)
async def process_workout_duration(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль.")
        await state.clear()
        return
    data = await state.get_data()
    try:
        duration = int(message.text)
        c_burned = workout_calories(users[user_id]["weight"], duration, data["type"])
        users[user_id]["burned_calories"] += c_burned
        extra_water = (duration // 30) * 200
        users[user_id]["logged_water"].append(extra_water)
        await message.answer(
            f"Тренировка: {data['type']}, {duration} мин.\n"
            f"Сожжено: {c_burned:.1f} ккал.\n"
            f"Дополнительно добавлено {extra_water} мл воды."
        )
        await state.clear()
    except ValueError:
        await message.answer("Введите число (длительность в минутах).")

@dp.message(Command("check_progress"))
async def check_progress(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль (/set_profile).")
        return
    user = users[user_id]
    total_water = sum(user["logged_water"])
    total_calories = sum(user["logged_calories"])
    burned = user["burned_calories"]
    balance = total_calories - burned
    msg = (
        "📊 Прогресс:\n"
        f"Вода: {total_water} мл (цель: {user['water_goal']:.0f} мл)\n"
        f"Калорий съедено: {total_calories:.1f} (цель: {user['calorie_goal']:.1f})\n"
        f"Сожжено: {burned:.1f} ккал\n"
        f"Баланс (съедено - сожжено): {balance:.1f} ккал\n"
    )
    await message.answer(msg)

@dp.message(Command("progress_graphs"))
async def progress_graphs(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль (/set_profile).")
        return
    user = users[user_id]
    if len(user["logged_water"]) < 2 or len(user["logged_calories"]) < 2:
        await message.answer("Недостаточно данных для графиков (нужно хотя бы 2 записи).")
        return
    plt.figure(figsize=(8,4))
    plt.plot(user["logged_water"], marker='o', label='Вода (мл)')
    plt.title("Прогресс воды")
    plt.xlabel("Запись")
    plt.ylabel("Мл")
    plt.legend()
    buf_water = BytesIO()
    plt.savefig(buf_water, format='png')
    buf_water.seek(0)
    plt.close()
    plt.figure(figsize=(8,4))
    plt.plot(user["logged_calories"], marker='o', color='orange', label='Калории (ккал)')
    plt.title("Прогресс калорий")
    plt.xlabel("Запись")
    plt.ylabel("Ккал")
    plt.legend()
    buf_cal = BytesIO()
    plt.savefig(buf_cal, format='png')
    buf_cal.seek(0)
    plt.close()
    photo_water = BufferedInputFile(buf_water.getvalue(), filename='water.png')
    photo_cal = BufferedInputFile(buf_cal.getvalue(), filename='calories.png')
    await message.answer_photo(photo_water, caption="График потребления воды")
    await message.answer_photo(photo_cal, caption="График потребления калорий")

async def main():
    logging.info("Запуск бота!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
