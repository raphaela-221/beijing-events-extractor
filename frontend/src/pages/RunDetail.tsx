import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Button } from 'antd'
import { JobRunner } from '../components/job/JobRunner'
import { JobForm } from '../components/job/JobForm'
import { runsApi } from '../api/runs'

function safeParseParams(json: string | null): Record<string, unknown> | undefined {
  if (!json) return undefined
  try {
    const p = JSON.parse(json)
    return typeof p === 'object' && p ? (p as Record<string, unknown>) : undefined
  } catch {
    return undefined
  }
}

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const [showRerun, setShowRerun] = useState(sp.get('rerun') === '1')

  const { data: run } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.get(runId!),
    enabled: !!runId,
  })

  if (!runId) return null

  // 已终态 + 非 dev 压测 job 才能再跑；dev job 不在 registry，JobForm 拉 schema 会 404
  const canRerun =
    !!run &&
    run.status !== 'running' &&
    run.status !== 'queued' &&
    !run.op_id.startsWith('__dev_')

  return (
    <div>
      {canRerun && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Button onClick={() => setShowRerun((v) => !v)}>
              {showRerun ? '收起再跑表单' : '用同参数再跑一遍'}
            </Button>
            <span className="page-sub" style={{ margin: 0 }}>
              预填本次参数，可改一个再跑（不会直接执行）
            </span>
          </div>
          {showRerun && (
            <div style={{ marginTop: 14 }}>
              <JobForm
                jobId={run!.op_id}
                preset={run!.preset || undefined}
                initialParams={safeParseParams(run!.params_json)}
                submitLabel="用同参数再跑"
                onSubmitted={(newId) => nav(`/runs/${newId}`)}
              />
            </div>
          )}
        </div>
      )}
      <JobRunner runId={runId} />
    </div>
  )
}
