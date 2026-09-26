import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

from storage import get_faults, get_language, get_state, initialize_database, set_language

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_COMMAND_TOPIC = os.getenv("MQTT_COMMAND_TOPIC", "agribot/inverter/command")
ALLOWED_CHAT_IDS = {
    int(value.strip())
    for value in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")
    if value.strip()
}

router = Router()
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)


FAULT_RECOMMENDATIONS = {
    "INVERTER_OFFLINE": "Do not send control commands. Check inverter power, communications, and the controller connection.",
    "GROUND_FAULT": "Stop and isolate power. Have insulation, grounding, and cables checked by a qualified technician.",
    "PHASE_LOSS": "Stop operation and have the supply phases, protection devices, and wiring checked.",
    "OVER_VOLTAGE": "Stop operation if the condition persists. Check the PV/battery/AC supply and inverter settings.",
    "OVER_TEMPERATURE": "Reduce load or stop the pump, allow cooling, then check airflow, fans, and enclosure temperature.",
    "MOTOR_OVERHEAT": "Stop the motor, let it cool, and inspect the load, ventilation, and motor condition.",
    "OVERLOAD": "Stop the pump and inspect for a jam, blocked pipework, or excessive mechanical load before restarting.",
    "PUMP_BLOCKED": "Stop and isolate power before inspecting and clearing the pump or pipework blockage.",
    "DRY_RUN": "Stop the pump. Restore source water, prime the pump, and inspect the suction line before restarting.",
    "LOW_WATER": "Stop the pump or keep it stopped until the source-water level is safely restored.",
    "LOW_BATTERY": "Reduce demand and check battery charge, charging source, and terminal connections.",
    "UNDER_VOLTAGE": "Check the PV strings, battery, supply, and cable connections; avoid increasing the load.",
    "OVER_CURRENT": "Reduce load and inspect the pump, cable, and motor before returning to normal speed.",
    "LOW_CURRENT": "Stop and inspect for dry running, a loose cable, or a disconnected pump.",
    "COMMUNICATION_FAILURE": "Check controller power, network settings, and communication wiring; do not rely on remote control until restored.",
    "SENSOR_FAILURE": "Inspect the affected sensor and its wiring; replace or recalibrate it before relying on its reading.",
}

