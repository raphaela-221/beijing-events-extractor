import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { JobForm } from './JobForm'
import type { JobSchema, LastRun } from '../../api/jobs'
import { fmtDateTime } from '../../utils/format'

const ST: Record<string, string> = {
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
  running: '运行中',
  queued: '排队中',
}

export function JobCard({ job, lastRun }: { job: JobSchema; lastRun?: LastRun }) {
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const isDry = job.id.endsWith('_dry')
  const runLabel = isDry ? '试运行' : '运行'

  return (
    <div className={`job-card${job.danger === 'destructive' ? ' danger' : ''}`}>
      <div className="jc-head">
        <span className="jc-title">{job.label}</span>
        {job.danger === 'write_canonical' && <span className="tag-mini write">写 canonical</span>}
        {job.danger === 'destructive' && <span className="tag-mini destructive">破坏性</span>}
        {job.admin_only && <span className="tag-mini admin">管理员</span>}
      </div>
      <div className="jc-desc">{job.desc}</div>
      <div className="jc-foot">
        <span className="jc-last">
          {lastRun
            ? `上次：${fmtDateTime(lastRun.started_at)} · ${ST[lastRun.status] || lastRun.status}`
            : '未运行过'}
        </span>
        <button
          className={`btn sm${job.danger === 'destructive' ? ' danger' : ''}`}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? '收起' : runLabel}
        </button>
      </div>
      {open && (
        <div className="jc-form">
          <JobForm
            jobId={job.id}
            submitLabel={runLabel}
            onSubmitted={(id) => nav(`/runs/${id}?from=toolbox`)}
          />
        </div>
      )}
    </div>
  )
}
