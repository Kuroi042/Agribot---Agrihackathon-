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

from storage import get_faults, get_state, initialize_database

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


class ControlForm(StatesGroup):
    waiting_for_speed = State()


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 - Pump status", callback_data="menu:status")],
        [InlineKeyboardButton(text="2 - Show faults", callback_data="menu:faults")],
        [InlineKeyboardButton(text="3 - Recommendation", callback_data="menu:recommend")],
        [InlineKeyboardButton(text="4 - Manual control", callback_data="menu:manual")],
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


def format_status() -> str:
    state = get_state()
    if not state:
        return "No inverter data received yet. Start mqtt_ingestor.py and publish telemetry."
    return (
        "Pump status\n"
        f"1. Speed: {fmt_number(state.get('frequency_hz'), 'Hz')}\n"
        f"2. DC voltage: {fmt_number(state.get('dc_voltage_v'), 'V')}\n"
        f"3. Current: {fmt_number(state.get('current_a'), 'A')}\n"
        f"4. Pump: {'running' if state.get('running') else 'stopped'}\n"
        f"5. Inverter: {'available' if state.get('available') else 'not available'}\n"
        f"6. Rotation: {fmt_number(state.get('rotation_rpm'), 'RPM')}\n"
        f"7. Water level: {fmt_number(state.get('water_level_percent'), '%')}\n"
        f"Last update: {state.get('updated_at', 'unknown')}"
    )


def format_faults() -> str:
    faults = get_faults(active_only=True)
    if not faults:
        return "No active faults."
    lines = ["Active faults:"]
    for index, fault in enumerate(faults, 1):
        lines.append(f"{index}. {fault['code']}: {fault['message']}")
    return "\n".join(lines)


def recommendation() -> tuple[float | None, str]:
    state = get_state()
    if not state or state.get("frequency_hz") is None:
        return None, "No telemetry is available, so a safe speed cannot be suggested."
    current_speed = float(state["frequency_hz"])
    faults = {item["code"] for item in get_faults(active_only=True)}
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
    await message.answer("Irrigation inverter control — choose an option:", reply_markup=menu_keyboard())


@router.message(Command("status"))
async def status_command(message: types.Message) -> None:
    if not await reject_if_unauthorized(message):
        await message.answer(format_status(), reply_markup=menu_keyboard())


@router.callback_query(F.data == "menu:home")
async def home(callback: types.CallbackQuery, state: FSMContext) -> None:
    if await reject_if_unauthorized(callback):
        return
    await state.clear()
    await callback.message.edit_text("Irrigation inverter control — choose an option:", reply_markup=menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:status")
async def show_status(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    await callback.message.edit_text(format_status(), reply_markup=menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:faults")
async def show_faults(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    await callback.message.edit_text(format_faults(), reply_markup=menu_keyboard())
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
            [InlineKeyboardButton(text="3 - #YOLO", callback_data="recommend:yolo")],
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


@router.callback_query(F.data == "recommend:yolo")
async def yolo(callback: types.CallbackQuery) -> None:
    if await reject_if_unauthorized(callback):
        return
    await callback.answer("#YOLO is intentionally blocked for pump safety.", show_alert=True)


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
    choice = (message.text or "").strip()
    if choice == "1":
        await message.answer(format_status(), reply_markup=menu_keyboard())
    elif choice == "2":
        await message.answer(format_faults(), reply_markup=menu_keyboard())
    elif choice == "3":
        speed, text = recommendation()
        await message.answer(text + ("\nUse the menu button to confirm." if speed is not None else ""), reply_markup=menu_keyboard())
    elif choice == "4":
        await message.answer("Manual control:", reply_markup=manual_keyboard())
    else:
        await message.answer("Choose 1-4 or use the buttons.", reply_markup=menu_keyboard())


async def main() -> None:
    if not TOKEN:
        sys.exit("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
    initialize_database()
    print("Telegram bot is starting...")
    await dp.start_polling(Bot(token=TOKEN))


if __name__ == "__main__":
    asyncio.run(main())
