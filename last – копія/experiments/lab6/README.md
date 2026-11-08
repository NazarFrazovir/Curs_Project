# ЛР6 — фрагменти для live-демо pre-commit хука

Файли мають розширення `.txt`, щоб їх не сканували lizard, pytest і ruff.

| Файл | Що це |
|---|---|
| `movement_actions_messy.py.txt` | «спагеті»-версія матриці прав журналу рухів: вкладені `if`, **CC = 12** |
| `movement_actions_table.py.txt` | та сама логіка як таблиця даних `MOVEMENT_ACTIONS`, **CC = 1** |
| `test_movement_actions.py.txt` | тест поведінки (кладеться в `tests/test_movement_actions.py`) |

Обидві версії еквівалентні: 140 комбінацій (ролі × типи × статуси), 0 розбіжностей.

```bash
cd "last – копія"
# FAIL: хук блокує коміт
cat experiments/lab6/movement_actions_messy.py.txt >> inventory.py
git add inventory.py
git commit -m "feat: add messy code"            # ✖ КОМІТ ЗАБЛОКОВАНО ... CC = 12

# PASS: повертаємо файл і дописуємо табличну версію
git checkout HEAD -- inventory.py
cat experiments/lab6/movement_actions_table.py.txt >> inventory.py
cp experiments/lab6/test_movement_actions.py.txt tests/test_movement_actions.py
git add inventory.py tests/test_movement_actions.py
git commit -m "refactor(inventory): movement actions via lookup table"   # ✔
```
