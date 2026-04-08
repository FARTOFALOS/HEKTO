# HEKTO
СИСТЕМА ПОВЕДЕНЧЕСКОГО АНАЛИЗА ТРЕЙДЕРА

Персональная система, которая наблюдает, как трейдер принимает решения,
связывает его внутренний диалог с последствиями и со временем начинает
видеть закономерности, которые сам трейдер не замечает.

Центр системы — **цепочка решения** (trade chain):
от первой мысли о сетапе до исхода сделки.

---

> ### 🔰 Новичок? Никогда не работал с кодом?
> **[Открой INSTALL.md](INSTALL.md)** — там пошаговая инструкция с картинками:
> скачать → открыть терминал → запустить одну команду. Всё.

---

## 🚀 Установка одной командой

### Вариант 1 — Скачать и установить (одна команда)

**macOS / Linux** — открой Терминал и вставь:
```bash
curl -sL https://github.com/FARTOFALOS/HEKTO/archive/refs/heads/main.zip -o /tmp/hekto.zip \
  && unzip -o /tmp/hekto.zip -d ~/HEKTO_install \
  && cd ~/HEKTO_install/HEKTO-main \
  && bash setup_hekto.sh
```

**Windows (PowerShell)** — нажми Win+X → "PowerShell" и вставь:
```powershell
Invoke-WebRequest -Uri "https://github.com/FARTOFALOS/HEKTO/archive/refs/heads/main.zip" -OutFile "$env:TEMP\hekto.zip"
Expand-Archive -Path "$env:TEMP\hekto.zip" -DestinationPath "$HOME\HEKTO_install" -Force
Set-Location "$HOME\HEKTO_install\HEKTO-main"
.\setup_hekto.bat
```

### Вариант 2 — Если уже скачал/клонировал

**macOS / Linux:**
```bash
bash setup_hekto.sh
```

**Windows:**
- Двойной клик на `setup_hekto.bat`
- Или в терминале: `setup_hekto.bat`

**Если Python уже есть:**
```bash
python setup_hekto.py
```

**Проверить, всё ли на месте:**
```bash
python setup_hekto.py --check
```

### После установки

Появятся скрипты быстрого запуска:

| Скрипт | Что делает |
|--------|-----------|
| `hekto_state.sh` / `.bat` | Записать утреннее состояние (сон, стресс) |
| `hekto_record.sh` / `.bat` | Начать запись голоса (Enter = стоп) |
| `hekto_daily.sh` / `.bat` | Полный анализ дня |
| `hekto_report.sh` / `.bat` | Отчёт за день |

---

## Структура проекта

```
HEKTO/
├── src/
│   ├── config.py              # Конфигурация, пути, константы, ключевые слова ролей
│   ├── recorder.py            # Запись микрофона → WAV
│   ├── process_recording.py   # Сегментация → Whisper → голосовые признаки → роль → baseline → DB
│   ├── classify.py            # Классификация чанков по роли (analysis/doubt/hold/exit/...)
│   ├── baseline.py            # Личная базовая линия голоса (rolling 10 дней)
│   ├── signal.py              # Immediate Signal — отклонения от baseline
│   ├── chain.py               # Управление цепочками решений (trade chains)
│   ├── correlate.py           # Привязка речи к рыночным свечам
│   ├── db_writer.py           # SQLite: схема и запись данных (9 таблиц)
│   ├── reporter.py            # Генерация дневных отчётов (chain-centric + паттерны)
│   ├── pattern_engine.py      # Pattern Engine — анализ паттернов (фаза 2–3)
│   ├── daily_state.py         # CLI для дневного состояния трейдера
│   └── run_daily.py           # Один ежедневный запуск всего пайплайна
├── tests/                     # Pytest-тесты (100+ тестов)
├── data/
│   ├── raw/                   # Сырые аудиофайлы
│   ├── processed/             # SQLite БД
│   └── patterns/              # Markdown-отчёты и паттерны
├── requirements.txt
└── README.md
```

## Ценностная ось

