/**
 * k6 load test — Hotel Search API
 *
 * Usage:
 *   k6 run tests/load/hotel_search.js
 *   k6 run --env BASE_URL=https://your-api.example.com tests/load/hotel_search.js
 *
 * Scenarios:
 *   steady_10   — 10 concurrent VUs for 5 minutes  (baseline)
 *   ramp_to_100 — ramp 1 → 100 VUs over 10 minutes (stress)
 *
 * Thresholds:
 *   p(95) < 3000 ms, error rate < 1%
 */
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend, Rate, Counter } from 'k6/metrics'

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const searchDuration = new Trend('hotel_search_duration', true)
const streamFirstByte = new Trend('hotel_stream_first_byte', true)
const errorRate = new Rate('hotel_error_rate')
const timeouts = new Counter('hotel_timeouts')

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000'

export const options = {
  scenarios: {
    steady_10: {
      executor: 'constant-vus',
      vus: 10,
      duration: '5m',
      tags: { scenario: 'steady_10' },
    },
    ramp_to_100: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '2m', target: 10 },
        { duration: '4m', target: 50 },
        { duration: '3m', target: 100 },
        { duration: '1m', target: 0 },
      ],
      startTime: '5m30s', // runs after steady_10 finishes
      tags: { scenario: 'ramp_to_100' },
    },
  },
  thresholds: {
    // Global p95 < 3 s
    http_req_duration: ['p(95)<3000'],
    // Scenario-specific
    'http_req_duration{scenario:steady_10}': ['p(95)<3000'],
    'http_req_duration{scenario:ramp_to_100}': ['p(95)<5000'],
    // Error rate < 1%
    hotel_error_rate: ['rate<0.01'],
    // Custom search duration
    hotel_search_duration: ['p(95)<3000'],
  },
}

// ---------------------------------------------------------------------------
// Realistic payloads — rotate to simulate variety
// ---------------------------------------------------------------------------
const PAYLOADS = [
  {
    city: 'Barcelona',
    arrival_date: '2026-08-01',
    departure_date: '2026-08-05',
    adults: 2,
    children: 0,
    user_wishes: 'quiet hotel near beach, free breakfast',
    price_min: 80,
    price_max: 250,
    stars_min: 3,
    currency: 'EUR',
  },
  {
    city: 'Paris',
    arrival_date: '2026-09-10',
    departure_date: '2026-09-14',
    adults: 1,
    children: 0,
    user_wishes: 'central location, good WiFi, gym',
    price_min: 100,
    price_max: 400,
    stars_min: 4,
    currency: 'EUR',
  },
  {
    city: 'Amsterdam',
    arrival_date: '2026-07-15',
    departure_date: '2026-07-18',
    adults: 2,
    children: 1,
    user_wishes: 'family-friendly, near city center, free cancellation',
    price_min: 60,
    price_max: 200,
    stars_min: 3,
    currency: 'EUR',
  },
  {
    city: 'Rome',
    arrival_date: '2026-10-01',
    departure_date: '2026-10-04',
    adults: 2,
    children: 0,
    user_wishes: 'romantic, historic area, rooftop terrace',
    price_min: 120,
    price_max: 350,
    stars_min: 4,
    currency: 'EUR',
  },
]

function pickPayload() {
  return PAYLOADS[Math.floor(Math.random() * PAYLOADS.length)]
}

const HEADERS = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
}

// ---------------------------------------------------------------------------
// Scenario: POST /api/hotels/search  (full synchronous pipeline)
// ---------------------------------------------------------------------------
function runSearch() {
  const payload = JSON.stringify(pickPayload())
  const start = Date.now()

  const res = http.post(`${BASE_URL}/api/hotels/search`, payload, {
    headers: HEADERS,
    timeout: '80s', // backend deadline is 62 s; allow buffer
  })

  const duration = Date.now() - start
  searchDuration.add(duration)

  const ok = check(res, {
    'search: status 200': (r) => r.status === 200,
    'search: has hotels array': (r) => {
      try {
        const body = JSON.parse(r.body)
        return Array.isArray(body.hotels)
      } catch {
        return false
      }
    },
    'search: completed within 75 s': () => duration < 75_000,
  })

  if (!ok || res.status !== 200) {
    errorRate.add(1)
    if (res.status === 504 || duration >= 75_000) {
      timeouts.add(1)
    }
  } else {
    errorRate.add(0)
  }
}

// ---------------------------------------------------------------------------
// Scenario: POST /api/hotels/search/stream  (SSE — measure first-byte latency)
// ---------------------------------------------------------------------------
function runStream() {
  const payload = JSON.stringify(pickPayload())
  const start = Date.now()

  // k6 does not natively support SSE; use http.post to measure TTFB
  const res = http.post(`${BASE_URL}/api/hotels/search/stream`, payload, {
    headers: { ...HEADERS, Accept: 'text/event-stream' },
    timeout: '80s',
  })

  const firstByte = Date.now() - start
  streamFirstByte.add(firstByte)

  const ok = check(res, {
    'stream: status 200': (r) => r.status === 200,
    'stream: contains event:result': (r) =>
      typeof r.body === 'string' && r.body.includes('event: result'),
  })

  errorRate.add(ok ? 0 : 1)
}

// ---------------------------------------------------------------------------
// Default function — mix of search and stream calls
// ---------------------------------------------------------------------------
export default function () {
  if (Math.random() < 0.7) {
    runSearch()
  } else {
    runStream()
  }

  // Think time: 1–3 seconds between requests
  sleep(1 + Math.random() * 2)
}

// ---------------------------------------------------------------------------
// Summary handler — print p50/p95/p99 per scenario
// ---------------------------------------------------------------------------
export function handleSummary(data) {
  const fmt = (v) => (v ? `${v.toFixed(0)} ms` : 'n/a')

  const rows = []
  for (const [name, metrics] of Object.entries(data.metrics)) {
    if (!name.startsWith('hotel_') && name !== 'http_req_duration') continue
    const m = metrics.values
    if (!m) continue
    rows.push(
      `${name.padEnd(30)} p50=${fmt(m['p(50)'])}  p95=${fmt(m['p(95)'])}  p99=${fmt(m['p(99)'])}  count=${m.count ?? '-'}`
    )
  }

  return {
    stdout: [
      '',
      '=== Hotel Search Load Test Summary ===',
      ...rows,
      `hotel_error_rate: ${((data.metrics.hotel_error_rate?.values?.rate ?? 0) * 100).toFixed(2)}%`,
      `hotel_timeouts:   ${data.metrics.hotel_timeouts?.values?.count ?? 0}`,
      '',
    ].join('\n'),
  }
}