TEXT = {
    "en": {
        "language": "5 - 🌐 Language", "status_menu": "1 - 📊 Pump status", "faults_menu": "2 - ⚠️ Show faults",
        "recommend_menu": "3 - 💡 Recommendation", "manual_menu": "4 - 🎛️ Manual control", "status_title": "⚡ Inverter {id} — {pump} ({health})",
        "running": "Running", "stopped": "Stopped", "online": "Online", "offline": "Offline", "unknown": "unknown",
        "power": "Power", "output": "Output", "solar_input": "Solar input", "current": "Current", "solar_power": "Solar power",
        "mode": "Mode", "battery": "Battery", "water_level": "Water level", "temperature": "Temperature", "pump_speed": "Pump speed",
        "flow": "Flow", "pressure": "Pressure", "energy": "Energy", "today": "today", "total": "total", "runtime": "Runtime",
        "power_factor": "Power factor", "active_faults": "Active faults", "faults_available": "Available", "faults_not_available": "Not available", "last_update": "Last update", "no_faults": "None",
        "faults_title": "Active faults:", "no_active_faults": "No active faults.", "select_language": "Choose your language:",
        "language_saved": "Language set to English.", "home": "Irrigation inverter control — choose an option:", "invalid_choice": "Choose 1-5 or use the buttons.",
    },
    "ar": {
        "language": "5 - 🌐 اللغة", "status_menu": "1 - 📊 حالة المضخة", "faults_menu": "2 - ⚠️ عرض الأعطال",
        "recommend_menu": "3 - 💡 التوصية", "manual_menu": "4 - 🎛️ التحكم اليدوي", "status_title": "⚡ العاكس {id} — {pump} ({health})",
        "running": "قيد التشغيل", "stopped": "متوقفة", "online": "متصل", "offline": "غير متصل", "unknown": "غير معروف",
        "power": "القدرة", "output": "الخرج", "solar_input": "دخل الطاقة الشمسية", "current": "التيار", "solar_power": "قدرة الطاقة الشمسية",
        "mode": "الوضع", "battery": "البطارية", "water_level": "مستوى الماء", "temperature": "الحرارة", "pump_speed": "سرعة المضخة",
        "flow": "التدفق", "pressure": "الضغط", "energy": "الطاقة", "today": "اليوم", "total": "الإجمالي", "runtime": "مدة التشغيل",
        "power_factor": "معامل القدرة", "active_faults": "الأعطال النشطة", "faults_available": "موجودة", "faults_not_available": "غير موجودة", "last_update": "آخر تحديث", "no_faults": "لا يوجد",
        "faults_title": "الأعطال النشطة:", "no_active_faults": "لا توجد أعطال نشطة.", "select_language": "اختر اللغة:",
        "language_saved": "تم اختيار العربية.", "home": "التحكم في عاكس الري — اختر خياراً:", "invalid_choice": "اختر من 1 إلى 5 أو استخدم الأزرار.",
    },
    "it": {
        "language": "5 - 🌐 Lingua", "status_menu": "1 - 📊 Stato pompa", "faults_menu": "2 - ⚠️ Mostra guasti",
        "recommend_menu": "3 - 💡 Raccomandazione", "manual_menu": "4 - 🎛️ Controllo manuale", "status_title": "⚡ Inverter {id} — {pump} ({health})",
        "running": "In funzione", "stopped": "Fermata", "online": "Online", "offline": "Non disponibile", "unknown": "sconosciuto",
        "power": "Potenza", "output": "Uscita", "solar_input": "Ingresso solare", "current": "Corrente", "solar_power": "Potenza solare",
        "mode": "Modalità", "battery": "Batteria", "water_level": "Livello acqua", "temperature": "Temperatura", "pump_speed": "Velocità pompa",
        "flow": "Portata", "pressure": "Pressione", "energy": "Energia", "today": "oggi", "total": "totale", "runtime": "Ore di funzionamento",
        "power_factor": "Fattore di potenza", "active_faults": "Guasti attivi", "faults_available": "Disponibili", "faults_not_available": "Non disponibili", "last_update": "Ultimo aggiornamento", "no_faults": "Nessuno",
        "faults_title": "Guasti attivi:", "no_active_faults": "Nessun guasto attivo.", "select_language": "Scegli la lingua:",
        "language_saved": "Lingua impostata su italiano.", "home": "Controllo inverter irrigazione — scegli un'opzione:", "invalid_choice": "Scegli da 1 a 5 o usa i pulsanti.",
    },
    "fr": {
        "language": "5 - 🌐 Langue", "status_menu": "1 - 📊 État de la pompe", "faults_menu": "2 - ⚠️ Voir les défauts",
        "recommend_menu": "3 - 💡 Recommandation", "manual_menu": "4 - 🎛️ Commande manuelle", "status_title": "⚡ Onduleur {id} — {pump} ({health})",
        "running": "En marche", "stopped": "Arrêtée", "online": "En ligne", "offline": "Hors ligne", "unknown": "inconnu",
        "power": "Puissance", "output": "Sortie", "solar_input": "Entrée solaire", "current": "Courant", "solar_power": "Puissance solaire",
        "mode": "Mode", "battery": "Batterie", "water_level": "Niveau d'eau", "temperature": "Température", "pump_speed": "Vitesse de la pompe",
        "flow": "Débit", "pressure": "Pression", "energy": "Énergie", "today": "aujourd'hui", "total": "total", "runtime": "Durée de fonctionnement",
        "power_factor": "Facteur de puissance", "active_faults": "Défauts actifs", "faults_available": "Disponibles", "faults_not_available": "Non disponibles", "last_update": "Dernière mise à jour", "no_faults": "Aucun",
        "faults_title": "Défauts actifs :", "no_active_faults": "Aucun défaut actif.", "select_language": "Choisissez votre langue :",
        "language_saved": "Langue réglée sur le français.", "home": "Commande de l'onduleur d'irrigation — choisissez une option :", "invalid_choice": "Choisissez de 1 à 5 ou utilisez les boutons.",
    },
}

FAULT_TEXT = {
    "E056": {"ar": "جهد البطارية منخفض. خفّض الطلب وافحص الشحن والأطراف.", "it": "Tensione batteria bassa. Ridurre il carico e controllare ricarica e morsetti."},
    "E065": {"ar": "ارتفاع حرارة العاكس. خفّض الحمل أو أوقف المضخة وافحص التهوية.", "it": "Sovratemperatura inverter. Ridurre il carico o fermare la pompa e controllare la ventilazione."},
    "E070": {"ar": "مستوى الماء منخفض. أوقف المضخة حتى يعود الماء إلى مستوى آمن.", "it": "Livello acqua basso. Fermare la pompa finché il livello non torna sicuro."},
    "LOW_SOLAR": {"ar": "جهد الطاقة الشمسية منخفض.", "it": "Tensione solare troppo bassa.", "fr": "Tension solaire trop basse."},
    "LOW_BATTERY": {"ar": "شحن البطارية منخفض.", "it": "Carica batteria bassa.", "fr": "Charge de batterie faible."},
    "OVER_TEMPERATURE": {"ar": "حرارة العاكس أعلى من الحد الآمن.", "it": "Temperatura inverter oltre il limite sicuro.", "fr": "Température de l'onduleur au-dessus de la limite sûre."},
    "LOW_WATER": {"ar": "مستوى الماء أقل من الحد الآمن.", "it": "Livello acqua sotto il limite sicuro.", "fr": "Niveau d'eau sous la limite sûre."},
}

