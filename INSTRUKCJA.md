# Instrukcja uruchomienia – GDP & Events Analysis

## Temat projektu
**Wpływ zmian PKB krajów na ilość i typy organizowanych eventów**

Dane źródłowe:
- **World Bank Open Data API** – wskaźnik PKB `NY.GDP.MKTP.CD` (bez klucza API)
- **GDELT Project 2.0 Document API** – wolumen artykułów o eventach per kraj/typ (bez klucza API)

---

## Wymagania wstępne

Zainstalowane na systemie Ubuntu:
- **Docker** ≥ 24.0
- **Docker Compose** ≥ 2.20
- **Git** ≥ 2.34
- Dostęp do Internetu (pobieranie danych z API)

Instalacja na Ubuntu 22.04:
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
newgrp docker
```

---

## Struktura projektu

```
gdp-events-analysis/
├── docker-compose.yml          # środowisko produkcyjne
├── docker-compose.dev.yml      # środowisko developerskie
├── docker-compose.test.yml     # środowisko testowe
├── .env.example                # przykładowe zmienne środowiskowe
├── db/
│   └── init.sql                # schemat bazy danych + dane słownikowe
├── ingestion/                  # moduł akwizycji danych
│   ├── worldbank_ingester.py   # pobieranie PKB z World Bank API
│   ├── gdelt_ingester.py       # pobieranie eventów z GDELT API
│   ├── scheduler.py            # harmonogram ingestion
│   └── models.py               # modele SQLAlchemy
├── processing/
│   └── processor.py            # obliczanie korelacji Pearsona
├── backend/                    # FastAPI REST API
│   ├── main.py
│   ├── routers/
│   │   ├── gdp.py
│   │   ├── events.py
│   │   └── analysis.py
│   └── models.py / schemas.py
├── frontend/
│   └── index.html              # SPA z wykresami Chart.js
└── tests/
    ├── unit/                   # testy jednostkowe (pytest)
    └── performance/            # testy wydajnościowe (locust)
```

---

## KROK 1 – Sklonuj / skopiuj projekt

```bash
# Jeśli masz repozytorium git:
git clone <url-repozytorium>
cd gdp-events-analysis

# Lub skopiuj folder na Ubuntu i przejdź do niego:
cd /path/to/gdp-events-analysis
```

Skopiuj plik środowiskowy:
```bash
cp .env.example .env
```

---

## KROK 2 – Uruchomienie środowiska produkcyjnego

```bash
docker compose up --build -d
```

Usługi uruchomione:
| Usługa     | Port    | Opis                              |
|------------|---------|-----------------------------------|
| frontend   | **80**  | Strona WWW (nginx + Chart.js)     |
| backend    | (80/api)| FastAPI REST API (przez nginx)    |
| db         | wew.    | PostgreSQL 15                     |
| ingestion  | -       | Pobieranie danych (uruchamia się raz, potem co 24h) |
| processing | -       | Obliczanie korelacji              |

Sprawdź status:
```bash
docker compose ps
docker compose logs -f ingestion     # obserwuj pobieranie danych
docker compose logs -f backend
```

> **Uwaga:** Pierwsze pobieranie danych z GDELT może trwać **30–90 minut** (200+ zapytań do API z rate-limitingiem 1 req/s).  
> World Bank API jest szybkie – kilkanaście sekund.

---

## KROK 3 – Weryfikacja

### Sprawdź czy backend odpowiada
```bash
curl http://localhost/health
# Oczekiwany wynik: {"status":"ok","db":"ok","version":"1.0.0"}
```

### Sprawdź liczbę pobranych rekordów
```bash
curl http://localhost/api/v1/analysis/summary
# Przykład: {"countries": 10, "gdp_data": 140, "gdelt_events": 0, ...}
```

### Otwórz frontend
Wejdź w przeglądarkę: `http://localhost`

---

## KROK 4 – Ręczne uruchomienie ingestion (opcjonalne)

Jeśli chcesz pobrać dane osobno:
```bash
# Tylko World Bank (szybko, ~15s):
docker compose exec ingestion python scheduler.py --source worldbank --once

# Tylko GDELT (wolno, 30-90 min):
docker compose exec ingestion python scheduler.py --source gdelt --once

# Po pobraniu – przelicz korelacje:
docker compose exec processing python processor.py
```

---

## KROK 5 – Środowisko developerskie

