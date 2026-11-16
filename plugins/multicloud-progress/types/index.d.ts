// The mod's state contract: one value, the status of each onboarding step.
// A step missing from the map is pending.

export type StepStatus = 'pending' | 'active' | 'done' | 'waiting'

export type StepState = { status: StepStatus; note?: string }

export type Progress = Record<string, StepState>

declare module 'claude-code' {
  interface PluginState {
    'multicloud-progress': { progress: Shaped<Progress> }
  }
}
