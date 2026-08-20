import { useEffect, useRef, useState } from 'react'
import { runsApi, type LogLine, type Run, type RunStatus } from '../api/runs'

interface Stage {
  index: number
  name: string
}

// 回放（REST 分页拉已落盘）+ SSE 续接（from_seq=last_seq+1），不重不漏。
export function useJobLog(runId: string) {
  const [run, setRun] = useState<Run | null>(null)
  const [lines, setLines] = useState<LogLine[]>([])
  const [status, setStatus] = useState<RunStatus>('running')
  const [stage, setStage] = useState<Stage | null>(null)
  const [summary, setSummary] = useState<unknown>(null)
  const [llm, setLlm] = useState<unknown>(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const r = await runsApi.get(runId)
      if (cancelled) return
      setRun(r)
      setStatus(r.status)
      if (r.stage_index != null)
        setStage({ index: r.stage_index, name: r.current_stage || '' })
      try {
        if (r.summary_json) setSummary(JSON.parse(r.summary_json))
      } catch {
        /* ignore */
      }
      try {
        if (r.llm_json) setLlm(JSON.parse(r.llm_json))
      } catch {
        /* ignore */
      }
      // 回放已落盘日志（分页直到追上）
      let from = 0
      const acc: LogLine[] = []
      while (true) {
        const page = await runsApi.log(runId, from, 5000)
        if (cancelled) return
        acc.push(...page.lines)
        from = page.last_seq
        if (!page.has_more) break
      }
      if (cancelled) return
      setLines(acc)
      if (['success', 'failed', 'cancelled'].includes(r.status)) return
      // SSE 续接
      const es = new EventSource(runsApi.streamUrl(runId, from))
      esRef.current = es
      es.onopen = () => setConnected(true)
      es.addEventListener('log', (e) => {
        const rec = JSON.parse((e as MessageEvent).data) as LogLine
        setLines((prev) =>
          prev.length && prev[prev.length - 1].seq >= rec.seq ? prev : [...prev, rec],
        )
      })
      es.addEventListener('stage', (e) => {
        const d = JSON.parse((e as MessageEvent).data)
        setStage({ index: d.stage_index, name: d.stage })
      })
      es.addEventListener('summary', (e) => {
        const d = JSON.parse((e as MessageEvent).data)
        if (d.summary_json) setSummary(d.summary_json)
        if (d.llm_json) setLlm(d.llm_json)
      })
      es.addEventListener('status', (e) => {
        const d = JSON.parse((e as MessageEvent).data)
        setStatus(d.status)
        setRun((prev) =>
          prev
            ? {
                ...prev,
                status: d.status,
                exit_code: d.exit_code ?? null,
                error_summary: d.error_summary ?? null,
                error_kind: d.error_kind ?? null,
                ended_at: d.ended_at ?? prev.ended_at,
                duration_ms: d.duration_ms ?? prev.duration_ms,
              }
            : prev,
        )
        if (['success', 'failed', 'cancelled'].includes(d.status)) es.close()
      })
      es.onerror = () => setConnected(false)
    })().catch(() => {
      /* 401 等由守卫处理；这里静默 */
    })
    return () => {
      cancelled = true
      esRef.current?.close()
    }
  }, [runId])

  return { run, lines, status, stage, summary, llm, connected }
}
