import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { JobForm } from '../components/job/JobForm'

const PRESETS = [
  {
    id: 'step1_full',
    icon: '📦',
    title: '全量抽取',
    desc: '处理上传文件 + 同时采集北京演唱会。月度例行首选，覆盖最全。',
  },
  {
    id: 'step1_input_only',
    icon: '📄',
    title: '只处理上传文件',
    desc: '跳过演唱会采集。政务网站不可达时的备选，先出文件类结果。',
  },
  {
    id: 'step1_concert_only',
    icon: '🎤',
    title: '只采集演唱会',
    desc: '不处理本地文件，只重新采集演唱会信息。用于单独刷新演出数据。',
  },
] as const

export function Step1() {
  const nav = useNavigate()
  const [selected, setSelected] = useState<string>('step1_full')
  const preset = PRESETS.find((p) => p.id === selected)!
  const submitLabel = selected === 'step1_concert_only' ? '开始采集' : '开始抽取'

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Step 1 · 上传与抽取</div>
          <div className="page-sub">选一个预设，或展开高级选项自定义参数</div>
        </div>
        <button className="btn ghost sm" onClick={() => nav('/dashboard')}>
          ← 返回总览
        </button>
      </div>

      <div className="card">
        <div className="card-title">选择运行方式</div>
        <div className="preset-grid">
          {PRESETS.map((p) => (
            <div
              key={p.id}
              className={`preset-card${p.id === selected ? ' selected' : ''}`}
              onClick={() => setSelected(p.id)}
            >
              <div className="pc-icon">{p.icon}</div>
              <div className="pc-title">{p.title}</div>
              <div className="pc-desc">{p.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">{preset.title} · 参数</div>
        <JobForm
          key={selected}
          jobId={selected}
          preset={selected}
          submitLabel={submitLabel}
          onSubmitted={(runId) => nav(`/runs/${runId}?from=step1`)}
        />
      </div>
    </div>
  )
}
