import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { STEPS } from './register'

const TOOL = 'mcp__multicloud-progress__mark_step'

const PANE = {
  plugin: 'multicloud-progress',
  component: 'Pane',
  requestId: 'multicloud-onboarding',
  props: {
    title: 'Multicloud onboarding',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

// What the engine answers beneath the plugin for the calls it makes on `$`.
function stubEngine(on: On) {
  on('tool.register', () => ({ value: { tool: TOOL } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

test('mark_step marks a step and the pane draws the check mark', async ($, on) => {
  stubEngine(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  const answer = await $.tool.call({
    tool: TOOL,
    step: 'aws-account',
    status: 'done',
  })
  expect(answer.isError).toBeUndefined()

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  const row = await ui.find({ type: 'Text', text: /✓ AWS account/ })
  expect(row?.text).toBe('✓ AWS account')
  expect((await ui.find({ type: 'Text', text: /1 of 8 done/ }))?.text).toBe(
    '1 of 8 done',
  )
  await ui.unmount()
})

test('an unknown step id is refused with a clear message', async ($, on) => {
  stubEngine(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  const answer = await $.tool.call({
    tool: TOOL,
    step: 'no-such-step',
    status: 'done',
  })
  // The hook refuses with `{ deny }`; the model reads the reason as the error.
  expect(answer.deny).toMatch(/Unknown step "no-such-step"/)
  expect(answer.deny).toMatch(/aws-account/)

  // Nothing was marked: the pane still shows zero done.
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /0 of 8 done/ }))?.text).toBe(
    '0 of 8 done',
  )
  await ui.unmount()
})

test('the pane renders every step, all pending until marked', async ($, on) => {
  stubEngine(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  expect(STEPS.length).toBe(8)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  for (const step of STEPS) {
    const row = await ui.find({ type: 'Text', text: new RegExp(`· ${step.title}$`) })
    expect(row?.text).toBe(`· ${step.title}`)
  }
  await ui.unmount()
})
