# Instrukcja uruchomienia – GDP & Events Analysis

## Temat projektu
**Wpływ zmian PKB krajów na ilość i typy organizowanych eventów**

Dane źródłowe:
- **World Bank Open Data API** – wskaźnik PKB `NY.GDP.MKTP.CD` oraz stopa wzrostu `NY.GDP.MKTP.KD.ZG` (bez klucza API)
- **GDELT Project v1 GKG** – wolumen artykułów per kraj/typ dla lat 2013–2016 (pliki dzienne, bez klucza API)
- **GDELT Project 2.0 Document API** – wolumen artykułów per kraj/typ dla lat 2017–2025 (bez klucza API)

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
│   ├── gdelt_ingester.py       # pobieranie eventów z GDELT v2 API (2017+)
│   ├── gdelt_v1_ingester.py    # pobieranie eventów z GDELT v1 GKG (2013–2016)
│   ├── seed_gdelt_fallback.py  # syntetyczny seed gdy GDELT API jest niedostępne
│   ├── scheduler.py            # harmonogram ingestion (World Bank + GDELT v1 + v2)
│   └── models.py               # modele SQLAlchemy
├── processing/
│   └── processor.py            # obliczanie korelacji Pearsona (tło, co 1h)
├── backend/                    # FastAPI REST API
│   ├── main.py
│   ├── routers/
│   │   ├── gdp.py              # endpointy PKB
│   │   ├── events.py           # endpointy GDELT
│   │   └── analysis.py         # korelacje, lag, anomalie
│   ├── models.py
│   └── schemas.py
├── frontend/
│   └── index.html              # SPA z wykresami Chart.js
├── tests/
│   ├── unit/                   # testy jednostkowe (pytest)
│   └── performance/            # testy wydajnościowe (locust)
├── README.md                   # opis projektu i stack technologiczny
└── INSTRUKCJA.md               # ten plik
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
| Usługa     | Port    | Opis                                                      |
|------------|---------|-----------------------------------------------------------|
| frontend   | **80**  | Strona WWW (nginx + Chart.js)                             |
| backend    | (80/api)| FastAPI REST API (przez nginx)                            |
| db         | wew.    | PostgreSQL 15                                             |
| ingestion  | –       | Pobieranie danych (uruchamia się raz przy starcie, potem co 24h) |
| processing | –       | Obliczanie korelacji Pearsona (uruchamia się raz, potem co 1h)   |

Sprawdź status:
```bash
docker compose ps
docker compose logs -f ingestion     # obserwuj pobieranie danych
docker compose logs -f backend
```

> **Uwaga dotycząca GDELT:** Ingestion GDELT składa się z dwóch etapów:
> - **v1 GKG 2013–2016** (~60–90 min) – pliki dzienne z `data.gdeltproject.org`
> - **v2 Doc API 2017–2025** (~8 min) – 60 zapytań do API z odstępem 8 s
>
> GDELT v2 API może blokować requesty automatyczne (Cloudflare).
> Jeśli tak się stanie, skorzystaj z seeda syntetycznego (→ KROK 4B).

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
# Oczekiwany wynik po pełnej ingestii:
# {"countries": 10, "gdp_data": 150, "gdelt_events": 11520, "analysis_results": 60}
```

### Sprawdź zasięg lat danych GDELT
```bash
docker compose exec db psql -U app gdp_events -c \
  "SELECT MIN(year), MAX(year), COUNT(*) FROM gdelt_events;"
```

### Otwórz frontend
Wejdź w przeglądarkę: `http://localhost`

> **VirtualBox (dostęp z Windows hosta):** Ustaw przekierowanie portów:
> VM → Sieć → Zaawansowane → Przekierowanie portów: `8080 (host) → 80 (gość)`,
> następnie otwórz `http://localhost:8080`.

---

## KROK 4 – Ręczne uruchomienie ingestion

### 4A – Standardowa ingestia (gdy API jest dostępne)

```bash
# Tylko World Bank (szybko, ~30s):
docker compose run --rm ingestion python scheduler.py --source worldbank --once

# GDELT – automatycznie uruchamia v1 GKG (2013–2016), potem v2 (2017–2025):
docker compose run --rm ingestion python scheduler.py --source gdelt --once

# Oba źródła naraz:
docker compose run --rm ingestion python scheduler.py --source all --once
```

Logi GDELT v1 (postęp co miesiąc):
```
GKG v1 ingestion starting: 2013-04-01 → 2016-12-31 (~1371 days)
GKG v1: 2013-04 committed (847 records). Progress: 30/1371 days
...
GKG v1 ingestion complete: ~42000 records
```

Logi GDELT v2:
```
GDELT ingesting POL/PROTEST (1/60)
GDELT OK country=POL theme=PROTEST – 412 data points
...
GDELT ingestion complete: 7200 records
```

### 4B – Seed syntetyczny (gdy GDELT v2 API jest zablokowane)

GDELT v2 Doc API może blokować automatyczne requesty przez Cloudflare.
Objawem są błędy `429 Too Many Requests` lub brak odpowiedzi w logach.

```bash
# Zatrzymaj ingestion żeby nie spamował zablokowanego API:
docker compose stop ingestion

# Uruchom seed syntetyczny (pokrywa 2010–2025, ~11 520 rekordów):
docker compose run --rm \
  -v $(pwd)/ingestion/seed_gdelt_fallback.py:/app/seed_gdelt_fallback.py \
  ingestion python seed_gdelt_fallback.py
```

