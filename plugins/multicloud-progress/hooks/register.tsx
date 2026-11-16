import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Progress, StepStatus } from '../types'

// The onboarding steps, in order. Change the list here and nowhere else.
export const STEPS = [
  { id: 'workstation', title: 'Prepare this computer' },
  { id: 'aws-account', title: 'AWS account' },
  { id: 'connect-aws', title: 'Connect AWS to Multicloud' },
  { id: 'quota', title: 'AWS GPU quota' },
  { id: 'extend-cluster', title: 'Check the Kubernetes cluster' },
  { id: 'extend-pool', title: 'Extend pool and peering' },
  { id: 'extend-first-run', title: 'First workload' },
  { id: 'cleanup', title: 'Cleanup' },
] as const

const PANE_ID = 'multicloud-onboarding'
const PANE_TITLE = 'Multicloud onboarding'
const TOOL_NAME = 'mark_step'
// The model calls the tool as mcp__<plugin>__<name>.
const TOOL_CALL = 'mcp__multicloud-progress__mark_step'
const STATUSES: readonly StepStatus[] = ['pending', 'active', 'done', 'waiting']
const MARKS: Record<StepStatus, string> = {
  pending: '·',
  active: '›',
  done: '✓',
  waiting: '!',
}
const NOTE_MAX = 200

// Shape tag: bump it when the stored value's meaning changes.
const progress = atom({ plugin: 'multicloud-progress', key: 'progress' } as const, {} as Progress, {
  shape: 'progress-1',
})

const isStepId = (id: string): boolean => STEPS.some(step => step.id === id)
const isStatus = (value: unknown): value is StepStatus =>
  STATUSES.some(status => status === value)
const clip = (text: string, width: number): string =>
  text.length > width ? `${text.slice(0, Math.max(0, width - 1))}…` : text

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: TOOL_NAME,
      description:
        'Mark an onboarding step in the Multicloud onboarding panel. Call it when a step starts (active), finishes (done), or waits on something the person must do (waiting, with a short note such as the open quota request IDs). Steps: ' +
        STEPS.map(step => step.id).join(', ') +
        '.',
      inputSchema: {
        type: 'object',
        properties: {
          step: { type: 'string', enum: STEPS.map(step => step.id) },
          status: { type: 'string', enum: [...STATUSES] },
          note: { type: 'string', maxLength: NOTE_MAX },
        },
        required: ['step', 'status'],
      },
      isDeferred: false,
    })
    void $.ui.open({ id: PANE_ID, title: PANE_TITLE })

    return next(e)
  })

  on('tool.call', { tool: TOOL_CALL }, async ($, e) => {
    try {
      const step = typeof e.step === 'string' ? e.step : ''
      if (!isStepId(step)) {
        return {
          deny: `Unknown step "${step}". Use one of: ${STEPS.map(s => s.id).join(', ')}.`,
        }
      }
      if (!isStatus(e.status)) {
        return {
          deny: `Unknown status "${String(e.status)}". Use one of: ${STATUSES.join(', ')}.`,
        }
      }
      const status: StepStatus = e.status
      const note =
        typeof e.note === 'string' && e.note.trim() !== ''
          ? e.note.trim().slice(0, NOTE_MAX)
          : undefined

      await update($, progress, current => ({
        ...current,
        [step]: note === undefined ? { status } : { status, note },
      }))

      return { result: { step, status, ...(note === undefined ? {} : { note }) } }
    } catch {
      return { deny: 'mark_step failed; the step was not marked.' }
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const current = await read($, progress)
    const width = Math.max(12, Number(e.props.bodyColumns) || 40)
    const done = STEPS.filter(step => current[step.id]?.status === 'done').length

    return (
      <Box flexDirection="column">
        <Text dimColor>{clip(`${done} of ${STEPS.length} done`, width)}</Text>
        {STEPS.map(step => {
          const state = current[step.id]
          const status: StepStatus = state?.status ?? 'pending'

          return (
            <Box key={step.id} flexDirection="column">
              <Text>{clip(`${MARKS[status]} ${step.title}`, width)}</Text>
              {state?.note !== undefined && (
                <Text dimColor>{clip(`    ${state.note}`, width)}</Text>
              )}
            </Box>
          )
        })}
      </Box>
    )
  })
}