FAULT_TEXT["E056"]["fr"] = "Tension de batterie faible. Réduisez la charge et vérifiez la recharge et les bornes."
FAULT_TEXT["E065"]["fr"] = "Surchauffe de l'onduleur. Réduisez la charge ou arrêtez la pompe et vérifiez la ventilation."
FAULT_TEXT["E070"]["fr"] = "Niveau d'eau faible. Arrêtez la pompe jusqu'au retour à un niveau sûr."

MODE_TEXT = {
    "irrigation": {"ar": "الري", "it": "irrigazione"},
    "manual": {"ar": "يدوي", "it": "manuale", "fr": "manuel"},
    "automatic": {"ar": "تلقائي", "it": "automatico", "fr": "automatique"},
    "standby": {"ar": "وضع الاستعداد", "it": "standby", "fr": "veille"},
}
MODE_TEXT["irrigation"]["fr"] = "irrigation"


def t(language: str, key: str, **values: object) -> str:
    return TEXT.get(language, TEXT["en"]).get(key, TEXT["en"].get(key, key)).format(**values)


def localized_mode(value: object, language: str) -> str:
    mode = str(value or "").lower()
    if not mode:
        return t(language, "unknown")
    return MODE_TEXT.get(mode, {}).get(language, mode)


class ControlForm(StatesGroup):
    waiting_for_speed = State()


def menu_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "status_menu"), callback_data="menu:status")],
        [InlineKeyboardButton(text=t(language, "faults_menu"), callback_data="menu:faults")],
        [InlineKeyboardButton(text=t(language, "recommend_menu"), callback_data="menu:recommend")],
        [InlineKeyboardButton(text=t(language, "manual_menu"), callback_data="menu:manual")],
        [InlineKeyboardButton(text=t(language, "language"), callback_data="menu:language")],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="العربية", callback_data="language:ar")],
        [InlineKeyboardButton(text="Italiano", callback_data="language:it")],
        [InlineKeyboardButton(text="Français", callback_data="language:fr")],
        [InlineKeyboardButton(text="English", callback_data="language:en")],
    ])


def manual_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Start", callback_data="control:start"),
            InlineKeyboardButton(text="Stop", callback_data="control:stop"),
        ],
        [InlineKeyboardButton(text="Set speed (0-50 Hz)", callback_data="control:speed")],
        [InlineKeyboardButton(text="Back", callback_data="menu:home")],
    ])


def allowed(event: types.Message | types.CallbackQuery) -> bool:
    chat = event.message.chat if isinstance(event, types.CallbackQuery) else event.chat
    return not ALLOWED_CHAT_IDS or chat.id in ALLOWED_CHAT_IDS


async def reject_if_unauthorized(event: types.Message | types.CallbackQuery) -> bool:
    if allowed(event):
        return False
    if isinstance(event, types.CallbackQuery):
        await event.answer("This chat is not authorized.", show_alert=True)
    else:
        await event.answer("This chat is not authorized.")
    return True


def fmt_number(value: object, unit: str) -> str:
    return "unknown" if value is None else f"{value} {unit}"


