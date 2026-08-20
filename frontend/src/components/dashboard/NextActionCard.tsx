import { useNavigate } from 'react-router-dom'
import type { NextAction } from '../../api/pipeline'

const ICONS: Record<string, string> = {
  env_keys: '🔑',
  canonical_exists: '📋',
  canonical_structure: '🛠',
  dates_pending: '📅',
  data_freshness: '🔄',
  changed_months: '🎨',
  concert_state: '🎤',
  disk_space: '💾',
}

// 下一步建议卡：按优先级取第一条命中的检查项，做成显眼卡片 + 直达按钮（指南 §5.4）
export function NextActionCard({ action }: { action: NextAction | null }) {
  const nav = useNavigate()
  if (!action) {
    return (
      <div className="next-action">
        <div className="na-icon">✓</div>
        <div className="na-body">
          <div className="na-label">下一步建议</div>
          <div className="na-title">全部就绪，可以开始月度流程</div>
          <div className="na-sub">没有待处理的检查项。</div>
        </div>
      </div>
    )
  }
  const isBlock = action.severity === 'block'
  return (
    <div className={`next-action ${isBlock ? 'is-block' : ''}`}>
      <div className="na-icon">{ICONS[action.id] || '🛠'}</div>
      <div className="na-body">
        <div className="na-label">{isBlock ? '需先处理' : '下一步建议'}</div>
        <div className="na-title">{action.title}</div>
        <div className="na-sub">{action.desc}</div>
      </div>
      <a className={`btn ${isBlock ? 'danger solid' : 'primary'}`} onClick={() => nav(action.link)}>
        前往处理
      </a>
    </div>
  )
}