```
STATE → BEHAVIOR → OUTCOME
```

Состояние трейдера → порождает речь и поведение → приводит к результату.
Без OUTCOME — нет паттерна. Нет паттерна — нет смысла.

## Два слоя

| Слой | Когда работает | Что делает |
|------|---------------|-----------|
| **Immediate Signal** | С первой недели (≥5 чанков) | Сравнивает голос с личной нормой: «Тон +25% выше baseline» |
| **Pattern Engine** | После 20+ цепочек | Выявляет закономерности: «В 71% случаев слово "подержу" → убыток» |

## Быстрый старт

```bash
# Установка зависимостей
pip install -r requirements.txt

# 1. Записать дневное состояние (интерактивный режим)
python -m src.daily_state

# 1b. Или одной командой
python -m src.daily_state --date 2025-01-15 --sleep 7.5 --stress 3 --physical "нормально" --notes "бодрость"

# 2. Запись (нажать Enter для остановки)
python -m src.recorder

# 3. Полный дневной прогон одной командой
python -m src.run_daily --date 2025-01-15 --candles candles.csv --trades trades.csv

# 4. Обработка записи по шагам (если нужен ручной контроль)
python -m src.process_recording data/raw/recording_YYYYMMDD_HHMMSS.wav

# 5. Загрузка свечей из CSV
python -m src.correlate ingest candles.csv --symbol BTCUSDT

# 6. Привязка речи к свечам
python -m src.correlate link 2025-01-15 --symbol BTCUSDT

# 7. Генерация дневного отчёта
python -m src.reporter --date 2025-01-15

# 8. Запуск Pattern Engine вручную (если нужен отдельный анализ)
python -m src.pattern_engine --db data/processed/hekto.db
```

## Тесты

```bash
python -m pytest tests/ -v
```

## Типология высказываний (chunk roles)

| Роль | Примеры | Определение |
|------|---------|------------|
| analysis | «вижу сопротивление», «жду реакции» | Ключевые слова (MVP) |
| expectation | «думаю пойдёт», «скорее всего» | Ключевые слова (MVP) |
| doubt | «не уверен», «не стоит, но» | Ключевые слова (MVP) |
| hold | «подержу», «ещё чуть-чуть» | Ключевые слова (MVP) |
| exit | «закрыл», «вышел» | Ключевые слова + trade event |
| reflection | «надо было», «зря вошёл» | После закрытия цепочки |

## Схема данных (9 таблиц)

### audio_files
Метаданные аудиофайлов.

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| filename | TEXT | Имя файла |
| recorded_at | TEXT | ISO-8601 время записи |
| duration_sec | REAL | Длительность в секундах |
| sample_rate | INTEGER | Частота дискретизации (16000) |
| silence_threshold_db | REAL | Динамический порог тишины |
| mean_db | REAL | Средний уровень громкости |

### trade_chains 🎯
**ЦЕНТР СИСТЕМЫ**: цепочки решений.

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| symbol | TEXT | Торговый инструмент (BTCUSDT) |
| direction | TEXT | long / short / NULL |
| outcome | TEXT | profit / loss / breakeven / no_entry / stop / NULL |
| pnl | REAL | Финансовый результат |
| status | TEXT | incomplete / complete |
| opened_at | TEXT | ISO-8601 начало цепочки |
| closed_at | TEXT | ISO-8601 завершение цепочки |

### speech_chunks
Фрагменты речи с текстом, ролью, chain_id, baseline-отклонениями.

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| audio_file_id | INTEGER FK | Ссылка на audio_files |
| chunk_index | INTEGER | Порядковый номер в аудиофайле |
| chunk_start_ms | INTEGER | Начало фрагмента (мс) |
| chunk_end_ms | INTEGER | Конец фрагмента (мс) |
| text | TEXT | Транскрипция (Whisper) |
| spoken_time | TEXT | Время, произнесённое трейдером |
| system_time | TEXT | Реальное время (wall-clock) |
| voice_features | TEXT (JSON) | Голосовые признаки |
| baseline_deviation | TEXT (JSON) | Отклонения от базовой линии |
| chunk_role | TEXT | analysis/expectation/doubt/hold/exit/reflection/other |
| chain_id | INTEGER FK | Ссылка на trade_chains |
| self_catch_flag | INTEGER | 1 = self-catch событие |

