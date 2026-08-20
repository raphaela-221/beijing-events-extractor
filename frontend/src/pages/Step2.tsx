import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { App as AntdApp, Button, InputNumber } from 'antd'
import { JobForm } from '../components/job/JobForm'
import { jobsApi } from '../api/jobs'
import { pipelineApi } from '../api/pipeline'

type Mode = 'all' | 'step'

const SUBSTEPS = [
  { id: 'step2_extract', title: '① 抽取 High 事件', desc: 'run_pipeline.py extract · 从 canonical 抽取 High 事件' },
  { id: 'step2_themes', title: '② 生成月度主题', desc: 'run_pipeline.py themes · 调 Ark 增量生成主题' },
  { id: 'step2_calendar', title: '③ 校验页面文件齐全', desc: 'run_pipeline.py calendar · 校验页面文件可用' },
  { id: 'step2_package', title: '④ 打包分享文件', desc: 'run_pipeline.py package · 打包到 02_web_output/' },
] as const

export function Step2() {
  const nav = useNavigate()
  const { message } = AntdApp.useApp()
  const [mode, setMode] = useState<Mode>('all')
  const [year, setYear] = useState<number>(2026)
  const [running, setRunning] = useState<string | null>(null)

  // changed_months：复用总览页健康检查，非空（warn）时顶部提示
  const { data: state } = useQuery({
    queryKey: ['pipeline-state'],
    queryFn: pipelineApi.state,
  })
  const cmCheck = state?.checks.find((c) => c.id === 'changed_months')
  const changedMonths = cmCheck && cmCheck.status === 'warn' ? cmCheck.detail : ''

  const runSub = async (jobId: string, params: Record<string, unknown>) => {
    setRunning(jobId)
    try {
      const { run_id } = await jobsApi.run(jobId, params, 'step2')
      nav(`/runs/${run_id}?from=step2`)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setRunning(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Step 2 · 生成日历</div>
          <div className="page-sub">从人工审核清单抽取 High 事件，生成月度主题与日历页面</div>
        </div>
        <button className="btn ghost sm" onClick={() => nav('/dashboard')}>
          ← 返回总览
        </button>
      </div>

      {changedMonths && (
        <div className="banner info">
          <span className="ic">ℹ</span>
          <div>
            <b>有月份将重新生成主题</b>：{changedMonths}。其余月份复用已有主题，不会重复调用模型。
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title">运行方式</div>
        <div className="pill-tabs">
          <div className={`pill${mode === 'all' ? ' active' : ''}`} onClick={() => setMode('all')}>
            一键整跑
          </div>
          <div className={`pill${mode === 'step' ? ' active' : ''}`} onClick={() => setMode('step')}>
            分步执行
          </div>
        </div>

        {mode === 'all' ? (
          <div style={{ marginTop: 18 }}>
            <JobForm
              jobId="step2_all"
              preset="step2_all"
              submitLabel="开始生成"
              onSubmitted={(runId) => nav(`/runs/${runId}?from=step2`)}
            />
          </div>
        ) : (
          <>
            <div style={{ marginTop: 18, display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className="page-sub" style={{ margin: 0 }}>
                公共年份（仅「生成月度主题」步骤使用）
              </span>
              <InputNumber
                value={year}
                onChange={(v) => setYear(Number(v) || 2026)}
                style={{ width: 120 }}
              />
            </div>
            <div className="page-sub" style={{ margin: '16px 0 6px' }}>
              ↓ 可单独跑其中一步，适合只想重跑某一环节时使用
            </div>
            <div className="substep-list">
              {SUBSTEPS.map((s) => (
                <div key={s.id} className="substep-row">
                  <div className="ss-title">{s.title}</div>
                  <div className="ss-desc">{s.desc}</div>
                  <Button
                    size="small"
                    loading={running === s.id}
                    onClick={() =>
                      runSub(
                        s.id,
                        s.id === 'step2_themes' ? { year, force_month: '' } : {},
                      )
                    }
                  >
                    单独运行
                  </Button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
