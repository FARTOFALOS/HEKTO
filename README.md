# HEKTO
ЭМОЦИОНАЛЬНЫЙ ТРЕЙДИНГ АССИСТЕНТ

Локальная персональная система анализа трейдера по голосу и контексту рынка.

Система слушает трейдера через микрофон, фиксирует **что** и **как** он говорит,
привязывает фразы к минутным свечам и со временем выявляет повторяющиеся
психологические паттерны, которые предшествуют ошибкам.

---

## Структура проекта

```
HEKTO/
├── src/
│   ├── config.py              # Конфигурация, пути, константы
│   ├── recorder.py            # Запись микрофона → WAV
│   ├── process_recording.py   # Сегментация, Whisper, голосовые признаки
│   ├── correlate.py           # Привязка речи к рыночным свечам
│   ├── db_writer.py           # SQLite: схема и запись данных
│   └── reporter.py            # Генерация дневных отчётов
├── tests/                     # Pytest-тесты
├── data/
│   ├── raw/                   # Сырые аудиофайлы
│   ├── processed/             # SQLite БД
│   └── patterns/              # Markdown-отчёты и паттерны
├── HEARTBEAT.md               # Расписание агента (daily/weekly/monthly)
├── requirements.txt
└── README.md
```

## Быстрый старт

```bash
# Установка зависимостей
pip install -r requirements.txt

# 1. Запись (нажать Enter для остановки)
python -m src.recorder

# 2. Обработка записи (сегментация → Whisper → голосовые признаки → SQLite)
python -m src.process_recording data/raw/recording_YYYYMMDD_HHMMSS.wav

# 3. Загрузка свечей из CSV
python -m src.correlate ingest candles.csv --symbol BTCUSDT

# 4. Привязка речи к свечам
python -m src.correlate link 2025-01-15 --symbol BTCUSDT

# 5. Генерация дневного отчёта
python -m src.reporter --date 2025-01-15
```

## Тесты

```bash
python -m pytest tests/ -v
```

## Ключевые решения (MVP)

| Тема | Решение |
|------|---------|
| Порог тишины | Динамический: `mean_dB − 14` (per-file) |
| Транскрипция | Whisper (модель `base`, язык `ru`) |
| Голосовые признаки | librosa (pitch, energy, pause ratio, speech rate) |
| Распознавание времени | Цифры (`10:14`) и русские слова (`десять четырнадцать`) |
| Dual Time Model | `spoken_time` (из речи) + `system_time` (часы) + `time_confidence` |
| Хранение | SQLite (WAL mode) + Markdown-отчёты |
| Сегментация | pydub silence detection с динамическим порогом |

## Схема данных

- **audio_files** — метаданные аудиофайлов
- **speech_chunks** — фрагменты речи с текстом, временем, голосовыми признаками
- **market_context** — минутные свечи (OHLCV)
- **daily_state** — дневное состояние трейдера (сон, стресс, заметки)
- **self_catch_links** — связи SELF_CATCH ↔ EMOTION
- **patterns** — выявленные психологические паттерны

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `HEKTO_WHISPER_MODEL` | `base` | Модель Whisper |
| `HEKTO_WHISPER_LANG` | `ru` | Язык для Whisper |
| `HEKTO_SYMBOL` | `BTCUSDT` | Символ по умолчанию |
| `HEKTO_LOG_LEVEL` | `INFO` | Уровень логирования |