### trade_events
Торговые события (entry/exit) из CSV / голоса / ручной метки.

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| chain_id | INTEGER FK | Ссылка на trade_chains |
| event_type | TEXT | entry / exit |
| symbol | TEXT | Торговый инструмент |
| direction | TEXT | long / short |
| price | REAL | Цена |
| quantity | REAL | Объём |
| timestamp | TEXT | ISO-8601 |
| source | TEXT | csv / voice / manual |

### market_context
Минутные свечи (OHLCV + ATR + trend).

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| timestamp | TEXT | ISO-8601 время открытия свечи |
| symbol | TEXT | Инструмент |
| timeframe | TEXT | По умолчанию «1m» |
| open/high/low/close | REAL | OHLC |
| volume | REAL | Объём |
| volatility | REAL | Волатильность |
| atr | REAL | ATR |
| trend | TEXT | up / down / flat |

### voice_baseline
Личная базовая линия голоса (rolling, per day).

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| date | TEXT UNIQUE | Дата (YYYY-MM-DD) |
| chunk_count | INTEGER | Количество чанков в базе |
| pitch_mean/pitch_std | REAL | Средний тон и стд. отклонение |
| speech_rate_mean/speech_rate_std | REAL | Темп речи |
| energy_mean/energy_std | REAL | Энергия голоса |
| pause_ratio_mean/pause_ratio_std | REAL | Доля пауз |

### daily_state
Дневное состояние трейдера (сон, стресс, заметки).

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| date | TEXT UNIQUE | Дата (YYYY-MM-DD) |
| sleep_hours | REAL | Часов сна |
| stress_level | INTEGER | 1-10 |
| physical_state | TEXT | Описание физического состояния |
| notes | TEXT | Свободные заметки |

### self_catch_links
Связи SELF_CATCH ↔ EMOTION событий.

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| self_catch_event_id | INTEGER FK | ID self-catch чанка |
| emotion_event_id | INTEGER FK | ID эмоционального чанка |
| time_delta_seconds | REAL | Время между событиями |
| same_trade | INTEGER | 1 = в рамках одной сделки |

### patterns
Выявленные паттерны (условия, доказательства, уровень доверия).

| Поле | Тип | Описание |
|------|-----|----------|
| pattern_id | INTEGER PK | Автоинкремент |
| title | TEXT | Название паттерна |
| description | TEXT | Описание |
| conditions | TEXT (JSON) | Условия срабатывания |
| evidence | TEXT (JSON) | Список chain_id-доказательств |
| counter_evidence | TEXT (JSON) | Список chain_id-контрпримеров |
| evidence_count | INTEGER | Количество доказательств |
| counter_evidence_count | INTEGER | Количество контрпримеров |
| confidence | REAL | 0.0–1.0 |
| confidence_level | TEXT | low / medium / high |
| status | TEXT | candidate / confirmed / rejected |

## Примеры SQL-запросов

