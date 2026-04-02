/**
 * LoadingPage freeze-fix tests.
 * Run: npm test
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import LoadingPage from '../LoadingPage'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('../../api/trips', () => ({
  generatePlan: vi.fn(),
}))

vi.mock('../../store/tripStore', () => ({
  useTripStore: () => ({
    trip: { city: 'Barcelona' },
    setItinerary: vi.fn(),
  }),
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

import { generatePlan } from '../../api/trips'
const mockGeneratePlan = vi.mocked(generatePlan)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage(tripId = 'trip-123') {
  return render(
    <MemoryRouter initialEntries={[`/loading/${tripId}`]}>
      <Routes>
        <Route path="/loading/:tripId" element={<LoadingPage />} />
      </Routes>
    </MemoryRouter>
  )
}

/** Returns a Promise that never resolves + refs to resolve/reject it manually */
function pendingPromise() {
  let _resolve!: (v: unknown) => void
  let _reject!: (r: unknown) => void
  const p = new Promise((resolve, reject) => {
    _resolve = resolve
    _reject = reject
  })
  return { p, resolve: _resolve, reject: _reject }
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockNavigate.mockReset()
  mockGeneratePlan.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LoadingPage — normal load', () => {
  it('renders loading animation and cancel button on mount', async () => {
    const { p } = pendingPromise()
    mockGeneratePlan.mockReturnValue(p as any)

    renderPage()

    expect(screen.getByText('Barcelona')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    )
  })

  it('calls generatePlan once on mount', async () => {
    const { p } = pendingPromise()
    mockGeneratePlan.mockReturnValue(p as any)

    renderPage()

    await waitFor(() => expect(mockGeneratePlan).toHaveBeenCalledTimes(1))
    expect(mockGeneratePlan).toHaveBeenCalledWith('trip-123', expect.any(AbortSignal))
  })

  it('navigates to itinerary on successful response', async () => {
    mockGeneratePlan.mockResolvedValue({ days: [] } as any)

    renderPage()

    await waitFor(() => expect(mockNavigate).toHaveBeenCalled(), { timeout: 2000 })
    expect(mockNavigate).toHaveBeenCalledWith('/itinerary/trip-123', { replace: true })
  })
})

describe('LoadingPage — cancellation', () => {
  it('passes AbortSignal to generatePlan', async () => {
    const { p } = pendingPromise()
    mockGeneratePlan.mockReturnValue(p as any)

    renderPage()

    await waitFor(() => expect(mockGeneratePlan).toHaveBeenCalled())
    const signal = mockGeneratePlan.mock.calls[0][1]
    expect(signal).toBeInstanceOf(AbortSignal)
    expect(signal?.aborted).toBe(false)
  })

  it('aborts the in-flight request on unmount', async () => {
    let capturedSignal: AbortSignal | undefined
    const { p } = pendingPromise()
    mockGeneratePlan.mockImplementation((_id, signal) => {
      capturedSignal = signal
      return p as any
    })

    const { unmount } = renderPage()
    await waitFor(() => expect(mockGeneratePlan).toHaveBeenCalled())

    expect(capturedSignal?.aborted).toBe(false)
    unmount()
    expect(capturedSignal?.aborted).toBe(true)
  })

  it('Cancel button aborts request and calls navigate(-1)', async () => {
    let capturedSignal: AbortSignal | undefined
    const { p } = pendingPromise()
    mockGeneratePlan.mockImplementation((_id, signal) => {
      capturedSignal = signal
      return p as any
    })

    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(mockGeneratePlan).toHaveBeenCalled())

    const cancelBtn = await screen.findByRole('button', { name: /cancel/i })
    await user.click(cancelBtn)

    expect(capturedSignal?.aborted).toBe(true)
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })

  it('does NOT show an error when request is aborted by cancel (AbortError)', async () => {
    mockGeneratePlan.mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    renderPage()

    // Wait for the mock to be called and rejected
    await waitFor(() => expect(mockGeneratePlan).toHaveBeenCalled())
    // Give React time to update — error state should NOT appear
    await new Promise((r) => setTimeout(r, 100))

    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })
})

describe('LoadingPage — error handling', () => {
  it('shows error message and action buttons on API failure', async () => {
    mockGeneratePlan.mockRejectedValue(new Error('Service unavailable'))

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/service unavailable/i)).toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: /go back/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('retry fires a new generatePlan call with a distinct AbortSignal', async () => {
    const signals: (AbortSignal | undefined)[] = []

    mockGeneratePlan
      .mockImplementationOnce((_id, signal) => {
        signals.push(signal)
        return Promise.reject(new Error('first failure'))
      })
      .mockImplementationOnce((_id, signal) => {
        signals.push(signal)
        return new Promise(() => {}) // hang — keep loading
      })

    const user = userEvent.setup()
    renderPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(mockGeneratePlan).toHaveBeenCalledTimes(2))

    // Both calls received distinct, non-aborted signals
    expect(signals[0]).toBeInstanceOf(AbortSignal)
    expect(signals[1]).toBeInstanceOf(AbortSignal)
    expect(signals[0]).not.toBe(signals[1])
    expect(signals[1]?.aborted).toBe(false)
  })
})

describe('LoadingPage — timeout', () => {
  it('shows a friendly error on TimeoutError (not silently ignored)', async () => {
    mockGeneratePlan.mockRejectedValue(
      new DOMException('Request timeout', 'TimeoutError')
    )

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/request timed out/i)).toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})