def format_status(language: str = "en") -> str:
    state = get_state()
    if not state:
        return "No inverter data received yet. Start mqtt_ingestor.py and publish telemetry."
    power = state.get("ac_power_w")
    unknown = t(language, "unknown")
    power_text = unknown if power is None else f"{float(power) / 1000:.2f} kW"
    health = t(language, "online") if state.get("available") else t(language, "offline")
    pump = t(language, "running") if state.get("running") else t(language, "stopped")
    active_faults = get_faults(active_only=True)
    fault_text = t(language, "faults_available") if active_faults else t(language, "faults_not_available")
    return (
        f"{t(language, 'status_title', id=state.get('inverter_id', unknown), pump=pump, health=health)}\n\n"
        f"⚡ {t(language, 'power')}: {power_text}\n"
        f"🔌 {t(language, 'output')}: {fmt_number(state.get('ac_voltage_v'), 'V')} at {fmt_number(state.get('frequency_hz'), 'Hz')}\n"
        f"☀️ {t(language, 'solar_input')}: {fmt_number(state.get('dc_voltage_v'), 'V')} | {t(language, 'current')}: {fmt_number(state.get('current_a'), 'A')}\n"
        f"🌞 {t(language, 'solar_power')}: {fmt_number(state.get('solar_power_w'), 'W')} | ⚙️ {t(language, 'mode')}: {localized_mode(state.get('operating_mode'), language)}\n"
        f"🔋 {t(language, 'battery')}: {fmt_number(state.get('battery_percent'), '%')} | 💧 {t(language, 'water_level')}: {fmt_number(state.get('water_level_percent'), '%')}\n"
        f"🌡️ {t(language, 'temperature')}: {fmt_number(state.get('temperature_c'), '°C')} | 🔄 {t(language, 'pump_speed')}: {fmt_number(state.get('rotation_rpm'), 'RPM')}\n"
        f"🚰 {t(language, 'flow')}: {fmt_number(state.get('pump_flow_m3h'), 'm³/h')} | 📈 {t(language, 'pressure')}: {fmt_number(state.get('pump_pressure_bar'), 'bar')}\n"
        f"📊 {t(language, 'energy')}: {fmt_number(state.get('daily_energy_kwh'), 'kWh')} {t(language, 'today')} | {fmt_number(state.get('total_energy_kwh'), 'kWh')} {t(language, 'total')}\n"
        f"⏱️ {t(language, 'runtime')}: {fmt_number(state.get('runtime_hours'), 'hours')}\n"
        f"📐 {t(language, 'power_factor')}: {fmt_number(state.get('power_factor'), '')}\n\n"
        f"⚠️ {t(language, 'active_faults')}: {fault_text}\n"
        f"🕒 {t(language, 'last_update')}: {state.get('updated_at', unknown)}"
    )


def format_faults(language: str = "en") -> str:
    faults = get_faults(active_only=True)
    if not faults:
        return t(language, "no_active_faults")
    lines = [f"⚠️ {t(language, 'faults_title')}"]
    for index, fault in enumerate(faults, 1):
        translated = FAULT_TEXT.get(fault["code"], {}).get(language, fault["message"])
        lines.append(f"{index}. 🔴 {fault['code']}: {translated}")
    return "\n".join(lines)


def recommendation() -> tuple[float | None, str]:
    state = get_state()
    if not state or state.get("frequency_hz") is None:
        return None, "No telemetry is available, so a safe speed cannot be suggested."
    current_speed = float(state["frequency_hz"])
    faults = {item["code"] for item in get_faults(active_only=True)}
    for code, advice in FAULT_RECOMMENDATIONS.items():
        if code in faults:
            return None, advice
    if "HIGH_CURRENT" in faults or "LOW_SOLAR" in faults:
        suggested = max(0.0, current_speed - 3.0)
        return suggested, f"I suggest lowering speed from {current_speed:g} Hz to {suggested:g} Hz."
    if "LOW_CURRENT" in faults:
        return None, "Low current may mean dry running or a disconnected pump. Stop and inspect it."
    return current_speed, f"Readings are normal. Keep the current speed at {current_speed:g} Hz."


def publish_command(command: str, value: float | None = None) -> tuple[bool, str]:
    payload = {
        "command": command,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "telegram",
    }
    if value is not None:
        payload.update({"value": value, "unit": "Hz"})
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        username = os.getenv("MQTT_USERNAME")
        if username:
            client.username_pw_set(username, os.getenv("MQTT_PASSWORD"))
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        client.loop_start()
        info = client.publish(MQTT_COMMAND_TOPIC, json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=5)
        client.disconnect()
        client.loop_stop()
        if not info.is_published():
            return False, "The MQTT broker did not acknowledge the command."
        return True, "Command sent to the inverter controller."
    except Exception as exc:
        return False, f"MQTT command failed: {exc}"


@router.message(CommandStart())
async def start(message: types.Message, state: FSMContext) -> None:
    if await reject_if_unauthorized(message):
        return
    await state.clear()
    language = get_language(message.chat.id)
    await message.answer(t(language, "home"), reply_markup=menu_keyboard(language))


@router.message(Command("status"))
async def status_command(message: types.Message) -> None:
    if not await reject_if_unauthorized(message):
        language = get_language(message.chat.id)
        await message.answer(format_status(language), reply_markup=menu_keyboard(language))


@router.callback_query(F.data == "menu:home")
async def home(callback: types.CallbackQuery, state: FSMContext) -> None:
    if await reject_if_unauthorized(callback):
        return
    await state.clear()
    language = get_language(callback.message.chat.id)
    await callback.message.edit_text(t(language, "home"), reply_markup=menu_keyboard(language))
    await callback.answer()


