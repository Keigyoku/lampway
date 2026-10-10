// SPDX-FileCopyrightText: 2026 Lampway contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Display compatibility only: all rows come from the native history projection.
type Snapshot = {
  protocol: number
  session_id: string
  revision: number
  history: { count: number; messages: unknown[] }
}
type Context = {
  sid: () => string | undefined
  idle: () => boolean
  read: (sid: string) => Promise<Snapshot | null>
  replace: (messages: unknown[]) => void
}

let requestCurrent: (sid: string, after?: () => void) => boolean = () => false
export const requestNativeHistoryRefresh = (sid: string, after?: () => void): boolean => requestCurrent(sid, after)

export function createNativeHistoryRefresh(ctx: Context) {
  let sid = ''
  let epoch = 0
  let desired = -1
  let applied = -1
  let compatible = false
  let pending = false
  let again = false
  let force = false
  let acknowledgement: (() => void) | undefined

  const reset = () => {
    const current = ctx.sid() || ''
    if (current !== sid) {
      sid = current
      epoch++
      desired = applied = -1
      compatible = false
      force = false
      acknowledgement = undefined
    }
  }
  const pump = async () => {
    reset()
    if (pending) { again = true; return }
    if (!sid || !compatible || !ctx.idle() || !force) return
    const requestedSid = sid
    const requestedEpoch = epoch
    pending = true
    again = false
    try {
      const result = await ctx.read(requestedSid)
      reset()
      if (requestedSid !== sid || requestedEpoch !== epoch || !ctx.idle()) return
      if (!result || result.protocol !== 1 || result.session_id !== sid || !Number.isSafeInteger(result.revision)
          || result.revision < desired || result.revision < applied || !Array.isArray(result.history?.messages)) return
      applied = result.revision
      force = false
      ctx.replace(result.history.messages)
      const after = acknowledgement
      acknowledgement = undefined
      after?.()
    } catch {
      // A native busy/stale-session refusal leaves the current screen intact.
      // The next native invalidation/completion may request a fresh snapshot.
    } finally {
      pending = false
      if (again) queueMicrotask(() => { void pump() })
    }
  }
  const request = (requestedSid: string, after?: () => void): boolean => {
    reset()
    if (!compatible || requestedSid !== sid) return false
    epoch++
    force = true
    acknowledgement = after
    queueMicrotask(() => { void pump() })
    return true
  }
  requestCurrent = request
  const event = (type: string, payload?: unknown) => {
    reset()
    if (type.startsWith('gateway.')) {
      epoch++
      compatible = false
      desired = applied = -1
      force = false
      acknowledgement = undefined
      return
    }
    if (type.startsWith('message.') || type.startsWith('tool.')) {
      epoch++
      acknowledgement = undefined
    }
    if (type === 'session.info') {
      const value = payload as {
        lampway_history?: { protocol?: number; revision?: number; reason?: string }
        running?: boolean
      } | undefined
      const marker = value?.lampway_history
      if (marker?.protocol === 1 && Number.isSafeInteger(marker.revision) && marker.revision! >= 0) {
        compatible = true
        if (marker.reason === 'undo' && marker.revision! > applied) force = true
        if (marker.revision! > desired) { desired = marker.revision!; epoch++ }
      }
    }
    // Queue after the native handler has applied its busy/streaming state.
    if (type === 'session.info' || type === 'message.complete') queueMicrotask(() => { void pump() })
  }
  return { event, request }
}


// Frontend provenance is not a conversation row or a serializable protocol field.
const frontendNotice = Symbol('lampway.frontendNotice')
const nativeReplacement = Symbol('lampway.nativeHistoryReplacement')
export function markFrontendNotice<T extends object>(message: T): T {
  Object.defineProperty(message, frontendNotice, { value: true, enumerable: true })
  return message
}
export function retainFrontendNotices<T extends { kind?: string }>(previous: T[]): T[] {
  return previous.filter(message => message.kind === 'slash' || message.kind === 'panel'
    || (message as T & { [frontendNotice]?: boolean })[frontendNotice] === true)
}
export function nativeHistoryReplacement<T extends object>(setter: T): T {
  Object.defineProperty(setter, nativeReplacement, { value: true })
  return setter
}
export function isNativeHistoryReplacement(value: unknown): boolean {
  return typeof value === 'function' && (value as { [nativeReplacement]?: boolean })[nativeReplacement] === true
}