```sql
-- Все завершённые цепочки с P&L
SELECT id, symbol, direction, outcome, pnl, opened_at, closed_at
FROM trade_chains
WHERE status = 'complete'
ORDER BY opened_at DESC;

-- Процент прибыльных сделок
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN outcome = 'profit' THEN 1 ELSE 0 END) as profits,
    ROUND(SUM(CASE WHEN outcome = 'profit' THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) as win_rate_pct
FROM trade_chains
WHERE status = 'complete' AND outcome IN ('profit', 'loss');

-- Чанки с наибольшим отклонением голоса от нормы
SELECT sc.id, sc.text, sc.chunk_role, sc.baseline_deviation, tc.outcome
FROM speech_chunks sc
JOIN trade_chains tc ON sc.chain_id = tc.id
WHERE sc.baseline_deviation IS NOT NULL
ORDER BY sc.id DESC
LIMIT 20;

-- Связь ролей с исходами (основа для Pattern Engine)
SELECT
    sc.chunk_role,
    tc.outcome,
    COUNT(*) as count
FROM speech_chunks sc
JOIN trade_chains tc ON sc.chain_id = tc.id
WHERE tc.status = 'complete' AND tc.outcome IN ('profit', 'loss')
GROUP BY sc.chunk_role, tc.outcome
ORDER BY sc.chunk_role, tc.outcome;

-- Топ паттернов по уверенности
SELECT title, confidence, confidence_level, evidence_count, counter_evidence_count, status
FROM patterns
WHERE status IN ('candidate', 'confirmed')
ORDER BY confidence DESC;

-- Средний P&L по дням с состоянием
SELECT ds.date, ds.sleep_hours, ds.stress_level,
       AVG(tc.pnl) as avg_pnl, COUNT(tc.id) as trades
FROM daily_state ds
LEFT JOIN trade_chains tc ON tc.opened_at LIKE ds.date || 'T%'
WHERE tc.status = 'complete'
GROUP BY ds.date
ORDER BY ds.date DESC;

-- Голосовая базовая линия за последние 10 дней
SELECT date, chunk_count, pitch_mean, speech_rate_mean, energy_mean, pause_ratio_mean
FROM voice_baseline
ORDER BY date DESC
LIMIT 10;
```

## Финальная реализация (фаза 3 — Инсайты)

### Что реализовано

1. **Критический фикс: параллельные позиции** — `link_events_to_chains()` теперь корректно обрабатывает несколько одновременных позиций в одном символе. При выходе используется price-based matching (ближайшая цена входа) с FIFO-fallback.

2. **Pattern Engine** (`src/pattern_engine.py`) — полноценный анализатор паттернов:
   - Автоматический запуск после 20+ завершённых цепочек
   - 4 типа паттернов: role-outcome, voice-outcome, duration-outcome, keyword-outcome
   - Каждый паттерн: условие, доказательства, контрпримеры, confidence (0.0–1.0), confidence_level (Low/Medium/High)
   - Сохранение в таблицу `patterns` и Markdown-отчёты в `data/patterns/`
   - Предиктивный сигнал: `get_predictive_signal()` предупреждает о совпадении с известными паттернами

3. **CLI для daily_state** (`src/daily_state.py`) — удобный ввод дневного состояния:
   - Интерактивный режим (без аргументов)
   - Командная строка: `--sleep`, `--stress`, `--physical`, `--notes`
   - Просмотр: `--show`

4. **Интеграция в run_daily** — Pattern Engine запускается автоматически в ежедневном пайплайне.

5. **Reporter обновлён** — дневные отчёты теперь включают секцию обнаруженных паттернов.

### Запуск Pattern Engine

```bash
# Автоматически (в составе ежедневного прогона)
python -m src.run_daily --date 2025-01-15 --trades trades.csv

# Вручную
python -m src.pattern_engine --db data/processed/hekto.db

# Ввод дневного состояния
python -m src.daily_state --date 2025-01-15 --sleep 7 --stress 4
```

## Эволюция системы

| Фаза | Цепочки | Что происходит |
|------|---------|---------------|
| 0 — Привычка | 0–20 | Система стабильно работает каждый день |
| 1 — Первые сигналы | 20–50 | Baseline сформирован, Immediate Signal работает |
| 2 — Гипотезы | 50–100 | Первые паттерны с уровнем доверия Low |
| 3 — Инсайты | 100+ | Устойчивые паттерны, предиктивные сигналы |

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `HEKTO_WHISPER_MODEL` | `base` | Модель Whisper |
| `HEKTO_WHISPER_LANG` | `ru` | Язык для Whisper |
| `HEKTO_SYMBOL` | `BTCUSDT` | Символ по умолчанию |
| `HEKTO_LOG_LEVEL` | `INFO` | Уровень логирования |