```bash
# Uruchom środowisko dev (hot-reload, porty otwarte na zewnątrz):
docker compose -f docker-compose.dev.yml up --build

# Backend dostępny na: http://localhost:8000
# Frontend na: http://localhost:3000
# PostgreSQL na: localhost:5432 (user: app, pass: app, db: gdp_events_dev)
# Swagger UI: http://localhost:8000/docs
```

---

## KROK 6 – Testy jednostkowe

### Lokalne (bez Dockera), wymagany Python 3.11+:
```bash
# Zainstaluj zależności:
pip install -r tests/unit/requirements.txt
pip install -r ingestion/requirements.txt
pip install -r processing/requirements.txt
pip install -r backend/requirements.txt

# Uruchom testy:
PYTHONPATH=ingestion:processing:backend pytest tests/unit -v
```

Oczekiwany wynik:
```
tests/unit/test_worldbank.py::TestFetchIndicator::test_returns_empty_on_http_error PASSED
tests/unit/test_worldbank.py::TestFetchIndicator::test_parses_valid_response PASSED
tests/unit/test_gdelt.py::TestParseMonth::test_parses_valid_date PASSED
... (łącznie ~18 testów)
```

### W Dockerze:
```bash
docker compose -f docker-compose.test.yml up unit-tests --build
```

---

## KROK 7 – Testy wydajnościowe (Locust)

### Lokalnie (backend musi działać):
```bash
pip install locust==2.20.1

# Interaktywny dashboard (otwórz http://localhost:8089):
locust -f tests/performance/locustfile.py --host http://localhost

# Headless (bez UI):
locust -f tests/performance/locustfile.py --headless \
  -u 20 -r 5 --run-time 60s \
  --host http://localhost \
  --only-summary
```

### W Dockerze:
```bash
docker compose -f docker-compose.test.yml up perf-tests --build
```

---

## KROK 8 – Dokumentacja API (Swagger)

Po uruchomieniu środowiska dev, Swagger jest dostępny pod:
```
http://localhost:8000/docs       # Swagger UI
http://localhost:8000/openapi.json  # OpenAPI 3.0 JSON
```

Endpointy:
| Metoda | URL | Opis |
|--------|-----|------|
| GET | `/health` | Status systemu |
| GET | `/api/v1/gdp/countries` | Lista krajów |
| GET | `/api/v1/gdp/{country_code}` | Dane PKB kraju |
| GET | `/api/v1/events/types` | Typy eventów |
| GET | `/api/v1/events/{country_code}` | Eventy GDELT kraju |
| GET | `/api/v1/analysis/correlations` | Korelacje PKB–eventy |
| GET | `/api/v1/analysis/summary` | Statystyki bazy |

Przykłady:
```bash
curl "http://localhost/api/v1/gdp/POL?year_start=2018&year_end=2022"
curl "http://localhost/api/v1/events/POL?event_type=PROTEST"
curl "http://localhost/api/v1/analysis/correlations?country_code=POL"
```

---

## KROK 9 – Zatrzymanie systemu

```bash
# Zatrzymaj i usuń kontenery (dane w DB zostają):
docker compose down

# Zatrzymaj i usuń wszystko łącznie z wolumenami:
docker compose down -v
```

---

## Informacje o API źródłowych

### World Bank Open Data API
- **Brak klucza API** – dostęp publiczny
- Endpoint PKB: `https://api.worldbank.org/v2/country/{kod}/indicator/NY.GDP.MKTP.CD?format=json`
- Dokumentacja: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392

### GDELT 2.0 Document API
- **Brak klucza API** – dostęp publiczny
- Endpoint timeline: `https://api.gdeltproject.org/api/v2/doc/doc?query=sourcecountry:US+theme:PROTEST&mode=timelinevol&format=json`
- Dokumentacja: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- Ograniczenie: ~1 zapytanie/sekundę (wbudowane w kod)

---

## Rozwiązywanie problemów

**Problem: Dane GDELT są puste / korelacje nie wyliczone**
```bash
# Sprawdź logi ingestion:
docker compose logs ingestion

# Sprawdź status bazy:
curl http://localhost/api/v1/analysis/summary

# Wymuś ponowne pobranie:
docker compose exec ingestion python scheduler.py --source gdelt --once
```

**Problem: Backend nie startuje**
```bash
docker compose logs backend
# Najczęstsza przyczyna: baza danych jeszcze nie gotowa – odczekaj 10s i spróbuj ponownie
```

**Problem: Port 80 zajęty**
```bash
# W docker-compose.yml zmień port frontendu:
# ports:
#   - "8080:80"
```
