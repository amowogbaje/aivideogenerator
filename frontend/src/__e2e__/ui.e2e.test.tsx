/**
 * Drives the REAL React app (jsdom) against a REAL running backend:
 *   create series → add episode → review gate → approve → generate scene images → fix an image with a
 *   correction prompt → render → video appears.
 * Start the backend first (see README). Providers can be the offline demo ones.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, expect, test, vi } from 'vitest'
import App from '../App'

const BACKEND = (import.meta.env.VITE_E2E_BACKEND as string | undefined) ?? 'http://127.0.0.1:8000'
const LONG = { timeout: 180_000, interval: 500 }

beforeAll(() => {
  const realFetch = globalThis.fetch
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === 'string' && input.startsWith('/') ? BACKEND + input : input, init))
  // jsdom has no media playback
  vi.stubGlobal('Audio', class { play() { return Promise.resolve() } pause() {} })
  window.confirm = () => true
})
afterEach(cleanup)

const SCRIPT =
  'Ada walked into the old lighthouse at dawn. She carried a brass lantern and a worn map. "We are late," said Ada.\n' +
  'Her brother Tunde looked at the sea. He had never seen the harbor so quiet. "Then we should hurry," Tunde whispered.\n' +
  'Inside the lighthouse the stairs were steep. Ada lit the lantern and climbed.'

test('series → episode → approve → scene images → correction → render', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)

  // 1. create a series
  await user.type(await screen.findByPlaceholderText('The Lighthouse Keepers'), 'UI Test Series')
  await user.click(screen.getByRole('button', { name: 'Create series' }))
  await screen.findByRole('heading', { name: 'UI Test Series', level: 1 }, LONG)  // level 1 = the series page, not a list card

  // 2. add an episode (script is long, so set it directly instead of typing char by char)
  fireEvent.change(screen.getByPlaceholderText(/Episode 1/), { target: { value: 'Pilot' } })
  fireEvent.change(screen.getByLabelText(/^Script/), { target: { value: SCRIPT } })
  await user.click(screen.getByRole('button', { name: /Add episode & analyze/ }))

  // 3. the review gate: assets appear, scene generation is locked until they're approved
  await screen.findByText('2 · Review cast, places & props', undefined, LONG)
  const produce = await screen.findByRole('button', { name: /Generate scene images/ })
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Approve' }).length).toBeGreaterThanOrEqual(4), LONG)
  expect((produce as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText(/Approve \d+ more:/)).toBeTruthy()

  // a character's voice can be previewed
  await user.click(screen.getAllByRole('button', { name: /Preview/ })[0])

  // 4. approve everything -> the gate opens
  await user.click(screen.getByRole('button', { name: 'Approve all' }))
  await waitFor(() => expect((screen.getByRole('button', { name: /Generate scene images/ }) as HTMLButtonElement).disabled).toBe(false), LONG)
  await user.click(screen.getByRole('button', { name: /Generate scene images/ }))

  // 5. scene images appear
  await screen.findByText('3 · Scene images', undefined, LONG)
  await waitFor(() => {
    const imgs = screen.getAllByRole('img').filter((i) => /Scene \d+/.test(i.getAttribute('alt') ?? ''))
    expect(imgs.length).toBeGreaterThanOrEqual(3)
  }, LONG)
  const firstSrc = screen.getByAltText('Scene 2').getAttribute('src')

  // 6. correction prompt on a scene image
  const fixButtons = screen.getAllByRole('button', { name: 'Fix image…' })
  await user.click(fixButtons[fixButtons.length - 1])  // scene cards come after the asset cards
  const dialog = await screen.findByRole('dialog')
  const scenes = screen.getAllByText(/^Scene \d+$/)
  expect(scenes.length).toBeGreaterThanOrEqual(3)
  await user.type(within(dialog).getByLabelText(/What needs fixing/), 'remove the extra person')
  await user.click(within(dialog).getByRole('button', { name: 'Regenerate' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), LONG)
  await waitFor(() => expect((screen.getByRole('button', { name: /Render video/ }) as HTMLButtonElement).disabled).toBe(false), LONG)
  expect(firstSrc).toBeTruthy()

  // 7. render
  await user.click(screen.getByRole('button', { name: /Render video/ }))
  const download = await screen.findByRole('link', { name: 'Download MP4' }, LONG)
  expect(download.getAttribute('href')).toMatch(/^\/media\/.+\.mp4$/)
  const res = await fetch(download.getAttribute('href')!)
  expect(res.status).toBe(200)
  expect((await res.arrayBuffer()).byteLength).toBeGreaterThan(10_000)
}, 600_000)
