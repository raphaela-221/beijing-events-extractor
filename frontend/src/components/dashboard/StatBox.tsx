import type { PipelineStats } from '../../api/pipeline'

// 统计行：事件总数 / High 优先级 / 覆盖月份 / 最后修改
export function StatBox({ stats }: { stats: PipelineStats }) {
  const total = stats.total_events ?? 0
  const high = stats.high_priority ?? 0
  const pct = total > 0 ? Math.round((high / total) * 100) : 0
  return (
    <div className="stat-row">
      <div className="stat-box">
        <div className="sb-k">当前事件总数</div>
        <div className="sb-v">{total || '-'}</div>
        <div className="sb-sub">canonical 全量</div>
      </div>
      <div className="stat-box">
        <div className="sb-k">High 优先级</div>
        <div className="sb-v" style={{ color: 'var(--error)' }}>{high || '-'}</div>
        <div className="sb-sub">占比 {pct}%</div>
      </div>
      <div className="stat-box">
        <div className="sb-k">覆盖月份</div>
        <div className="sb-v">{stats.covered_months ?? '-'}</div>
        <div className="sb-sub">个自然月</div>
      </div>
      <div className="stat-box">
        <div className="sb-k">最后修改</div>
        <div className="sb-v" style={{ fontSize: 16 }}>{stats.last_modified || '-'}</div>
        <div className="sb-sub">canonical 更新时间</div>
      </div>
    </div>
  )
}
