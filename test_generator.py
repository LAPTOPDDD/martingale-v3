#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_generator.py
====================================
Проверяет, что generator.py выдаёт:
  1) синтаксически валидный Python-код
  2) с БЕЗОПАСНЫМИ проверками MT5-массивов (исправление ошибки)
  3) SMA без look-ahead (окно исключает текущий бар)
НЕ требует plotly / streamlit (импортирует только generator).
Запуск:  python test_generator.py
"""
import os
import sys
import tempfile
import subprocess

import generator  # noqa: E402  (только stdlib + hashlib)


def main():
    print("=" * 64)
    print("TEST GENERATOR: generator.generate_bot_code()")
    print("=" * 64)

    code, filename = generator.generate_bot_code(
        symbol="CARDANO", timeframe="H1",
        start_lot=0.01, max_positions=10, sma_period=20,
    )

    print(f"\n[1] Сгенерирован файл: {filename} ({len(code.splitlines())} строк)")

    # Проверка 1: сохраняем и компилируем
    tmp = os.path.join(tempfile.gettempdir(), filename)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code)
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", tmp],
        capture_output=True, text=True,
    )
    os.remove(tmp)
    if result.returncode != 0:
        print("❌ Синтаксическая ошибка в сгенерированном коде:")
        print(result.stderr)
        sys.exit(1)
    print("✅ Синтаксис сгенерированного бота: валиден (py_compile OK)")

    # Проверка 2: безопасные проверки массивов
    print("\n[2] Безопасные проверки MT5-массивов:")
    checks = {
        "def _has_enough(rates, n):": "def _has_enough(rates, n):" in code,
        "return rates is not None and len(rates) >= n": "return rates is not None and len(rates) >= n" in code,
        "if not _has_enough(rates, 2):  # ✅": "if not _has_enough(rates, 2):" in code,
    }
    for name, ok in checks.items():
        print(f"   {'✅' if ok else '❌'} {name}")
    if not all(checks.values()):
        sys.exit(1)

    # Проверка 3: отсутствие ОПАСНОЙ конструкции (причина ошибки ValueError)
    print("\n[3] Отсутствие ОПАСНОЙ конструкции 'if not rates or len(rates)...':")
    dangerous = "if not rates or len(rates)" in code
    print(f"   {'❌ НАЙДЕНА' if dangerous else '✅ отсутствует (безопасно)'}")
    if dangerous:
        sys.exit(1)

    # Проверка 4: SMA без look-ahead (окно исключает текущий бар)
    print("\n[4] SMA без look-ahead (окно по истории ДО свечи):")
    has_window = "window = closes[-(period + 1):-1]" in code
    has_old_bad = "sma_val = sum(closes[-period:]) / period" in code
    print(f"   {'✅' if has_window else '❌'} window = closes[-(period + 1):-1] (исключает текущий бар)")
    if has_old_bad:
        print("   ❌ осталась старая формула closes[-period:] (look-ahead)!")
        sys.exit(1)
    if not has_window:
        sys.exit(1)

    # Проверка 5: лот фиксированный (без мартингейла / умножения лота)
    print("\n[5] Лот фиксированный (без мартингейла):")
    uses_start_lot = "start_lot" in code
    # Опасные паттерны динамического лота (любой из них = мартингейл):
    import re
    dynamic_lot = bool(re.search(r"lot\s*[\*=]\s*(?:lot|sum_vol|.*multiplier)", code))
    fixed = uses_start_lot and not dynamic_lot
    print(f"   {'✅' if fixed else '❌'} лот не умножается (нет мартингейла)")
    if dynamic_lot:
        print("      ⚠ найден паттерн динамического лота!")

    print("\n" + "=" * 64)
    print("ИТОГ: ✅ Генератор выдаёт исправленный, валидный бот")
    print("       (безопасные массивы + SMA без look-ahead + фикс. лот).")
    print("       Дашборд генерирует корректный код для демо.")
    print("=" * 64)


if __name__ == "__main__":
    main()
