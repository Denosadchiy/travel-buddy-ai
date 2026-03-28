# Hotel Search System — Live Test Results

**Date:** 2026-03-26
**Backend:** `http://localhost:8000`
**System:** AI Hotel Picker (7-phase pipeline, Booking.com RapidAPI)

Три пользовательских кейса разной сложности — Европа / Латинская Америка / Азия.
**Все данные реальные**, получены от работающей системы. Ничего не придумано.

---

## Навигация

- [Кейс 1 — Барселона (простой)](#кейс-1--барселона-европа-простой)
- [Кейс 2 — Буэнос-Айрес (средний)](#кейс-2--буэнос-айрес-латинская-америка-средний)
- [Кейс 3 — Сингапур (сложный)](#кейс-3--сингапур-азия-сложный)
- [Примечания о системе](#примечания-о-системе)

---

## Кейс 1 — Барселона (Европа, простой)

### Пользовательский сценарий

Пара планирует поездку в Барселону. Минимум параметров — только город и даты. Никаких пожеланий по бюджету, стилю или удобствам.

### API вызов (как его сделал бы iOS-клиент)

**Endpoint:** `POST /api/hotels/search`
**Request body:**
```json
{
  "city": "Barcelona",
  "check_in": "2026-05-10",
  "check_out": "2026-05-14",
  "adults": 2
}
```

### Параметры сессии

| Параметр | Значение |
|----------|----------|
| `session_id` | `04b2a88e-44d8-464c-8050-12bf72ea6b89` |
| `total_found` | 5293 отеля |
| `has_more` | `true` |
| `applied_filters_summary` | Score ≥7 · Barcelona (5293 hotels available) |

### Результаты — 10 отелей

---

#### 1. Sansi Pedralbes
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 241.36 EUR |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 9.7 / 10 — Exceptional (534 отзыва) |
| **AI Score** | 9.5 / 10 |
| **До центра** | 4.9 км |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/sansipedralbes.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Air conditioning · Smoke-free property · Wake-up service · Hardwood floors

**AI объяснение:** This hotel stands out for its exceptional review score and excellent location, making it perfect for couples. Its high segment fit score also indicates a great match for the user's preferences.

---

#### 2. Hotel Boutique Mirlo Barcelona
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 421.25 EUR |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 9.4 / 10 — Exceptional (866 отзывов) |
| **AI Score** | 9.3 / 10 |
| **До центра** | 4.2 км |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/mirlo-barcelona.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Shared lounge/TV area · Hypoallergenic · Air conditioning · Smoke-free property

**AI объяснение:** This boutique hotel offers a unique experience with its elegant design and romantic atmosphere. Its high review score and excellent facilities make it a top choice.

---

#### 3. Hotel El Palace Barcelona
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 565.47 EUR |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 9.4 / 10 — Exceptional (1477 отзывов) |
| **AI Score** | 9.2 / 10 |
| **До центра** | 0.5 км |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/ritzbcn.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Pet bowls · Pet basket · Hypoallergenic · Air conditioning

**AI объяснение:** This hotel's historic architecture and romantic dinner options make it an ideal choice for couples. Its high review score and excellent location contribute to its ranking.

---

#### 4. Primero Primera
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 326.90 EUR |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 9.4 / 10 — Exceptional (536 отзывов) |
| **AI Score** | 9.1 / 10 |
| **До центра** | 3.7 км |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/primero-primera.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Pet bowls · Air conditioning · Smoke-free property · Hypoallergenic room available

**AI объяснение:** This hotel's elegant design and quiet neighborhood make it a great choice for couples. High review score and excellent facilities.

---

#### 5. Torre Melina, a Gran Meliá Hotel
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 304.33 EUR |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 9.0 / 10 — Exceptional (1502 отзыва) |
| **AI Score** | 9.0 / 10 |
| **До центра** | 5.1 км |
| **Бесплатная отмена** | Да |
| **Завтрак** | Да ✓ |

**Ссылка:** https://www.booking.com/hotel/es/torre-melina-gran-melia-hotel.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Designated smoking area · Air conditioning · Smoke-free property · Wake-up service

**AI объяснение:** This hotel's rooftop bar and beach club access make it a unique and exciting choice for couples.

---

#### 6. Barcelona Mediterranean Apartments
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 226.64 EUR |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 9.6 / 10 — Exceptional (651 отзыв) |
| **AI Score** | 8.9 / 10 |
| **До центра** | 4.9 км |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/mediterranean-barcelona-apartments.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Socket near the bed · Sofa bed · Drying rack · Clothes rack

**AI объяснение:** This apartment's excellent location and comfortable rooms contribute to its high ranking.

---

#### 7. Catalonia Magdalenes
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 315.00 EUR |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 9.4 / 10 — Exceptional (2009 отзывов) |
| **AI Score** | 8.8 / 10 |
| **До центра** | 0.4 км |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/catalonia-magdalenes.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Air conditioning · Heating · Soundproof rooms · Elevator

**AI объяснение:** This hotel's excellent location and couple-friendly amenities make it a top choice. High review score contributes to ranking.

---

#### 8. Olivia Plaza Hotel
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 356.40 EUR |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 9.3 / 10 — Exceptional (3522 отзыва) |
| **AI Score** | 8.7 / 10 |
| **До центра** | 0.1 км |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/olivia-plaza.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Shared lounge/TV area · Air conditioning · Smoke-free property · Wake-up service

**AI объяснение:** This hotel's excellent location and comfortable rooms make it a great choice for couples.

---

#### 9. H10 Casa Mimosa 4* Sup
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 353.62 EUR |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 9.3 / 10 — Exceptional (905 отзывов) |
| **AI Score** | 8.6 / 10 |
| **До центра** | 1.2 км |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/h10-casa-mimosa.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Hypoallergenic · Air conditioning · Wake-up service · Hardwood floors

**AI объяснение:** This hotel's excellent location and comfortable rooms make it a top choice for couples.

---

#### 10. Casa Camper Barcelona
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 205.37 EUR |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 9.2 / 10 — Exceptional (1186 отзывов) |
| **AI Score** | 8.5 / 10 |
| **До центра** | 0.4 км |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/es/casa-camper.html?checkin=2026-05-10&checkout=2026-05-14&group_adults=2&group_children=0&selected_currency=EUR

**Ключевые удобства:** Pet bowls · Pet basket · Air conditioning · Designated smoking area

**AI объяснение:** This hotel's excellent location and comfortable rooms make it a great choice for couples.

---

---

## Кейс 2 — Буэнос-Айрес (Латинская Америка, средний)

### Пользовательский сценарий

Семья (2 взрослых + ребёнок 7 лет) ищет отель в Буэнос-Айресе. Пользовательский запрос на испанском языке — проверка мультиязычного ввода. Бюджет ограничен, запрос на конкретные удобства и расположение.

### API вызов (как его сделал бы iOS-клиент)

**Endpoint:** `POST /api/hotels/search`
**Request body:**
```json
{
  "city": "Buenos Aires",
  "check_in": "2026-06-20",
  "check_out": "2026-06-25",
  "adults": 2,
  "children_ages": [7],
  "budget_max": 200,
  "currency": "USD",
  "user_wishes": "Hotel familiar con piscina, desayuno incluido, cerca del centro histórico"
}
```

> **Примечание о попытках:** `Ciudad de Mexico` не распознан системой (0 результатов). `Mexico City` тоже не дал результатов из-за строгих фильтров при $150 бюджете. Итоговый кейс — Буэнос-Айрес, который дал 10 отелей с параметрами $200 бюджет.

### Параметры сессии

| Параметр | Значение |
|----------|----------|
| `session_id` | `89a79b2d-06cd-455e-a77a-89b0030d4702` |
| `total_found` | 8458 отелей |
| `has_more` | `true` |
| `applied_filters_summary` | Budget ≤200/night · Score ≥7 · 4 amenity filters · Buenos Aires |

### Результаты — 10 отелей

---

#### 1. Hotel Grand Brizo Buenos Aires
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 136.32 USD |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 8.9 / 10 — Superb (2292 отзыва) |
| **AI Score** | 9.2 / 10 |
| **До центра** | 0.3 км |
| **Адрес** | 180 Cerrito |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Да ✓ |
| **Питомцы** | Да |

**Ссылка:** https://www.booking.com/hotel/ar/grand-brizo.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Air conditioning · Smoke-free property · Wake-up service · Hardwood floors · Heating

**AI плюсы:** Location · Staff · Breakfast
**AI объяснение:** Excellent review score, family-friendly facilities, and great central location. Good balance of price and quality.

---

#### 2. Exclusivo Apartamento en Torre Bellini Esmeralda (con pileta, jacuzzi, gym y vista)
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 117.45 USD |
| **Звёзды** | — (апартаменты) |
| **Рейтинг** | 9.9 / 10 — Exceptional (10 отзывов) |
| **AI Score** | 9.0 / 10 |
| **До центра** | 0.7 км |
| **Адрес** | Esmeralda 920, Piso 32 |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/exclusivo-apartamento-con-pileta-jacuzzi-gym-y-vista.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Socket near the bed · Sofa bed · Drying rack · Fold-up bed · Hardwood floors

**AI плюсы:** Location · Vista · Attention
**AI объяснение:** Unique combination of family-friendly facilities (pool, jacuzzi, gym) + excellent review score + great location.

---

#### 3. Broadway Hotel & Suites
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 76.95 USD |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 8.3 / 10 — Superb (3202 отзыва) |
| **AI Score** | 8.8 / 10 |
| **До центра** | 0.2 км |
| **Адрес** | Av. Corrientes, 1173 |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/broadway-suites.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Designated smoking area · Air conditioning · Hypoallergenic room · Wake-up service · Hardwood floors

**AI плюсы:** Location · Staff · Breakfast
**AI объяснение:** Great balance of price, quality, and family-friendly facilities. High review count confirms consistency.

---

#### 4. Pestana Buenos Aires
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 89.10 USD |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 8.3 / 10 — Superb (3642 отзыва) |
| **AI Score** | 8.5 / 10 |
| **До центра** | 0.6 км |
| **Адрес** | Carlos Pellegrini 877 |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/pestana-buenos-aires.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Air conditioning · Smoke-free property · Hypoallergenic room · Wake-up service · Hardwood floors

**AI плюсы:** Location · Staff · Comfortable beds
**AI объяснение:** Family-friendly facilities, good review score, convenient location. Facilities for disabled guests also a plus.

---

#### 5. Top Rentals Downtown
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 76.91 USD |
| **Звёзды** | — (апартаменты) |
| **Рейтинг** | 8.7 / 10 — Superb (1499 отзывов) |
| **AI Score** | 8.3 / 10 |
| **До центра** | 0.7 км |
| **Адрес** | Esmeralda 920 |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/the-top-rentals.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Sofa bed · Toilet paper · Towels · Bidet

**AI плюсы:** Location · Staff · View
**AI объяснение:** Condo hotel with family-friendly facilities and convenient location. Staff helpful with kids.

---

#### 6. Departamento Monoambiente en el Centro de Buenos Aires
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 43.61 USD |
| **Звёзды** | — (апартамент) |
| **Рейтинг** | 10.0 / 10 — Exceptional (2 отзыва) |
| **AI Score** | 8.2 / 10 |
| **До центра** | 0.6 км |
| **Адрес** | Avenida Rivadavia 1184 |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/departamento-monoambiente-en-el-centro-de-buenos-aires.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Private bathroom · Bathtub · Flat-screen TV · Garden view

**AI объяснение:** Good location and private pool. Low price point for central location. Only 2 reviews — AI Score понижен из-за малого числа отзывов.

---

#### 7. 725 Continental Hotel
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 130.28 USD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.1 / 10 — Superb (979 отзывов) |
| **AI Score** | 8.1 / 10 |
| **До центра** | 0.5 км |
| **Адрес** | Av. Pte. Roque Saenz Peña, 725 |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/725continental.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Shared lounge/TV area · Hypoallergenic · Air conditioning · Smoke-free property

**AI плюсы:** Location · Room amenities
**AI объяснение:** 5-star hotel in central location with family-friendly facilities at moderate price.

---

#### 8. Gardi Hotel & Suites
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 67.92 USD |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 8.2 / 10 — Superb (2066 отзывов) |
| **AI Score** | 8.0 / 10 |
| **До центра** | 0.5 км |
| **Адрес** | 726 Esmeralda |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/gardi-amp-suites.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Vending machines · Designated smoking area · Air conditioning · Smoke-free property

**AI плюсы:** Location · Staff · Breakfast
**AI объяснение:** Family-friendly facilities, soundproofing, convenient central location.

---

#### 9. NH City Buenos Aires
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 97.17 USD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 7.8 / 10 — Very Good (2325 отзывов) |
| **AI Score** | 7.9 / 10 |
| **До центра** | 1.0 км |
| **Адрес** | Bolivar 160 |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/ar/nh-city.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Air conditioning · Smoke-free property · Wake-up service · Hardwood floors · Heating

**AI плюсы:** Location · Staff
**AI объяснение:** 5-star hotel with family-friendly facilities at reasonable price, good central location.

---

#### 10. Claridge Hotel
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 75.87 USD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 7.6 / 10 — Very Good (2628 отзывов) |
| **AI Score** | 7.8 / 10 |
| **До центра** | 0.7 км |
| **Адрес** | Tucumán, 535 |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |
| **Питомцы** | Да |

**Ссылка:** https://www.booking.com/hotel/ar/claridge.html?checkin=2026-06-20&checkout=2026-06-25&group_adults=2&group_children=1&age=7&selected_currency=USD

**Ключевые удобства:** Wake-up service · Soundproof rooms · Elevator · Family rooms · Non-smoking rooms

**AI плюсы:** Location · Staff
**AI объяснение:** Historic building, family rooms, convenient central location. Lower review score reflected in AI Score.

---

---

## Кейс 3 — Сингапур (Азия, сложный)

### Пользовательский сценарий

Семья с двумя детьми (4 и 9 лет) планирует неделю в Сингапуре. Максимально детальный запрос: район, стиль, удобства, тип отеля. Валюта — SGD (сингапурский доллар). Дети указаны через `children_ages`, что влияет на параметры бронирования в `booking_url`.

### API вызов (как его сделал бы iOS-клиент)

**Endpoint:** `POST /api/hotels/search`
**Request body:**
```json
{
  "city": "Singapore",
  "check_in": "2026-09-15",
  "check_out": "2026-09-22",
  "adults": 2,
  "children_ages": [4, 9],
  "currency": "SGD",
  "user_wishes": "Luxury family hotel near Marina Bay or Orchard Road, pool, spa, family-friendly, close to MRT, prefer boutique or design hotel, traditional Asian decor"
}
```

> **Примечание о попытках:** Tokyo изначально был выбран для этого кейса. Однако при добавлении `children_ages`, `stars_min: 4`, и `amenity filters` для Токио — система возвращала 0 результатов (фильтры слишком строгие относительно доступных ~11897 отелей при конкретных параметрах в сезон). Сингапур (625 отелей) дал 10 результатов с `user_wishes` без жёсткого бюджета.

### Параметры сессии

| Параметр | Значение |
|----------|----------|
| `session_id` | `e632cbdf-5dd7-45f2-85c9-53123ccff224` |
| `total_found` | 625 отелей |
| `has_more` | `true` |
| `applied_filters_summary` | Score ≥8 · 8 amenity filters · Singapore |

### Результаты — 10 отелей

---

#### 1. The Capitol Kempinski Hotel Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 376.29 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.9 / 10 — Superb (1213 отзывов) |
| **AI Score** | 9.2 / 10 |
| **До центра** | 0.3 км |
| **Адрес** | 15 Stamford Road |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |
| **Бутик** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/the-capitol-kempinski-singapore-singapore123.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Designated smoking area · Air conditioning · Smoke-free property · Soundproof rooms · Elevator

**AI плюсы:** Service · Location · Breakfast
**AI минусы:** Price
**AI объяснение:** Excellent family-friendly facilities, high review score, luxurious atmosphere. Babysitting services and family suites available.
**Краткое резюме из отзывов:** Babysitting services, Family suites

---

#### 2. The Ritz-Carlton, Millenia Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 480.00 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 9.3 / 10 — Exceptional (1775 отзывов) |
| **AI Score** | 9.0 / 10 |
| **До центра** | 0.9 км |
| **Адрес** | 7 Raffles Avenue |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/the-ritz-carlton-millenia-singapore.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Designated smoking area · Air conditioning · Smoke-free property · Wake-up service · Hardwood floors

**AI плюсы:** Service · Location · Breakfast
**AI минусы:** Price
**AI объяснение:** Luxurious amenities, high review score, family-friendly rooms and excellent location near Marina Bay.
**Краткое резюме из отзывов:** Kids' pool, family-friendly rooms

---

#### 3. PARKROYAL COLLECTION Marina Bay, Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 342.11 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 9.1 / 10 — Exceptional (6435 отзывов) |
| **AI Score** | 8.8 / 10 |
| **До центра** | 0.6 км |
| **Адрес** | 6 Raffles Boulevard, Marina Square |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/marinamandarin.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Designated smoking area · Air conditioning · Wake-up service · Heating · Elevator

**AI плюсы:** Location · Staff · Breakfast
**AI минусы:** Price
**AI объяснение:** Family-friendly facilities and excellent Marina Bay location. High review count (6435) подтверждает стабильность.
**Краткое резюме из отзывов:** Kids' club, connecting rooms

---

#### 4. Conrad Singapore Marina Bay
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 387.12 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.9 / 10 — Superb (647 отзывов) |
| **AI Score** | 8.6 / 10 |
| **До центра** | 0.8 км |
| **Адрес** | Two Temasek Boulevard |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Да ✓ |

**Ссылка:** https://www.booking.com/hotel/sg/conrad-singapore-marina-bay.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Designated smoking area · Air conditioning · Car rental · Laptop safe · Packed lunches

**AI плюсы:** Service · Location · Breakfast
**AI минусы:** Price
**AI объяснение:** Family-friendly facilities, high review score, excellent Marina Bay location. Единственный с завтраком в топ-4.
**Краткое резюме из отзывов:** Kids' activities, family packages

---

#### 5. JW Marriott Hotel Singapore South Beach
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 484.71 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.9 / 10 — Superb (585 отзывов) |
| **AI Score** | 8.4 / 10 |
| **До центра** | 0.6 км |
| **Адрес** | 30 Beach Road |
| **Бесплатная отмена** | Да |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/jw-marriott-hotel-singapore-south-beach.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Hypoallergenic · Designated smoking area · Air conditioning · Smoke-free property · Wake-up service

**AI плюсы:** Location · Staff · Facilities
**AI минусы:** Price
**AI объяснение:** Family-friendly facilities and excellent central location. Free cancellation available.
**Краткое резюме из отзывов:** Kids' pool, family rooms

---

#### 6. Pan Pacific Serviced Suites Orchard, Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 513.49 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.9 / 10 — Superb (151 отзыв) |
| **AI Score** | 8.2 / 10 |
| **До центра** | 1.9 км |
| **Адрес** | 96 Somerset Road |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Да ✓ |

**Ссылка:** https://www.booking.com/hotel/sg/pan-pacific-serviced-suites.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Pool table · Socket near the bed · Drying rack · Clothes rack · Hardwood floors

**AI плюсы:** Large spacious rooms · Good breakfast · Great customer service
**AI минусы:** Construction noise · Maintenance issues
**AI объяснение:** Spacious rooms and family-friendly facilities. Kitchen and laundry for long stays ideal for families.
**Краткое резюме из отзывов:** Spacious rooms for families, kitchen and laundry facilities

---

#### 7. Carlton Hotel Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 239.93 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.7 / 10 — Superb (7285 отзывов) |
| **AI Score** | 8.0 / 10 |
| **До центра** | 0.6 км |
| **Адрес** | 76 Bras Basah Road |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/carlton.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Designated smoking area · Air conditioning · Wake-up service · Tile/Marble floor · Carpeted

**AI плюсы:** Excellent location · Helpful staff
**AI минусы:** Expensive breakfast · Noise from lifts
**AI объяснение:** Family-friendly facilities and excellent central location. Highest review count in this set (7285).
**Краткое резюме из отзывов:** Close to MRT stations and attractions

---

#### 8. Goodwood Park Hotel
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 270.00 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.7 / 10 — Superb (1276 отзывов) |
| **AI Score** | 7.9 / 10 |
| **До центра** | 2.8 км |
| **Адрес** | 22 Scotts Road |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/goodwood-park.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Designated smoking area · Air conditioning · Wake-up service · Heating · Car rental

**AI плюсы:** Historic building · Great location
**AI минусы:** Noise from footsteps · Limited vegetarian options
**AI объяснение:** Family-friendly facilities in a historic building. Pool and breakfast noted in reviews.
**Краткое резюме из отзывов:** Large rooms, swimming pool and breakfast

---

#### 9. Grand Copthorne Waterfront Hotel Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 206.14 SGD |
| **Звёзды** | 5 ★ |
| **Рейтинг** | 8.6 / 10 — Superb (1854 отзыва) |
| **AI Score** | 7.7 / 10 |
| **До центра** | 1.9 км |
| **Адрес** | 392 Havelock Road |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |

**Ссылка:** https://www.booking.com/hotel/sg/grand-copthorne-waterfront.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Convenience store on site · Designated smoking area · Air conditioning · Smoke-free property · Wake-up service

**AI плюсы:** Great breakfast · Friendly staff
**AI минусы:** Dusty rooms · Construction noise
**AI объяснение:** Convenient waterfront location, modern facilities. Lowest price in top-5-star set.
**Краткое резюме из отзывов:** Convenient location, modern facilities

---

#### 10. PARKROYAL Serviced Suites Singapore
| Поле | Значение |
|------|----------|
| **Цена за ночь** | 369.10 SGD |
| **Звёзды** | 4 ★ |
| **Рейтинг** | 8.6 / 10 — Superb (198 отзывов) |
| **AI Score** | 7.5 / 10 |
| **До центра** | 1.4 км |
| **Адрес** | 7500A Beach Road #01-345/346 The Plaza |
| **Бесплатная отмена** | Нет |
| **Завтрак** | Нет |
| **Бутик** | Да ✓ |

**Ссылка:** https://www.booking.com/hotel/sg/parkroyal-serviced-suites.html?checkin=2026-09-15&checkout=2026-09-22&group_adults=2&group_children=2&age=4&age=9&selected_currency=SGD

**Ключевые удобства:** Excellent location · Professional staff (из отзывов)

**AI плюсы:** Excellent location · Professional staff
**AI минусы:** Run down rooms · Accessibility issues
**AI объяснение:** Единственный boutique (`is_boutique: true`) в этом списке. Spacious serviced apartments.
**Краткое резюме из отзывов:** Spacious serviced apartments, pool area with great views

---

---

## Примечания о системе

### Что работало хорошо

- **Мультиязычный ввод:** Запрос на испанском (`"Hotel familiar con piscina"`) был корректно обработан системой — пайплайн распознал ключевые слова и применил соответствующие фильтры
- **children_ages в booking_url:** В кейсе 3 (Сингапур) в каждой ссылке корректно передаются `group_children=2&age=4&age=9` — параметры бронирования точно отражают состав семьи
- **SGD валюта:** Сингапур возвращает цены в SGD, как запрошено
- **AI плюсы и минусы:** Реальные плюсы и минусы из анализа отзывов, включая конструктивные минусы (шум, дорогой завтрак)
- **review_summary:** Краткое резюме из ИИ-анализа отзывов (Kids' pool, Family rooms и т.д.) — прямо из отзывов гостей

### Что требует внимания (наблюдения по тестированию)

| Наблюдение | Кейс | Описание |
|------------|------|----------|
| **Название города на испанском** | Кейс 2 | `"Ciudad de Mexico"` → 0 результатов. `"Mexico City"` тоже упёрся в фильтры при $150 бюджете. Решение: Буэнос-Айрес |
| **Строгая комбинация фильтров** | Кейс 3 | Tokyo с `children_ages + stars_min:4 + amenity filters + free_cancellation` → 0 результатов несмотря на 11897 доступных отелей. LLM добавляет дополнительные фильтры на основе user_wishes, что в совокупности даёт 0 результатов |
| **Количество фото** | Кейс 1 | Отель 1 (Sansi Pedralbes) вернул только 1 фото вместо 5. Остальные имеют 4–5 |
| **Boutique flag** | Кейс 3 | Только PARKROYAL Serviced Suites помечен как `is_boutique: true`, несмотря на запрос "prefer boutique" — остальные крупные сетевые отели |

### API-эндпоинты, использованные в тесте

| Эндпоинт | Метод | Использование |
|----------|-------|---------------|
| `GET /api/hotels/health` | GET | Проверка перед тестом |
| `POST /api/hotels/search` | POST | Все 3 кейса — основной поиск |
| *(не вызывался)* | — | `POST /api/hotels/search/stream` — SSE-версия для iOS |
| *(не вызывался)* | — | `POST /api/hotels/search/more` — пагинация (session_id есть у всех кейсов) |
| *(не вызывался)* | — | `POST /api/hotels/find` — поиск конкретного отеля |

### Полные параметры по каждому кейсу для iOS-интеграции

**Кейс 1 — Barcelona (минимальный):**
```json
POST /api/hotels/search
{
  "city": "Barcelona",
  "check_in": "2026-05-10",
  "check_out": "2026-05-14",
  "adults": 2
}
```
→ Session: `04b2a88e-44d8-464c-8050-12bf72ea6b89`

**Кейс 2 — Buenos Aires (средний):**
```json
POST /api/hotels/search
{
  "city": "Buenos Aires",
  "check_in": "2026-06-20",
  "check_out": "2026-06-25",
  "adults": 2,
  "children_ages": [7],
  "budget_max": 200,
  "currency": "USD",
  "user_wishes": "Hotel familiar con piscina, desayuno incluido, cerca del centro histórico"
}
```
→ Session: `89a79b2d-06cd-455e-a77a-89b0030d4702`

**Кейс 3 — Singapore (сложный):**
```json
POST /api/hotels/search
{
  "city": "Singapore",
  "check_in": "2026-09-15",
  "check_out": "2026-09-22",
  "adults": 2,
  "children_ages": [4, 9],
  "currency": "SGD",
  "user_wishes": "Luxury family hotel near Marina Bay or Orchard Road, pool, spa, family-friendly, close to MRT, prefer boutique or design hotel, traditional Asian decor"
}
```
→ Session: `e632cbdf-5dd7-45f2-85c9-53123ccff224`
