
import os
import json
import requests
import ollama

from dotenv import load_dotenv

load_dotenv()

HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

MODEL = "qwen2.5:3b"
conversation_history = []

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json"
}

DEVICES = {
    "lamp": ("Розумна лампа", "input_boolean.rozumna_lampa"),
    "heater": ("Обігрівач", "input_boolean.obigrivach"),
    "exhaust": ("Витяжка", "input_boolean.vitiazhka"),
    "night": ("Нічний режим", "input_boolean.nichnii_rezhim"),
    "morning": ("Ранковий режим", "input_boolean.rankovii_rezhim")
}

STATUS_ENTITIES = {
    "Температура": "input_number.temperatura",
    "Вологість": "input_number.vologist",
    "Двері": "input_boolean.dveri",
    "Датчик руху": "input_boolean.datchik_ruhu"
}


def get_states():
    response = requests.get(
        f"{HA_URL}/api/states",
        headers=HEADERS,
        timeout=60
    )
    response.raise_for_status()
    return response.json()


def control(entity_id, action):
    response = requests.post(
        f"{HA_URL}/api/services/input_boolean/turn_{action}",
        headers=HEADERS,
        json={"entity_id": entity_id},
        timeout=60
    )
    response.raise_for_status()


def show_status():
    states = get_states()
    state_map = {item["entity_id"]: item for item in states}

    print("\nСТАН БУДИНКУ:")

    for name, entity_id in STATUS_ENTITIES.items():
        item = state_map.get(entity_id)
        value = item["state"] if item else "невідомо"
        print(f"{name}: {value}")

    for name, entity_id in DEVICES.values():
        item = state_map.get(entity_id)
        value = item["state"] if item else "невідомо"
        print(f"{name}: {value}")

    print()


def turn_off_all():
    for name, entity_id in DEVICES.values():
        control(entity_id, "off")

    print("Усі пристрої та режими вимкнено.")


def understand_command(command):
    global conversation_history

    text = command.lower().strip()

    # Визначення пристрою
    device_rules = [
        (["ламп", "світло", "освітлення", "темно"], "lamp"),
        (["обігрівач", "обігрів", "нагрів", "холодно"], "heater"),
        (["витяжк", "вентиляц", "душно"], "exhaust"),
        (["нічний режим"], "night"),
        (["ранковий режим", "пора прокидатися"], "morning")
    ]

    target = None

    for words, device in device_rules:
        if any(word in text for word in words):
            target = device
            break

    # Розпізнавання пристрою з попередньої розмови
    pronouns = ["її", "його", "це", "цей", "цю"]

    if target is None and any(word in text.split() for word in pronouns):
        for item in reversed(conversation_history):
            previous_target = item.get("assistant", {}).get("target")

            if previous_target in DEVICES:
                target = previous_target
                break

    # Вимкнення всього
    if any(phrase in text for phrase in [
        "вимкни все", "вимкнути все", "виключи все"
    ]):
        result = {"action": "all_off", "target": "none"}

    # Перегляд стану
    elif any(word in text for word in [
        "статус", "стан будинку", "температура", "вологість",
        "що вдома", "як справи вдома"
    ]):
        result = {"action": "status", "target": "none"}

    # Вимкнення пристрою
    elif any(word in text for word in [
        "вимкни", "вимкнути", "виключи", "відключи"
    ]):
        if target:
            result = {"action": "turn_off", "target": target}
        else:
            result = {"action": "unknown", "target": "none"}

    # Увімкнення пристрою
    elif any(word in text for word in [
        "увімкни", "увімкнути", "включи", "запусти"
    ]):
        if target:
            result = {"action": "turn_on", "target": target}
        else:
            result = {"action": "unknown", "target": "none"}

    # Природні фрази
    elif target and any(word in text for word in [
        "темно", "холодно", "душно", "пора прокидатися"
    ]):
        result = {"action": "turn_on", "target": target}

    # Звернення до локального ШІ
    else:
        prompt = f"""
Ти Jarvis — помічник розумного будинку.

Доступні дії: status, unknown.
Ціль: none.

Якщо користувач запитує про стан будинку,
поверни status.
Для інших запитів поверни unknown.

Історія:
{json.dumps(conversation_history, ensure_ascii=False)}

Команда: {command}

Поверни тільки JSON:
"""

        response = ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Відповідай тільки коректним JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json"
        )

        result = json.loads(response["message"]["content"])

        if result.get("action") not in ["status", "unknown"]:
            result = {"action": "unknown", "target": "none"}

        result["target"] = "none"

    # Збереження історії
    conversation_history.append({
        "user": command,
        "assistant": result
    })

    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]

    return result


def process_command(command):
    if command.lower().strip() in ["вихід", "exit", "quit"]:
        return False

    result = understand_command(command)

    action = result.get("action")
    target = result.get("target")

    if action == "status":
        show_status()
        return True

    if action == "all_off":
        turn_off_all()
        return True

    if action in ["turn_on", "turn_off"] and target in DEVICES:
        name, entity_id = DEVICES[target]

        state_action = "on" if action == "turn_on" else "off"

        control(entity_id, state_action)

        if state_action == "on":
            print(f"{name} увімкнено.")
        else:
            print(f"{name} вимкнено.")

        return True

    print("Не зрозумів команду. Спробуй сформулювати інакше.")
    return True


def main():
    print("=" * 40)
    print("       JARVIS - SMART HOME AI")
    print("=" * 40)

    if not HA_URL or not HA_TOKEN:
        print("Помилка: перевір файл .env")
        return

    try:
        get_states()
        print("Home Assistant: підключено")

        ollama.list()
        print(f"Локальний ШІ: {MODEL}")
        print("Jarvis готовий до роботи!")
        print("Напиши «вихід», щоб завершити.\n")

        while True:
            command = input("Ти: ")

            try:
                if not process_command(command):
                    print("Jarvis завершив роботу.")
                    break

            except requests.RequestException as error:
                print(f"Помилка Home Assistant: {error}")

            except (ValueError, KeyError, TypeError) as error:
                print(f"Помилка обробки команди: {error}")

            except Exception as error:
                print(f"Помилка: {error}")

    except requests.RequestException as error:
        print(f"Не вдалося підключитися до Home Assistant: {error}")

    except Exception as error:
        print(f"Помилка запуску Jarvis: {error}")


if __name__ == "__main__":
    main()
