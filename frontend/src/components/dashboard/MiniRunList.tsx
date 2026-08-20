import { useNavigate } from 'react-router-dom'
import type { Run } from '../../api/runs'
import { fmtDateTime } from '../../utils/format'

const BADGE_CLS: Record<string, string> = {
  success: 'success',
  failed: 'error',
  cancelled: 'idle',
  running: 'running',
  queued: 'idle',
}
const BADGE_TEXT: Record<string, string> = {
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
  running: '运行中',
  queued: '排队中',
}

// 最近运行 mini 列表：状态 badge + 标题 + 时间，点击跳详情
export function MiniRunList({ runs }: { runs: Run[] }) {
  const nav = useNavigate()
  if (!runs.length) {
    return <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>暂无运行记录</div>
  }
  return (
    <div>
      {runs.map((r) => (
        <div key={r.run_id} className="mini-run" onClick={() => nav(`/runs/${r.run_id}`)}>
          <span className={`badge ${BADGE_CLS[r.status] || 'idle'}`} style={{ width: 52 }}>
            <span className="bdot" />
            {BADGE_TEXT[r.status] || r.status}
          </span>
          <span className="mr-title">{r.op_label}</span>
          <span className="mr-time">{fmtDateTime(r.started_at)}</span>
        </div>
      ))}
    </div>
  )
}
