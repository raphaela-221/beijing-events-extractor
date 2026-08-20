import { Card, Empty, Typography } from 'antd'

interface ConcertSummary {
  list_total?: number
  list_ok?: number
  list_failed?: number
  list_items?: number
  detail_total?: number
  detail_ok?: number
  detail_failed?: number
  detail_no_table?: number
  filt_keyword?: number
  filt_dup?: number
  filt_non_bj?: number
  filt_venue?: number
  final?: number
}

interface LlmProvider {
  label?: string
  calls?: number
  prompt?: number
  completion?: number
  total?: number
}
interface LlmSummary {
  providers?: LlmProvider[]
  total?: { calls: number; tokens: number }
}

// step2 阶段成果：run_pipeline.py 各子脚本打印的 📊 [Pipeline] 块，后端 summary.py 解析进 summary_json.pipeline
type PipelineData = Record<string, Record<string, number | string>>
const STAGES: { id: string; label: string }[] = [
  { id: 'extract', label: '抽取' },
  { id: 'themes', label: '主题' },
  { id: 'calendar', label: '校验' },
  { id: 'package', label: '打包' },
]

function Box({ k, v, sub }: { k: string; v: React.ReactNode; sub?: string }) {
  return (
    <div
      style={{
        border: '1px solid #F0F0F0',
        borderRadius: 6,
        padding: '12px 14px',
        background: '#FAFAFC',
      }}
    >
      <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 6 }}>{k}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: '#1F2937' }}>{v}</div>
      {sub ? (
        <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>{sub}</div>
      ) : null}
    </div>
  )
}

// 摘要卡片：标题随 summary 内容动态变化，避免「只处理文件」也显示「演唱会采集回显」。
// - 有 concert 数据 -> 「演唱会采集回显」+ 阶段计数
// - 有 pipeline 数据（step2 阶段成果）-> 「阶段成果」
// - 仅 LLM -> 「运行摘要」
// - 都无 -> 运行中显示「运行中…」，结束显示「本次无摘要」
export function SummaryCards({
  summary,
  llm,
  running,
}: {
  summary: unknown
  llm: unknown
  running: boolean
}) {
  const concert = (summary as { concert?: ConcertSummary } | null)?.concert
  const llmObj = llm as LlmSummary | null
  const pipeline = (summary as { pipeline?: PipelineData } | null)?.pipeline
  const hasConcert = !!concert
  const hasLlm = !!(llmObj && llmObj.providers && llmObj.providers.length > 0)
  const hasPipeline = !!pipeline && Object.keys(pipeline).length > 0

  if (!hasConcert && !hasLlm && !hasPipeline) {
    return (
      <Card title="运行摘要" size="small">
        <Empty
          description={running ? '运行中，摘要将在结束时填充' : '本次无摘要'}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    )
  }

  const title = hasConcert ? '演唱会采集回显' : hasPipeline ? '阶段成果' : '运行摘要'

  return (
    <Card
      title={title}
      size="small"
      extra={
        hasConcert ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            阶段计数
          </Typography.Text>
        ) : undefined
      }
    >
      {hasConcert && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
          <Box
            k="列表页分段"
            v={concert!.list_total ?? '-'}
            sub={`成功 ${concert!.list_ok ?? 0} / 失败 ${concert!.list_failed ?? 0}`}
          />
          <Box
            k="详情页"
            v={concert!.detail_total ?? '-'}
            sub={`成功 ${concert!.detail_ok ?? 0} / 失败 ${concert!.detail_failed ?? 0} / 无表格 ${concert!.detail_no_table ?? 0}`}
          />
          <Box
            k="最终入库"
            v={concert!.final ?? '-'}
            sub={`过滤：关键词 ${concert!.filt_keyword ?? 0} · 已采集 ${concert!.filt_dup ?? 0} · 非北京 ${concert!.filt_non_bj ?? 0} · 场地小 ${concert!.filt_venue ?? 0}`}
          />
        </div>
      )}
      {hasPipeline && (
        <div style={{ marginTop: hasConcert ? 14 : 0 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            阶段成果
          </Typography.Text>
          <div style={{ marginTop: 6 }}>
            {STAGES.filter((s) => pipeline![s.id]).map((s) => {
              const kvs = Object.entries(pipeline![s.id])
                .map(([k, v]) => `${k} ${v}`)
                .join(' · ')
              return (
                <div
                  key={s.id}
                  style={{
                    display: 'flex',
                    padding: '5px 0',
                    borderBottom: '1px dashed #F0F0F0',
                  }}
                >
                  <span style={{ flex: '0 0 56px', color: '#9CA3AF', fontSize: 12.5 }}>
                    {s.label}
                  </span>
                  <span style={{ color: '#1F2937', fontSize: 12.5 }}>{kvs}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {hasLlm && (
        <div style={{ marginTop: hasConcert || hasPipeline ? 14 : 0 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            LLM 用量
          </Typography.Text>
          <div style={{ marginTop: 6, fontSize: 12.5, color: '#6B7280' }}>
            {llmObj!.providers!.map((p) => (
              <div key={p.label}>
                {p.label}：{p.calls} 次调用 · prompt {p.prompt} + completion {p.completion} = {p.total} tok
              </div>
            ))}
            {llmObj!.total ? (
              <div style={{ marginTop: 4, color: '#1F2937', fontWeight: 500 }}>
                合计：{llmObj!.total.calls} 次调用 · {llmObj!.total.tokens} tok
              </div>
            ) : null}
          </div>
        </div>
      )}
    </Card>
  )
}
