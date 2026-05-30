# GDP Events Analysis

Analiza zależności między zmianami PKB a częstotliwością i typami zdarzeń społecznych w 10 krajach (2010–obecnie).

## Źródła danych

| Źródło | Dane | API |
|--------|------|-----|
| [World Bank Open Data](https://data.worldbank.org/) | Roczny PKB (USD) i stopa wzrostu PKB | `NY.GDP.MKTP.CD`, `NY.GDP.MKTP.KD.ZG` |
| [GDELT Project](https://www.gdeltproject.org/) | Miesięczna liczba artykułów per temat | Doc API v2 `timelinevol` |

**Kraje:** Polska, Niemcy, USA, Francja, Brazylia, Indie, Chiny, Japonia, Wielka Brytania, Włochy

**Typy zdarzeń:** Protesty, Konflikty zbrojne, Wybory, Gospodarka, Klęski żywiołowe, Przestępczość

## Architektura

```
┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│  ingestion  │   │  processing  │   │   backend   │
│  (Python)   │   │  (Python)    │   │  (FastAPI)  │
└──────┬──────┘   └──────┬───────┘   └──────┬──────┘
       │                 │                  │
       └─────────────────┴──────────────────┤
                                    ┌───────▼──────┐
                                    │  PostgreSQL  │
                                    └──────────────┘
                                           ▲
                                  ┌────────┴────────┐
                                  │ Nginx + HTML/JS │
                                  │   (port 80)     │
                                  └─────────────────┘
```

- **ingestion** — pobiera PKB z World Bank i dane zdarzeń z GDELT; uruchamia się przy starcie, następnie co 24 h
- **processing** — oblicza korelacje Pearsona i zapisuje wyniki; uruchamia się przy starcie, następnie co 1 h
- **backend** — REST API serwujące dane do frontendu; obsługuje również obliczanie korelacji na żądanie dla dowolnego zakresu lat
- **frontend** — aplikacja jednostronicowa (Chart.js) za reverse proxy Nginx

## Szybki start

```bash
git clone <repo-url>
cd gdp-events-analysis
docker compose up -d
```

Otwórz `http://localhost` w przeglądarce.

> **Uwaga:** Inicjalne pobieranie danych uruchamia się automatycznie przy pierwszym starcie. Dane PKB (World Bank) ładują się w ~30 s. Ingestion GDELT zajmuje ~10 min ze względu na limity API (8 s przerwy między każdym z 60 requestów).

## Schemat bazy danych

```
countries        — 10 rekordów krajów (kody ISO 3166-1 alpha-3)
gdp_data         — roczny PKB i stopa wzrostu per kraj
event_types      — definicje 6 typów zdarzeń
gdelt_events     — miesięczna liczba artykułów per kraj/temat/rok
analysis_results — wstępnie obliczone korelacje Pearsona (procesor w tle)
```

Wszystkie ścieżki zapisu używają `ON CONFLICT DO UPDATE` — wielokrotne uruchomienie nie tworzy duplikatów.

## Endpointy API

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| GET | `/api/v1/gdp/countries` | Lista krajów |
| GET | `/api/v1/gdp/{code}` | Dane PKB dla kraju (`?year_start=&year_end=`) |
| GET | `/api/v1/events/{code}` | Liczba artykułów (`?year_start=&year_end=&event_type=`) |
| GET | `/api/v1/events/types` | Lista typów zdarzeń |
| GET | `/api/v1/analysis/correlations` | Korelacje Pearsona (`?year_start=&year_end=&metric=gdp\|growth&country_code=&event_type=`) |
| GET | `/api/v1/analysis/correlations/lag` | Korelacje z przesunięciem czasowym −2…+2 lata |
| GET | `/api/v1/analysis/anomalies` | Miesiące z z-score > 2σ |
| GET | `/api/v1/analysis/summary` | Liczba rekordów per tabela |

### Szczegóły endpointu korelacji

Gdy podano `year_start`/`year_end`, korelacja obliczana jest **na żądanie** przy użyciu wbudowanej funkcji agregującej `corr()` PostgreSQL bezpośrednio z surowych danych — bez konieczności czekania na procesor w tle.

`metric=gdp` — koreluje bezwzględną wartość PKB z wolumenem zdarzeń.  
`metric=growth` — koreluje roczną stopę wzrostu PKB (%) z wolumenem zdarzeń — bardziej miarodajne ekonomicznie, gdyż ujmuje recesje niezależnie od zamożności kraju.

## Analizy

| Analiza | Opis |
|---------|------|
| Korelacja Pearsona | PKB (lub wzrost PKB) vs roczny wolumen zdarzeń per kraj/temat |
| Markery recesji | Wykres słupkowy stopy wzrostu PKB — czerwone słupki oznaczają lata recesji |
| Heatmapa korelacji | Kolorowa siatka 10×6 (kraje × tematy) dla szybkiej identyfikacji wzorców |
| Analiza opóźnień | Korelacja dla przesunięć −2…+2 lata — sprawdza czy zdarzenia poprzedzają czy następują po zmianach PKB |
| Detekcja anomalii | Miesięczny z-score > 2σ względem historycznej średniej — wykrywa statystycznie wyjątkowe miesiące |

## Uwagi dotyczące ingestii GDELT

GDELT wymaga **60 requestów** (10 krajów × 6 tematów), jeden na parę `(kraj, temat)` obejmujący pełny zakres lat. Jest to minimum dla zachowania granularności na poziomie kraju i tematu — Doc API nie posiada trybu zwracającego podział per kraj w jednym requeście.

Requesty używają biblioteki `curl_cffi` z impersonacją fingerprintu TLS Chrome (`impersonate="chrome124"`) w celu ominięcia filtrowania Cloudflare. Przerwa 8 sekund między requestami respektuje limity GDELT.

## Konfiguracja

Zmienne środowiskowe (ustawiane w `docker-compose.yml`):

| Zmienna | Domyślna | Opis |
|---------|----------|------|
| `DATABASE_URL` | `postgresql://app:app@db:5432/gdp_events` | Connection string PostgreSQL |
| `INGEST_YEAR_START` | `2010` | Pierwszy rok do pobrania |
| `INGEST_YEAR_END` | `2025` | Ostatni rok do pobrania |
| `INGEST_INTERVAL_HOURS` | `24` | Interwał ponownego pobierania |
| `PROCESS_INTERVAL_HOURS` | `1` | Interwał ponownego przetwarzania |

## Stack technologiczny

- **Python 3.11** — FastAPI, SQLAlchemy, Pydantic v2, curl_cffi, psycopg2
- **PostgreSQL 15** — agregat `corr()` do obliczania Pearsona na żądanie
- **Chart.js 4** — wykres liniowy PKB, skumulowany wykres słupkowy zdarzeń, wykres opóźnień, heatmapa korelacji
- **Nginx** — reverse proxy (`/api/` → `backend:8000`)
- **Docker Compose** — orkiestracja pięciu serwisów
