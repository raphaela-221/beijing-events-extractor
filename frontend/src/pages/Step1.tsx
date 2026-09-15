import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '../api/runs'
import { fmtDateTime } from '../utils/format'
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

// 产出说明（三类 job 行为一致）：Step1 产出独立日期文件，不改人工核对清单（canonical）

function LastOutputCard({ onDetail }: { onDetail: (runId: string) => void }) {
  const { data: page } = useQuery({
    queryKey: ['step1-last-output'],
    queryFn: () =>
      runsApi.listRuns({
        op_id: ['step1_full', 'step1_input_only', 'step1_concert_only'],
        status: ['success'],
        sort: 'started_at:desc',
        page: 1,
        page_size: 5,
      }),
  })
  // 最近一次成功的 step1 运行；产出文件按运行日期定位，当天多次运行指向同一文件
  const last = page?.items?.[0]
  if (!last) return null
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title">最近一次产出</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Typography.Text style={{ fontSize: 13 }}>
          {fmtDateTime(last.started_at)} · {last.op_label}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          （成功 · 产出文件按运行日期命名，当天多次运行指向同一份）
        </Typography.Text>
        <a className="btn ghost sm" href={runsApi.outputDownloadUrl(last.run_id)} target="_blank" rel="noreferrer">
          下载产出 Excel
        </a>
        <button className="btn ghost sm" onClick={() => onDetail(last.run_id)}>
          查看运行详情
        </button>
      </div>
    </div>
  )
}


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

      <LastOutputCard onDetail={(runId) => nav(`/runs/${runId}?from=step1`)} />

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
        <Typography.Text type="secondary" style={{ fontSize: 12.5, display: 'block', marginBottom: 12 }}>
          产出为独立日期文件（运行详情页可下载），不会直接改人工核对清单；新事件需到人工核对页手动合并。
        </Typography.Text>
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