@router.callback_query(F.data == "menu:language")
async def choose_language(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    language = get_language(callback.message.chat.id)
    await callback.message.edit_text(t(language, "select_language"), reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("language:"))
async def save_language(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    language = callback.data.split(":", 1)[1]
    if language not in TEXT:
        await callback.answer("Unsupported language.", show_alert=True)
        return
    set_language(callback.message.chat.id, language)
    await callback.message.edit_text(t(language, "language_saved"), reply_markup=menu_keyboard(language))
    await callback.answer()


@router.callback_query(F.data == "menu:status")
async def show_status(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    language = get_language(callback.message.chat.id)
    await callback.message.edit_text(format_status(language), reply_markup=menu_keyboard(language))
    await callback.answer()


@router.callback_query(F.data == "menu:faults")
async def show_faults(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    language = get_language(callback.message.chat.id)
    await callback.message.edit_text(format_faults(language), reply_markup=menu_keyboard(language))
    await callback.answer()


@router.callback_query(F.data == "menu:recommend")
async def show_recommendation(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    speed, text = recommendation()
    buttons = []
    if speed is not None:
        buttons.extend([
            [InlineKeyboardButton(text="1 - Confirm", callback_data=f"recommend:confirm:{speed}"),
             InlineKeyboardButton(text="2 - No", callback_data="menu:home")],
        ])
    buttons.append([InlineKeyboardButton(text="Back", callback_data="menu:home")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("recommend:confirm:"))
async def confirm_recommendation(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    speed = float(callback.data.rsplit(":", 1)[1])
    ok, result = await asyncio.to_thread(publish_command, "set_speed", speed)
    await callback.message.edit_text(
        f"{'Confirmed' if ok else 'Not sent'}: {speed:g} Hz. {result}", reply_markup=menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "menu:manual")
async def manual(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    await callback.message.edit_text("Manual control:", reply_markup=manual_keyboard())
    await callback.answer()


@router.callback_query(F.data.in_({"control:start", "control:stop"}))
async def start_stop(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    command = callback.data.split(":", 1)[1]
    ok, result = await asyncio.to_thread(publish_command, command)
    await callback.answer(result, show_alert=not ok)
    if ok:
        await callback.message.edit_text(f"{command.title()} command sent.", reply_markup=manual_keyboard())


@router.callback_query(F.data == "control:speed")
async def ask_speed(callback: types.CallbackQuery, state: FSMContext) -> None:
    if await reject_if_unauthorized(callback):
        return
    await state.set_state(ControlForm.waiting_for_speed)
    await callback.message.answer("Enter a speed from 0 to 50 Hz (example: 47):")
    await callback.answer()


@router.message(ControlForm.waiting_for_speed)
async def receive_speed(message: types.Message, state: FSMContext) -> None:
    if await reject_if_unauthorized(message):
        return
    try:
        speed = float((message.text or "").replace(",", "."))
        if not 0 <= speed <= 50:
            raise ValueError
    except ValueError:
        await message.answer("Enter a number between 0 and 50.")
        return
    ok, result = await asyncio.to_thread(publish_command, "set_speed", speed)
    await state.clear()
    await message.answer(
        f"{'Speed command sent' if ok else 'Speed was not changed'}: {speed:g} Hz. {result}",
        reply_markup=menu_keyboard(),
    )


@router.message()
async def numeric_menu(message: types.Message) -> None:
    if await reject_if_unauthorized(message):
        return
    language = get_language(message.chat.id)
    choice = (message.text or "").strip()
    if choice == "1":
        await message.answer(format_status(language), reply_markup=menu_keyboard(language))
    elif choice == "2":
        await message.answer(format_faults(language), reply_markup=menu_keyboard(language))
    elif choice == "3":
        speed, text = recommendation()
        await message.answer(text + ("\nUse the menu button to confirm." if speed is not None else ""), reply_markup=menu_keyboard(language))
    elif choice == "4":
        await message.answer("Manual control:", reply_markup=manual_keyboard())
    elif choice == "5":
        await message.answer(t(language, "select_language"), reply_markup=language_keyboard())
    else:
        await message.answer(t(language, "invalid_choice"), reply_markup=menu_keyboard(language))


async def main() -> None:
    if not TOKEN:
        sys.exit("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
    initialize_database()
    print("Telegram bot is starting...")
    await dp.start_polling(Bot(token=TOKEN))


if __name__ == "__main__":
    asyncio.run(main())