Oczekiwany wynik:
```
Seeded country POL (720 records so far)
Seeded country DEU (1440 records so far)
...
Seed complete: 11520 records (16 years × 10 countries × 6 themes × 12 months)
```

> Seed zawiera realistyczne dane z historycznymi spike'ami (Fukushima 2011,
> COVID/BLM 2020, wybory USA 2020, protesty w Polsce 2020, wybory w Niemczech itp.).
> Jest bezpieczny do wielokrotnego uruchamiania (`ON CONFLICT DO UPDATE`).

### 4C – Po pobraniu danych: przelicz korelacje

```bash
docker compose restart processing
docker compose logs -f processing
# Oczekiwane: "Correlation computation complete: 60 results (years 2010–2025)"
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
http://localhost:8000/docs          # Swagger UI
http://localhost:8000/openapi.json  # OpenAPI 3.0 JSON
```

Endpointy:
| Metoda | URL | Opis |
|--------|-----|------|
| GET | `/health` | Status systemu |
| GET | `/api/v1/gdp/countries` | Lista krajów |
| GET | `/api/v1/gdp/{country_code}` | Dane PKB kraju (`?year_start=&year_end=`) |
| GET | `/api/v1/events/types` | Typy eventów |
| GET | `/api/v1/events/{country_code}` | Eventy GDELT kraju (`?year_start=&year_end=&event_type=`) |
| GET | `/api/v1/analysis/correlations` | Korelacje PKB–eventy (`?year_start=&year_end=&metric=gdp\|growth&country_code=&event_type=`) |
| GET | `/api/v1/analysis/correlations/lag` | Korelacje z przesunięciem −2…+2 lata |
| GET | `/api/v1/analysis/anomalies` | Miesiące z z-score > 2σ (`?year_start=&year_end=&threshold=`) |
| GET | `/api/v1/analysis/summary` | Statystyki bazy danych |

Przykłady:
```bash
curl "http://localhost/api/v1/gdp/POL?year_start=2018&year_end=2022"
curl "http://localhost/api/v1/events/POL?event_type=PROTEST"
curl "http://localhost/api/v1/analysis/correlations?country_code=POL&year_start=2015&year_end=2024&metric=growth"
curl "http://localhost/api/v1/analysis/correlations/lag?country_code=POL"
curl "http://localhost/api/v1/analysis/anomalies?country_code=JPN&event_type=DISASTER"
```

---

## KROK 9 – Zatrzymanie systemu

```bash
# Zatrzymaj i usuń kontenery (dane w DB zostają):
docker compose down

# Zatrzymaj i usuń wszystko łącznie z wolumenami (czysty reset):
docker compose down -v
```

---

## Informacje o API źródłowych

### World Bank Open Data API
- **Brak klucza API** – dostęp publiczny
- Endpoint PKB: `https://api.worldbank.org/v2/country/{kod}/indicator/NY.GDP.MKTP.CD?format=json`
- Dostępność danych: 2010–2024 (2025 i nowsze jeszcze niedostępne)
- Dokumentacja: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392

### GDELT v1 GKG (Global Knowledge Graph)
- **Brak klucza API** – pliki statyczne, dostęp publiczny
- Pliki dzienne: `http://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip`
- Dostępność danych: od 2013-04-01
- Format: TSV, pole `THEMES` zawiera kody tematyczne, `LOCATIONS` kody FIPS krajów
- Zwykle **nie jest blokowany** nawet gdy API v2 jest niedostępne

### GDELT 2.0 Document API
- **Brak klucza API** – dostęp publiczny, ale z ograniczeniami Cloudflare
- Endpoint timeline: `https://api.gdeltproject.org/api/v2/doc/doc?query=sourcecountry:PL+theme:PROTEST&mode=timelinevol&format=json`
- Dostępność danych: od 2017 (stabilna)
- Ograniczenie: 1 zapytanie / 8 s (wbudowane w kod); może blokować IP automatycznych skryptów
- Dokumentacja: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

---

## Rozwiązywanie problemów

**Problem: Dane GDELT są puste / korelacje nie wyliczone**
```bash
# Sprawdź logi ingestion:
docker compose logs ingestion | grep -E "(error|ERROR|giving up|429)"

# Sprawdź stan bazy:
curl http://localhost/api/v1/analysis/summary

# Jeśli gdelt_events = 0, uruchom seed syntetyczny (KROK 4B)
```

**Problem: GDELT v2 zwraca błędy 429 lub nie odpowiada**
```bash
# Zatrzymaj ingestion i użyj seeda (KROK 4B)
docker compose stop ingestion
# Seed pokrywa lata 2010–2025 syntetycznymi, ale realistycznymi danymi
```

**Problem: Backend nie startuje**
```bash
docker compose logs backend
# Najczęstsza przyczyna: baza danych jeszcze nie gotowa – odczekaj 15s i spróbuj ponownie
docker compose restart backend
```

**Problem: Port 80 zajęty**
```bash
# W docker-compose.yml zmień port frontendu:
# ports:
#   - "8080:80"
```

**Problem: Korelacje nadal 0 po zasileniu bazy**
```bash
docker compose restart processing
docker compose logs -f processing
# Powinno pojawić się: "Correlation computation complete: 60 results"
```
