import type { HealthCheck } from '../../api/pipeline'

const LABELS: Record<string, string> = {
  env_keys: 'LLM key',
  canonical_exists: '清单存在',
  canonical_structure: '清单结构',
  dates_pending: '待补 Dates',
  data_freshness: '日历新鲜度',
  changed_months: '待重算主题',
  concert_state: '演唱会采集',
  disk_space: '磁盘空间',
}

// 健康检查条：全绿收起 / 有警告展开 / 有阻断项红条置顶（指南 §5.4、附录 C HealthStrip）
export function HealthStrip({ checks }: { checks: HealthCheck[] }) {
  const blockCount = checks.filter((c) => c.block).length
  const warnCount = checks.filter((c) => c.status === 'warn').length
  const cls = blockCount > 0 ? 'has-block' : warnCount > 0 ? 'has-warn' : 'all-ok'
  const msg = blockCount > 0
    ? `⚠ ${blockCount} 项阻断`
    : warnCount > 0
    ? `${warnCount} 项待处理`
    : '✓ 全部正常'
  return (
    <div className={`health-strip ${cls}`}>
      <span className="health-msg">{msg}</span>
      {checks.map((c) => (
        <div key={c.id} className={`health-item ${c.status}`} title={c.detail}>
          <span className="hi-dot" />
          {LABELS[c.id] || c.id}
        </div>
      ))}
    </div>
  )
}
