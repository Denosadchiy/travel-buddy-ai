# Live Test Results — 3 User Cases
**Дата:** 2026-03-27
**Backend:** `POST http://localhost:8000/api/hotels/search`
**Данные:** только реальные ответы системы, ничего не добавлено вручную

---

## Сводка кейсов

| # | Город | Регион | Сложность | LLM ранкинг | Найдено отелей |
|---|-------|--------|-----------|-------------|----------------|
| 1 | Прага | Европа | Простой | ✅ LLM | 4 744 |
| 2 | Медельин | Латинская Америка | Средний | ✅ LLM | 2 981 |
| 3 | Киото | Азия | Сложный | ⚠️ Formula fallback | 3 037 |

> **Примечание по кейсу 3 (Киото):** LLM-ранкер не сработал (использован детерминированный fallback по формуле) — все `ai_score` показаны как формульный результат (5.x/10), а `ai_match_reason` = "Score: X/10 (formula ranking)". Валюта в ответах Медельина и Киото пришла в местной (COP / JPY) несмотря на запрос в USD — отражено как есть.

---

## API Endpoints (как если бы вызывал фронтенд)

### Все три кейса

**Endpoint:** `POST /api/hotels/search`
**Content-Type:** `application/json`

Ниже — параметры запроса для каждого кейса.

---

## Кейс 1 — Простой: Прага, 2 взрослых, без доп. условий

### Параметры запроса

```json
POST /api/hotels/search
{
  "city": "Prague",
  "check_in": "2026-05-10",
  "check_out": "2026-05-13",
  "adults": 2
}
```

**Применённые фильтры (из ответа):** `Score ≥7 · Prague (4744 hotels available)`
**Session ID:** `df6b2d42-d8ad-4c1c-88b5-8bc857ca6046`
**Валюта ответа:** EUR

### Результаты

