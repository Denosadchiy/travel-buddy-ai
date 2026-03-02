export interface DailyWeatherForecast {
  date: string
  weatherCode: number | null
  tempMax: number | null
  tempMin: number | null
  precipitationProbabilityMax: number | null
  precipitationSum: number | null
  windSpeedMax: number | null
  sunrise: string | null
  sunset: string | null
}

const WEATHER_API_URL = 'https://api.open-meteo.com/v1/forecast'

export async function getDailyWeatherForecast(
  latitude: number,
  longitude: number,
  date: string
): Promise<DailyWeatherForecast | null> {
  const url = new URL(WEATHER_API_URL)
  url.searchParams.set('latitude', String(latitude))
  url.searchParams.set('longitude', String(longitude))
  url.searchParams.set(
    'daily',
    [
      'weather_code',
      'temperature_2m_max',
      'temperature_2m_min',
      'precipitation_probability_max',
      'precipitation_sum',
      'wind_speed_10m_max',
      'sunrise',
      'sunset',
    ].join(',')
  )
  url.searchParams.set('timezone', 'auto')
  url.searchParams.set('start_date', date)
  url.searchParams.set('end_date', date)

  const response = await fetch(url.toString())
  if (!response.ok) {
    throw new Error(`Weather request failed with ${response.status}`)
  }

  const payload = await response.json()
  const daily = payload?.daily
  if (!daily?.time?.length) return null

  return {
    date: daily.time[0] ?? date,
    weatherCode: daily.weather_code?.[0] ?? null,
    tempMax: daily.temperature_2m_max?.[0] ?? null,
    tempMin: daily.temperature_2m_min?.[0] ?? null,
    precipitationProbabilityMax: daily.precipitation_probability_max?.[0] ?? null,
    precipitationSum: daily.precipitation_sum?.[0] ?? null,
    windSpeedMax: daily.wind_speed_10m_max?.[0] ?? null,
    sunrise: daily.sunrise?.[0] ?? null,
    sunset: daily.sunset?.[0] ?? null,
  }
}
