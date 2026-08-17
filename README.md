# BARS to FIS GIA Integration Bridge / Мост интеграции БАРС.Образование в ФИС ГИА и Приема

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%207%20%7C%2010%20%7C%2011%20%7C%20Linux-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Автоматизированный инструмент для переноса заявлений абитуриентов из региональной системы **«БАРС.Образование - Электронный Колледж»** в федеральную информационную систему **«ФИС ГИА и Приема»**.*

---

## 🇷🇺 RU: Русская версия (Russian Version)

- [Идея и назначение](#-идея-и-назначение)
- [Архитектура проекта](#-архитектура-проекта)
- [Ключевые возможности](#-ключевые-возможности)
- [Логика работы и безопасность данных](#-логика-работы-и-безопасность-данных)
- [Быстрый старт (Quick Start)](#-быстрый-старт)
  - [1. Настройка и запуск Клиента (БАРС)](#1-настройка-и-запуск-клиента-bars-client)
  - [2. Настройка и запуск Сервера (ФИС ГИА)](#2-настройка-и-запуск-сервера-fis-gia-runner)
- [Структура проекта](#-структура-проекта)
- [Техническая документация](#-техническая-документация)

---

## 🌐 EN: English Version

- [Project Mission & Concept](#-project-mission--concept)
- [Architecture Overview](#-architecture-overview)
- [Key Features](#-key-features)
- [Processing Pipeline & Data Safety](#-processing-pipeline--data-safety)
- [Quick Start Guide](#-quick-start-guide)
  - [1. Client Setup (BARS Extraction)](#1-client-setup-bars-extraction)
  - [2. Server Setup (FIS GIA Submission)](#2-server-setup-fis-gia-submission)
- [Repository Structure](#-repository-structure)
- [Technical Documentation](#-technical-documentation)

---

# 🇷🇺 RU: Документация (Russian)

## 💡 Идея и назначение

В период приемной кампании сотрудники приемных комиссий колледжей и техникумов сталкиваются с колоссальной рутинной нагрузкой: одни и те же сведения об абитуриентах (ФИО, паспортные данные, СНИЛС, адрес, оценки аттестата, выбранные специальности и условия обучения) приходится заполнять **дважды**:
1. Сначала в региональную систему СПО (**БАРС.Web-Образование / Электронный Колледж**).
2. Затем вручную построчно в федеральную систему (**ФИС ГИА и Приема**) через многошаговый мастер добавления заявления.

**Задача проекта** — полностью автоматизировать этот процесс и свести его к **однократному вводу**:
1. Оператор регистрирует заявление в БАРС.
2. Клиентский модуль выгружает заявления из БАРС в структурированный `applications.json`.
3. Серверный модуль через защищенный шлюз ViPNet автоматически переносит данные в ФИС ГИА, проходя все шаги мастера за секунды.

---

## 🏛 Архитектура проекта

Проект разделен на две логические части: **`client`** и **`server`** *(названия исторические; фактически это два автономных скрипта автоматизации для разных рабочих мест)*:

```
┌─────────────────────────────────┐               ┌────────────────────────────────────────┐
│      Обычный ПК / Ноутбук       │               │      Защищенный ПК (ViPNet Client)     │
│   (Доступ к БАРС.Образование)   │               │       (Шлюз в сеть ФИС ГИА)            │
│                                 │               │                                        │
│  ┌───────────────────────────┐  │               │  ┌──────────────────────────────────┐  │
│  │   client/                 │  │               │  │   server/                        │  │
│  │   fetch_applications.py   │  │               │  │   send_to_fis.py                 │  │
│  └─────────────┬─────────────┘  │               │  └──────────────────▲───────────────┘  │
└────────────────┼────────────────┘               └─────────────────────┼──────────────────┘
                 │                                                      │
                 ▼                                                      │
      [ applications.json ] ────────────────────────────────────────────┘
     (Перенос файла / экспорт)
```

1. **`client/` (БАРС)** — запускается на любом рабочем компьютере, имеющем доступ к порталу БАРС.Образование. Подключается по сессионным cookie, запрашивает заявления выбранного периода и сохраняет готовый JSON-файл.
2. **`server/` (ФИС ГИА)** — запускается на аттестованном компьютере в защищенном контуре с активным **ViPNet Client**. Считывает подготовленный `applications.json` (`parsed_details.json`), сопоставляет специальности и пакетом отправляет заявления на сервер ФИС ГИА. Совместим с **Windows 7, 10, 11 и Linux**.

---

## ✨ Ключевые возможности

- 🚀 **Полная автоматизация мастера ФИС ГИА**: автоматическое выполнение всех 4 шагов создания заявления (Шаг 1 `NewWz0`, Шаг 2 `UpdWz1`, Шаг 3 `setEditDocument`, подтверждение оригиналов документов и финализация `SaveWz5`).
- 🛡 **Безопасный статус «Новый»**: заявления создаются в статусе черновика («Новый»), что позволяет сотрудникам приемной комиссии перепроверить и при необходимости отредактировать или откатить заявления вручную перед окончательным проведением.
- 🔢 **Автоматическая сквозная нумерация**: генерация номеров заявлений вида `1-26`, `2-26` с автоинкрементом (`ID_START`, `ID_SUFFIX`).
- 🔍 **Умное обнаружение дубликатов и очистка черновиков**: скрипт перед отправкой проверяет, не подавал ли абитуриент заявление ранее (`LoadApplicationNewRecords`). Если обнаружено существующее заявление, созданный черновик автоматически удаляется (`DeleteApplications`), исключая фантомные дубликаты.
- 🔄 **Автоматический повтор при коллизии номеров**: если номер заявления занят на сервере, счетчик автоматически инкрементируется и повторяет отправку (до 5 попыток). Если стартовый номер занят с первого раза — выполнение безопасно прерывается.
- 🧩 **Гибкое сопоставление специальностей (`specialties.json`)**: нечеткое сопоставление наименований и кодов специальностей из БАРС с аббревиатурами конкурсных групп ФИС ГИА (например, *«Сестринское дело»* $\rightarrow$ `СД-126`).
- 🌐 **Поддержка двух контуров (Dev / Prod)**: удобное переключение между тестовым контуром (порт `8383`) и основным (порт `8080`) через флаги `--dev` и `--prod`.
- 📝 **Двойное логирование**: потоковый вывод в консоль и запись в файлы логов с меткой времени (`server/logs/log_*.txt` и `server/logs/response_*.json`).

---

## 🔄 Логика работы и безопасность данных

### Пайплайн обработки каждого заявления:
1. **Шаг 1 (`NewWz0`)**: Создание чернового заявления с указанием года кампании, паспортных данных, даты регистрации и приоритетов выбранных конкурсных групп.
2. **Проверка на повтор**: Если абитуриент уже есть в базе, скрипт запрашивает список его заявлений, фиксирует факт дубликата, удаляет созданный на шаге 1 черновик и переходит к следующему студенту.
3. **Шаг 1.5**: Определение внутреннего `EntrantID` и `IdentityDocumentID`.
4. **Шаг 2 (`UpdWz1`)**: Ввод личных данных (ФИО, СНИЛС, пол, дата рождения, кем выдан паспорт, код подразделения, адрес регистрации, регион, тип населенного пункта, признак ЕПГУ).
5. **Шаг 3 (`setEditDocument`)**: Прикрепление документа об образовании (Аттестат об основном общем / среднем общем образовании, серия, номер, дата выдачи, организация, средний балл GPA).
6. **Подтверждение оригиналов (`SetDocumentOriginalReceived`)**: Автоматическая простановка отметок о предоставлении оригинала паспорта и оригинала аттестата датой регистрации заявления.
7. **Шаг 4 (`SaveWz5`)**: Перевод заявления из состояния «редактируется» в статус **«Новый»**. Заявление появляется в списке новых и готово к штатной проверке оператором.

---

## 🚀 Быстрый старт

### 1. Настройка и запуск Клиента (BARS Client)

1. Перейдите в папку `client/` и установите зависимости:
   ```bash
   cd client
   pip install -r requirements.txt
   ```
2. Скопируйте файл `.env.example` в `config.env` или `.env`:
   ```bash
   copy .env.example config.env
   ```
3. Откройте в браузере систему БАРС.Образование, откройте DevTools (F12) $\rightarrow$ вкладка **Application / Storage** $\rightarrow$ **Cookies** и скопируйте значения:
   ```ini
   BARS_BASE_URL=url_электронного_колледжа
   SSUZ_SESSIONID=ваш_значение_cookie_ssuz_sessionid
   CSRFTOKEN=ваш_значение_cookie_csrftoken
   ```
4. Настройте параметры выборки:
   ```ini
   # ID приемной кампании (например, 41)
   BARS_PERIOD_ID=41

   # Количество заявлений для выгрузки за один раз
   BARS_LIMIT=25

   # Смещение начальной записи (для пагинации)
   BARS_START=0

   # Опциональные фильтры:
   BARS_FILTER=          # Поиск по ФИО
   BARS_FILTER_1=        # Начальная дата (например 01.07.2026)
   BARS_FILTER_2=        # Конечная дата (например 15.08.2026)
   BARS_SORT=date        # Поле сортировки
   BARS_DIR=DESC         # Порядок сортировки (DESC / ASC)
   ```
5. Запустите скрипт выгрузки:
   ```bash
   py .\fetch_applications.py
   ```
6. В папке `client/` будет сформирован файл **`applications.json`** с данными абитуриентов. Скопируйте его на защищенный компьютер в файл `server/parsed_details.json`.

---

### 2. Настройка и запуск Сервера (FIS GIA Runner)

1. Перенесите папку `server/` на защищенный компьютер, где установлен **ViPNet Client**, и установите зависимости:
   ```bash
   cd server
   pip install -r requirements.txt
   ```
2. **Убедитесь, что ViPNet запущен и соединение с защищенной сетью активно.** Дополнительных настроек сети не требуется — Python будет автоматически отправлять запросы через открытый шлюз.
3. Создайте файлы конфигурации `dev.env` (тестовый контур) и/или `prod.env` (боевой контур) на основе `.env.example`:
   ```bash
   copy .env.example dev.env
   copy .env.example prod.env
   ```
4. Заполните конфигурационные файлы:
   ```ini
   # Порт 8383 для dev-контура, 8080 для prod-контура
   FIS_BASE_URL=http://10.0.3.1:8383

   # Токены авторизации (извлекаются из браузера после входа в ФИС ГИА)
   ACCESS_TOKEN=токен_доступа_bearer
   REFRESH_TOKEN=токен_обновления

   # Идентификаторы кампании и организации в ФИС ГИА (из DevTools при выборе кампании). FIS_INSTITUTION_ID - опционален
   FIS_CAMPAIGN_ID=12345
   FIS_INSTITUTION_ID=6789

   # Дата регистрации заявлений (dd.mm.yyyy)
   REGISTRATION_DATE=05.08.2026

   # Настройки автонумерации заявлений
   ID_START=1
   ID_SUFFIX=-26
   ```

   > ⚠️ **Важно**: Перед каждым запуском проверяйте актуальный свободный номер заявления в ФИС ГИА и указывайте его в `ID_START`. Если указанный номер уже занят, скрипт прервет работу с предупреждением.

5. **Настройка сопоставления специальностей (`server/specialties.json`)**:
   Отредактируйте `specialties.json`, сопоставив ключевые слова из наименований БАРС с префиксами конкурсных групп ФИС ГИА:
   ```json
   [
     {
       "keywords": ["сестринск", "34.02.01"],
       "prefixes": ["СД"],
       "comment": "Сестринское дело -> СД-126"
     },
     {
       "keywords": ["мехатроника", "15.02.10"],
       "prefixes": ["МР-126", "МР-226", "МР"],
       "comment": "Мехатроника и робототехника"
     }
   ]
   ```

6. **Запуск интеграции**:
   ```bash
   # Запуск на тестовом контуре (dev.env):
   py .\send_to_fis.py --dev

   # Запуск на боевом контуре (prod.env):
   py .\send_to_fis.py --prod

   # Запуск с указанием произвольного JSON-файла:
   py .\send_to_fis.py path/to/applications.json --prod
   ```

7. **Проверка результатов**:
   По окончании работы скрипт выведет итоговую сводку в консоль и сохранит детальные отчеты:
   - Текстовый лог: `server/logs/log_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.txt`
   - Результаты по каждому заявлению: `server/logs/response_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.json`

---

## 📁 Структура проекта

```
FISGIA/
├── client/                     # Клиентская часть (Выгрузка из БАРС)
│   ├── requirements.txt        # Зависимости клиента
│   ├── config.py               # Загрузчик .env / config.env
│   ├── parsers.py              # Парсеры ExtJS, фильтров дат, специальностей
│   ├── bars_client.py          # HTTP-клиент БАРС.Образование
│   ├── extractor.py            # Логика обхода и сборки заявлений
│   ├── fetch_applications.py   # Главный исполняемый CLI скрипт клиента
│   ├── config.env              # Локальный файл конфигурации
│   └── applications.json       # Выгруженный результат
│
├── server/                     # Серверная часть (Перенос в ФИС ГИА)
│   ├── requirements.txt        # Зависимости сервера
│   ├── core/                   # Базовые инфраструктурные модули
│   │   ├── config.py           # Менеджер окружений (dev/prod), CLI-аргументы
│   │   ├── logger.py           # Потоковый логер TeeLogger
│   │   └── helpers.py          # Форматирование GPA, извлечение ID, адреса
│   ├── services/               # Бизнес-логика взаимодействия с ФИС ГИА
│   │   ├── specialties.py      # Сопоставление специальностей (specialties.json)
│   │   ├── fis_client.py       # HTTP-клиент ФИС ГИА (токены, discovery, черновики)
│   │   ├── submission.py       # Пайплайн шагов отправки одного заявления
│   │   └── batch_runner.py     # Пакетный запуск, автосчетчик, повторные запросы
│   ├── send_to_fis.py          # Главный исполняемый CLI скрипт сервера
│   ├── specialties.json        # Справочник соответствия специальностей
│   ├── dev.env                 # Конфигурация тестового контура (:8383)
│   ├── prod.env                # Конфигурация боевого контура (:8080)
│   └── logs/                   # Логи запусков и JSON-ответы
│
├── requirements.txt            # Общие Python-зависимости
├── TECHNICAL_DOCS.md           # Полная техническая документация API
└── README.md                   # Документация проекта
```

---

<br><br>

---

# 🌐 EN: Documentation (English)

## 💡 Project Mission & Concept

During the college admissions season, admissions committee officers suffer from extreme double-data-entry overhead. The exact same applicant information (personal data, passport, SNILS, residence address, certificate marks, chosen study programs, and budget/paid funding types) must be entered **twice**:
1. First, into the regional vocational education portal (**BARS.Education / Electronic College**).
2. Second, manually re-typed field-by-field into the Russian Federal Information System (**FIS GIA & Admission**) across multiple complex web wizards.

**This project automates the entire workflow**:
1. Admission officers register applications in BARS once.
2. The client tool extracts structured application data into `applications.json`.
3. The runner script connects to the FIS GIA server over the secure ViPNet VPN gateway and automatically registers all applications in seconds.

---

## 🏛 Architecture Overview

The system consists of two decoupled components:

1. **`client/` (BARS Extractor)**: Runs on any workstation with web access to BARS. Authenticates via session cookies, queries M3/ExtJS endpoints, parses enrollees and declaration study plans, and outputs `applications.json`.
2. **`server/` (FIS GIA Runner)**: Runs on a certified secure machine with active **ViPNet Client** connection. Reads `applications.json` (or `parsed_details.json`), matches specialties against competitive groups, and executes the multi-step REST wizard. Fully compatible with **Windows 7, 10, 11, and Linux**.

---

## ✨ Key Features

- 🚀 **Full End-to-End Wizard Automation**: Automates Step 1 (`NewWz0`), Step 2 (`UpdWz1`), Step 3 (`setEditDocument`), original document verifications, and Step 4 finalization (`SaveWz5`).
- 🛡 **Safe Draft Status ("Новый")**: Applications are created in editable draft status (*"New"* / *«Новый»*), allowing manual verification, adjustment, or rollback before formal enrollment.
- 🔢 **Auto-Incrementing Application Numbers**: Generates sequential numbers (e.g., `1-26`, `2-26`) based on `ID_START` and `ID_SUFFIX`.
- 🔍 **Duplicate Detection & Automatic Cleanup**: Checks if an entrant already has an application in the active campaign (`LoadApplicationNewRecords`). If a duplicate draft was created, it automatically calls `DeleteApplications` to prevent phantom entries.
- 🔄 **Collision Auto-Retry**: If an application number is already taken, the counter advances automatically and retries submission (up to 5 attempts).
- 🧩 **Specialty Prefix Mapping Engine (`specialties.json`)**: Fuzzy keyword-to-prefix matching connecting BARS program names with FIS GIA competitive groups (e.g., *"Nursing"* $\rightarrow$ `СД-126`).
- 🌐 **Dual-Environment Support**: Seamless switching between test contour (port `8383`) and main production (port `8080`) via `--dev` and `--prod` CLI switches.
- 📝 **Dual Stream Logging**: Simultaneous console streaming and timestamped file recording (`server/logs/log_*.txt` & `server/logs/response_*.json`).

---

## 🔄 Processing Pipeline & Data Safety

For each application in the batch:
1. **Step 1 (`NewWz0`)**: Creates application draft with campaign ID, passport data, registration date, and competitive group priorities.
2. **Existing Entrant Check**: Queries existing records. If an active application is found, deletes the draft and marks the entry as `ALREADY_EXISTS`.
3. **Step 1.5**: Resolves server-side `EntrantID` and `IdentityDocumentID`.
4. **Step 2 (`UpdWz1`)**: Fills in applicant details (name, SNILS, birth date, passport issuer, subdivision code, registration address, region, town type, EPGU flag).
5. **Step 3 (`setEditDocument`)**: Attaches education certificate (General / Secondary education diploma, series, number, issue date, issuing organization, GPA).
6. **Original Documents Confirmation (`SetDocumentOriginalReceived`)**: Confirms receipt of both Passport and Certificate originals on the registration date.
7. **Step 4 (`SaveWz5`)**: Changes status from *Editing* to **"Новый" (New)**. The application is now ready for committee review.

---

## 🚀 Quick Start Guide

### 1. Client Setup (BARS Extraction)

1. Open the `client/` directory and install dependencies:
   ```bash
   cd client
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `config.env` (or `.env`):
   ```bash
   copy .env.example config.env
   ```
3. Open BARS in your browser, press F12 (DevTools) $\rightarrow$ **Application / Storage** $\rightarrow$ **Cookies**, and paste the values:
   ```ini
   BARS_BASE_URL=https://your_college_bars_domain
   SSUZ_SESSIONID=your_ssuz_sessionid_cookie_value
   CSRFTOKEN=your_csrftoken_cookie_value
   ```
4. Configure period and filters:
   ```ini
   BARS_PERIOD_ID=41
   BARS_LIMIT=25
   BARS_START=0
   BARS_SORT=date
   BARS_DIR=DESC
   ```
5. Run the extractor:
   ```bash
   py .\fetch_applications.py
   ```
6. The resulting **`applications.json`** will be generated inside `client/`. Copy it to the secure computer into `server/parsed_details.json`.

---

### 2. Server Setup (FIS GIA Submission)

1. Place `server/` onto the secure computer with **ViPNet Client** installed and install dependencies:
   ```bash
   cd server
   pip install -r requirements.txt
   ```
2. **Ensure ViPNet Client is running and connected.**
3. Copy `.env.example` to `dev.env` and/or `prod.env`:
   ```bash
   copy .env.example dev.env
   copy .env.example prod.env
   ```
4. Configure target parameters:
   ```ini
   # Port 8383 for dev/test contour, 8080 for production
   FIS_BASE_URL=http://10.0.3.1:8383

   ACCESS_TOKEN=your_access_token
   REFRESH_TOKEN=your_refresh_token

   FIS_CAMPAIGN_ID=12345
   FIS_INSTITUTION_ID=6789 # optional

   REGISTRATION_DATE=05.08.2026
   ID_START=1
   ID_SUFFIX=-26
   ```

   > ⚠️ **Note**: Check for the next available application number in FIS GIA before each run and set it in `ID_START`. If the starting number is already in use, the script aborts immediately.

5. Configure specialty mappings in `server/specialties.json`:
   ```json
   [
     {
       "keywords": ["medical", "nursing"],
       "prefixes": ["M"],
       "comment": "nursing -> M-126"
     }
   ]
   ```

6. Run submission:
   ```bash
   # Test environment:
   py .\send_to_fis.py --dev

   # Production environment:
   py .\send_to_fis.py --prod
   ```

7. Review execution logs in `server/logs/`.

---

## 📖 Technical Documentation

For deep technical details regarding HTTP endpoints, ExtJS AST parsing, FIS GIA REST/WZ schemas, sequence diagrams, and collision handling matrices, refer to **[TECHNICAL_DOCS.md](TECHNICAL_DOCS.md)**.