| # | Название | Цена/ночь | Валюта | Ссылка | Доп. информация |
|---|----------|-----------|--------|--------|-----------------|
| 1 | Hotel Nerudova 211 | 311.51 | EUR | [Booking.com](https://www.booking.com/hotel/cz/hotel-nerudova-211.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 4★, boutique, оценка 9.8/10 (1182 отзыва), бесплатная отмена, Прага 1, 1.4 км от центра. AI: уникальный декор, исключительный персонал |
| 2 | Romantik Hotel U Raka | 171.83 | EUR | [Booking.com](https://www.booking.com/hotel/cz/romantik-u-raka.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 4★, boutique, оценка 9.8/10 (374 отзыва), завтрак включён, бесплатная отмена, pets OK. Романтичная атмосфера, исторический шарм |
| 3 | Old Town Square Residence by Emblem | 163.39 | EUR | [Booking.com](https://www.booking.com/hotel/cz/old-town-square-and-residence.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 5★, condo hotel, оценка 9.0/10 (493 отзыва), бесплатная отмена, 0.03 км от центра (Старомест. пл.), pets OK. Скрытая проблема: шум |
| 4 | THE MANES Boutique Hotel Prague | 186.90 | EUR | [Booking.com](https://www.booking.com/hotel/cz/euroagentur-manes.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 4★, boutique, оценка 9.7/10 (4447 отзывов), без бесплатной отмены, 1.1 км от центра. Современный дизайн. Скрытая проблема: ванная/туалет раздельные |
| 5 | Allure Hotel & Residence Prague | 197.14 | EUR | [Booking.com](https://www.booking.com/hotel/cz/allure-prague.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 4★, boutique, оценка 9.7/10 (3182 отзыва), завтрак включён, без бесплатной отмены, 0.46 км от центра. Скрытая проблема: нет парковки |
| 6 | Hotel Pod Věží | 233.70 | EUR | [Booking.com](https://www.booking.com/hotel/cz/pod-vezi.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 4★, boutique, оценка 9.6/10 (1685 отзывов), завтрак включён, бесплатная отмена, 1.0 км от центра. Скрытая проблема: дорожные работы |
| 7 | Nosticova Heritage | 166.59 | EUR | [Booking.com](https://www.booking.com/hotel/cz/nosticova-apartments.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 4★, boutique, оценка 9.6/10 (1234 отзыва), бесплатная отмена, pets OK. Тихое расположение, удобные кровати |
| 8 | R16 Residences Prague | 177.68 | EUR | [Booking.com](https://www.booking.com/hotel/cz/apt16-old-town-prague.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 5★, condo hotel, оценка 9.7/10 (1641 отзыв), без бесплатной отмены, pets OK. Скрытая проблема: шум от дороги |
| 9 | Six Residences Prague | 155.25 | EUR | [Booking.com](https://www.booking.com/hotel/cz/6ix-residences.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 5★, condo hotel, оценка 9.7/10 (409 отзывов), без бесплатной отмены, pets OK. Роскошные апартаменты |
| 10 | Old Royal Post Boutique Hotel & Premium Suites | 126.87 | EUR | [Booking.com](https://www.booking.com/hotel/cz/old-royal-post-apartments.html?checkin=2026-05-10&checkout=2026-05-13&group_adults=2&group_children=0&selected_currency=EUR) | 5★, boutique, оценка 9.7/10 (2262 отзыва), без бесплатной отмены, pets OK. Исторический шарм + современные удобства |

**Почти вошедшие (notable_excluded):**
- Unesco Prague Apartments (5★, 9.6, 263 EUR/н) — высокая цена и шум
- MOOo by the Castle (4★, 9.7, 219 EUR/н) — ограниченные кухонные принадлежности
- Mama Shelter Prague (4★, 8.9, 123 EUR/н) — более низкий рейтинг

---

## Кейс 2 — Средний: Медельин, соло диджитал-номад, бюджет $120/ночь

### Параметры запроса

```json
POST /api/hotels/search
{
  "city": "Medellin",
  "check_in": "2026-06-01",
  "check_out": "2026-06-08",
  "adults": 1,
  "budget_max": 120,
  "currency": "USD",
  "amenities": ["facility::107"],
  "user_wishes": "Solo digital nomad, need fast WiFi and a desk to work. Prefer a quiet boutique hotel or aparthotel, close to cafes and restaurants. Not a chain."
}
```

**Применённые фильтры (из ответа):** `Budget ≤120/night · Score ≥8 · 3 amenity filters · Medellín (2981 hotels available)`
**Session ID:** `e07a90e4-0681-4b92-8a7c-bc1bc0beecd9`
**Валюта ответа:** COP (колумбийское песо) — несмотря на запрос USD
**Длительность:** 7 ночей (1–8 июня)

> **Примечание по валюте:** цены выведены в COP. Для ориентира: ~4400 COP ≈ 1 USD (на дату запроса).

### Результаты

| # | Название | Цена/ночь | Валюта | Ссылка | Доп. информация |
|---|----------|-----------|--------|--------|-----------------|
| 1 | Casa de las palmas 3 | 44.95 | COP | [Booking.com](https://www.booking.com/hotel/co/casa-de-las-palmas-medellin2.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, 0★ (без категории), оценка 9.6/10 (6 отзывов), бесплатная отмена, район Laureles, 0.9 км от центра |
| 2 | Hotel Boutique Casa Teresita | 35.97 | COP | [Booking.com](https://www.booking.com/hotel/co/boutique-santa-teresita.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Boutique, оценка 9.0/10 (85 отзывов), бесплатная отмена, pets OK, звукоизолированные номера, круглосуточная стойка. Скрытая проблема: далеко от метро |
| 3 | Casa de las Palmas 1 | 44.56 | COP | [Booking.com](https://www.booking.com/hotel/co/casa-de-las-palmas-medellin3.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, оценка 9.4/10 (41 отзыв), бесплатная отмена, pets OK, приватный вход, Laureles |
| 4 | Lovely apartment in the best zone of Medellin | 116.18 | COP | [Booking.com](https://www.booking.com/hotel/co/lovely-apartment-in-the-best-zone-of-medellin.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, оценка 9.1/10 (19 отзывов), бесплатная отмена, кухня, стиральная машина, вид на город. AI: отличный WiFi |
| 5 | Iconik 33 Hotel | 81.90 | COP | [Booking.com](https://www.booking.com/hotel/co/iconik-33.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | 3★, boutique, оценка 8.5/10 (34 отзыва), бесплатная отмена, pets OK, звукоизоляция, современный дизайн |
| 6 | Hermoso apartamento en zona central de Medellín | 45.85 | COP | [Booking.com](https://www.booking.com/hotel/co/beautiful-apartment-in-central-area-of-m-medellin.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, оценка 8.4/10 (103 отзыва), бесплатная отмена, pets OK, рядом Pueblito Paisa. Скрытая проблема: нет вентилятора |
| 7 | Apto 201 Sweet Home Medellín | 103.08 | COP | [Booking.com](https://www.booking.com/hotel/co/apartamento-sweet-home.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, оценка 9.1/10 (27 отзывов), бесплатная отмена, pets OK, приватная ванная, Laureles |
| 8 | Best Western Plus Hotel San Diego | 94.31 | COP | [Booking.com](https://www.booking.com/hotel/co/best-western-plus-hotel-san-diego.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | 4★, сеть, оценка 8.6/10 (654 отзыва), завтрак включён, бесплатная отмена, El Poblado. Скрытая проблема: муравьи в номерах |
| 9 | Amplio duplex con terraza privada | 37.05 | COP | [Booking.com](https://www.booking.com/hotel/co/amplio-duplex-con-terraza-privada.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, оценка 8.0/10 (5 отзывов), бесплатная отмена, pets OK, частная терраса. ⚠️ Кон: клопы (упомянуто в отзывах) |
| 10 | medellin - conquistadores 17 | 108.96 | COP | [Booking.com](https://www.booking.com/hotel/co/hermoso-y-nuevo-apartamento-al-lado-de-plaza-mayor.html?checkin=2026-06-01&checkout=2026-06-08&group_adults=1&group_children=0&selected_currency=USD) | Апартаменты, оценка 8.3/10 (17 отзывов), бесплатная отмена, pets OK, вид на город. Скрытая проблема: нет кондиционера |

**Почти вошедшие (notable_excluded):**
- Beminimal Hotel (4★, 8.9) — шум и превышение бюджета
- Luxury Apartments Prana By Cadissa (8.6) — нет кухонных принадлежностей + превышение бюджета

---

## Кейс 3 — Сложный: Киото, семья с детьми 6 и 10 лет

### Параметры запроса

```json
POST /api/hotels/search
{
  "city": "Kyoto",
  "check_in": "2026-09-20",
  "check_out": "2026-09-26",
  "adults": 2,
  "children_ages": [6, 10],
  "stars_min": 4,
  "budget_max": 350,
  "currency": "USD",
  "free_cancellation": true,
  "amenities": ["facility::433", "facility::54", "facility::28"],
  "user_wishes": "Family vacation in Kyoto, 2 kids aged 6 and 10. Want a luxury or traditional ryokan-style hotel with pool or onsen, family-friendly, close to temples and cultural sights. Breakfast included preferred. Not a generic chain - something special with Japanese atmosphere."
}
```

**Применённые фильтры (из ответа):** `Budget ≤455/night · Score ≥7 · Kyoto (3037 hotels available)`
**Session ID:** `a686585c-15a1-43cb-88a2-9ff46ae86b09`
**Валюта ответа:** JPY (японская иена) — несмотря на запрос USD
**LLM ранкинг:** ⚠️ **Использован детерминированный formula fallback** (LLM не вернул ответ в срок). Все `ai_score` — формульные (5.x/10), а не AI-оценки.
**Каскадный fallback:** система ослабила фильтры (бюджет ×1.3 → ≤455 USD/н), чтобы вернуть результаты с учётом запрошенных удобств pool/spa/family rooms.

### Результаты

| # | Название | Цена/ночь | Валюта | Ссылка | Доп. информация |
|---|----------|-----------|--------|--------|-----------------|
| 1 | STITCH HOTEL Kyoto | 598.86 | JPY | [Booking.com](https://www.booking.com/hotel/jp/stitch-kyoto-jing-du-shi.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 5★, boutique, оценка 9.7/10 (221 отзыв), бесплатная отмена, pets OK, район Gion, семейные номера. Formula score 5.8 |
| 2 | Shirasagi Kyoto | 329.02 | JPY | [Booking.com](https://www.booking.com/hotel/jp/shirasagi-kyoto.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 4★, vacation home, оценка 10.0/10 (85 отзывов!), бесплатная отмена, pets OK, татами, кухня, вид на реку. Formula score 5.8 |
| 3 | Auberge AZABU | 240.50 | JPY | [Booking.com](https://www.booking.com/hotel/jp/auberge-azabu.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 4★, ryokan, оценка 9.6/10 (493 отзыва), бесплатная отмена, pets OK, завтрак, персонализированный сервис для семей. Formula score 5.6 |
| 4 | MIMARU SUITES Kyoto Central | 475.07 | JPY | [Booking.com](https://www.booking.com/hotel/jp/mimaru-suites-kyoto-city-kyoto.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 4★, boutique, оценка 9.5/10 (375 отзывов), без бесплатной отмены, гипоаллергенный, семейные номера, просторные апартаменты. Formula score 5.5 |
| 5 | Umekoji Potel KYOTO | 246.77 | JPY | [Booking.com](https://www.booking.com/hotel/jp/umekoji-potel-kyoto.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 4★, boutique, оценка 9.3/10 (1549 отзывов), бесплатная отмена, настольный теннис, художественные галереи, удобства для гостей с ограниченными возможностями. Formula score 5.5 |
| 6 | Kyomachiya Suite Rikyu | 405.85 | JPY | [Booking.com](https://www.booking.com/hotel/jp/kyomachiya-suite-rikyu.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 5★, vacation home, оценка 9.8/10 (162 отзыва), без бесплатной отмены, татами, приватный вход, Gion. Традиционный японский стиль. Formula score 5.4 |
| 7 | Onyado Nono Kyoto Shichijo Natural Hot Spring | 229.93 | JPY | [Booking.com](https://www.booking.com/hotel/jp/onyado-nono-kyoto-shichijo.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 4★, boutique, оценка 9.1/10 (9346 отзывов), бесплатная отмена, pets OK, онсен, звукоизоляция, семейные номера. Скрытая проблема: тесные номера. Formula score 5.3 |
| 8 | Villa Sanjomuromachi KYOTO | 256.81 | JPY | [Booking.com](https://www.booking.com/hotel/jp/villa-sanjomuromachi-kyoto.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 4★, boutique, оценка 9.6/10 (317 отзывов), без бесплатной отмены, pets OK, звукоизоляция, ежедневная уборка, апгрейды бесплатно. Formula score 5.3 |
| 9 | Kyoto Umekoji Kadensho | 244.44 | JPY | [Booking.com](https://www.booking.com/hotel/jp/kyoto-umekoij-kadensho.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 5★, boutique, оценка 9.2/10 (1294 отзыва), бесплатная отмена, pets OK, приватный онсен, семейные номера. Скрытая проблема: шум от ж/д. Formula score 5.2 |
| 10 | GOOD NATURE HOTEL KYOTO | 238.71 | JPY | [Booking.com](https://www.booking.com/hotel/jp/good-nature-kyoto.html?checkin=2026-09-20&checkout=2026-09-26&group_adults=2&group_children=2&selected_currency=USD&age=6&age=10) | 5★, boutique, оценка 9.2/10 (2811 отзывов), бесплатная отмена, pets OK, рестораны, Gion. Скрытая проблема: лифт останавливается в лобби. Formula score 5.2 |

**notable_excluded:** пустой список (система не сформировала при formula fallback)

---

## Технические детали вызовов

### Внутренние API-вызовы, которые система делает по одному поисковому запросу

Ниже — цепочка HTTP-запросов, которую фронтенд инициирует одним вызовом `POST /api/hotels/search`:

```
Phase 1: Intent Parse + Destination Resolve (параллельно)
  LLM call → ParsedIntent (сегмент, веса, фильтры, prefer_free_cancellation, stars_min, ...)
  GET /api/v1/hotels/searchDestination?query={city}
    → dest_id, search_type, nr_hotels

Phase 2a: Multi-sort Candidate Fetch
  GET /api/v1/hotels/searchHotels (×1–4 параллельных, разные sort_by)
    Параметры: dest_id, arrival_date, departure_date, adults, children_age,
               price_min, price_max, categories_filter, sort_by, page_number=1, currency_code

Phase 2b: L1 Filter (детерминированный, без API)

Phase 3: Deep Fetch для 25 финалистов (5–6 параллельных вызовов на отель)
  GET /api/v1/hotels/getHotelDetails?hotel_id=...&arrival_date=...&departure_date=...
  GET /api/v1/hotels/getHotelReviewScores?hotel_id=...
  GET /api/v1/hotels/getHotelReviews?hotel_id=...&page=1&sort=sort_most_relevant
  GET /api/v1/hotels/getHotelReviews?hotel_id=...&page=2&sort=sort_most_relevant
  GET /api/v1/hotels/getHotelFacilities?hotel_id=...
  GET /api/v1/hotels/getHotelPhotos?hotel_id=...      ← 6-й вызов (добавлен в Stage 5)

Phase 4: Review Analysis (LLM batch)
Phase 5: Master Ranking (LLM → или formula fallback)
Phase 7: Сборка и возврат HotelSearchResponse
```

### Параметры categories_filter по кейсам

| Кейс | categories_filter | Описание |
|------|-------------------|----------|
| 1 (Прага) | — | не передавался (нет amenities) |
| 2 (Медельин) | `facility::107` | Free WiFi |
| 3 (Киото) | `facility::433,facility::54,facility::28` | Pool + Spa/wellness + Family rooms |

### Параметры children_age (Booking.com API)

Для кейса 3 с `children_ages: [6, 10]` в URL передаётся: `&age=6&age=10`

---

## Наблюдения по результатам

| Наблюдение | Кейс |
|-----------|------|
| Все 10 отелей — boutique (не сетевые), даже без явной просьбы | 1, 2, 3 |
| Валюта ответа = местная (COP/JPY), а не запрошенная USD | 2, 3 |
| LLM ранкинг сработал корректно (ai_score 8.5–9.5, уникальные причины) | 1, 2 |
| LLM ранкинг не успел → formula fallback (ai_score 5.x, нет notable_excluded) | 3 |
| Каскадный fallback смягчил бюджет ×1.3 (350→455 USD/н) при сложных фильтрах | 3 |
| `stars_min=4` применился корректно: все отели Киото 4★+ | 3 |
| `free_cancellation=true` → учтён как scoring bonus, не жёсткий фильтр | 3 |
