import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Checkbox, Modal, Pagination, Spin, Typography, Upload, App as AntdApp } from 'antd'
import { canonicalApi, type UploadResult } from '../api/canonical'
import { filesApi } from '../api/files'
import { useLockStore } from '../stores/useLockStore'
import { Flow3Steps, type StepState } from '../components/review/Flow3Steps'
import { DiffSummary } from '../components/review/DiffSummary'
import { fmtDateTime } from '../utils/format'

const PAGE_SIZE = 20

export function Review() {
  const nav = useNavigate()
  const { message } = AntdApp.useApp()
  const lock = useLockStore()

  const [downloadInfo, setDownloadInfo] = useState<{ download_id: string; at: string } | null>(null)
  const [uploadId, setUploadId] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [commitResult, setCommitResult] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [checked, setChecked] = useState(false)
  const [committing, setCommitting] = useState(false)

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [priority, setPriority] = useState('')
  const preview = useQuery({
    queryKey: ['canonical-preview', page, search, priority],
    queryFn: () => canonicalApi.preview({ page, page_size: PAGE_SIZE, search, priority }),
  })

  const onDownload = async () => {
    try {
      const { blob, download_id } = await canonicalApi.download()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'Events List.xlsx'
      a.click()
      URL.revokeObjectURL(url)
      setDownloadInfo({ download_id, at: new Date().toISOString() })
      setUploadResult(null)
      setUploadId(null)
      setCommitResult(null)
      message.success('已下载，请在本地 Excel 修改后上传回传')
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onFile = async (file: File) => {
    try {
      const { upload_id } = await filesApi.upload([file])
      setUploadId(upload_id)
      const result = await canonicalApi.upload(upload_id, downloadInfo?.download_id || null)
      setUploadResult(result)
      setChecked(false)
      setCommitResult(null)
      if (!result.hash_match) {
        message.warning('你下载的版本已不是最新，请查看版本过期警告')
      } else {
        message.success('结构校验通过，已生成差异摘要')
      }
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onAcquire = async () => {
    try {
      await lock.acquire()
      lock.refresh()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const doCommit = async () => {
    if (!uploadId) return
    setCommitting(true)
    try {
      const r = await canonicalApi.commit(uploadId)
      setCommitResult(r.backup_path)
      setConfirmOpen(false)
      message.success('已写回 canonical，已自动备份')
      preview.refetch()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setCommitting(false)
    }
  }

  const stepStates: StepState[] = [
    downloadInfo ? 'done' : 'active',
    uploadResult ? 'done' : downloadInfo ? 'active' : 'idle',
    uploadResult ? (commitResult ? 'done' : 'active') : 'idle',
  ]
  const stepDescs = [
    downloadInfo ? `已下载 · ${fmtDateTime(downloadInfo.at)}` : '下载当前 Events List.xlsx',
    downloadInfo ? '在桌面 Excel 中编辑，改完保存' : '请先下载清单',
    uploadResult ? '已上传，确认差异后写回' : '拖拽修改后的文件到下方区域',
  ]

  const lockByMe = !!lock.held && !!lock.is_me
  const diffTotal = uploadResult
    ? uploadResult.diff.added + uploadResult.diff.deleted + uploadResult.diff.modified
    : 0

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">人工核对</div>
          <div className="page-sub">下载当前清单 -&gt; 本地 Excel 修改 -&gt; 上传回传，系统自动校验并给出差异摘要</div>
        </div>
        <button className="btn ghost sm" onClick={() => nav('/dashboard')}>← 返回总览</button>
      </div>

      <div className="card">
        <Flow3Steps states={stepStates} descs={stepDescs} />
      </div>

      {uploadResult && !uploadResult.hash_match && (
        <div className="banner warn">
          <span className="ic">⚠️</span>
          <div>
            <b>你下载的版本已不是最新</b><br />
            下载后 canonical 被其他运行修改过（共 {uploadResult.intervening_runs.length} 次）。若继续覆盖，那些运行新增的内容将会丢失。
            <div style={{ marginTop: 8, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              {uploadResult.intervening_runs.map((r) => (
                <span key={r.run_id}>
                  <a onClick={() => nav(`/runs/${r.run_id}`)}>{r.op_label}</a> · {fmtDateTime(r.started_at)} · {r.status}
                </span>
              ))}
              <a onClick={onDownload}>重新下载最新版本</a>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title">下载当前清单</div>
        <div className="row-actions">
          <button className="btn primary" onClick={onDownload}>↓ 下载 Events List.xlsx</button>
        </div>
        <div className="page-sub" style={{ marginTop: 6 }}>
          共 {preview.data?.total ?? '?'} 条事件
        </div>
      </div>

      <div className="card">
        <div className="card-title">上传修改后的文件</div>
        <Upload.Dragger
          accept=".xlsx"
          multiple={false}
          showUploadList={false}
          beforeUpload={(file) => {
            onFile(file)
            return false
          }}
        >
          <div style={{ fontSize: 26, color: '#9CA3AF', marginBottom: 8 }}>⇪</div>
          <div style={{ fontSize: 13.5, color: '#1F2937' }}>拖拽 xlsx 文件到此处，或点击选择文件</div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>仅支持 .xlsx，上传后自动校验结构完整性</div>
        </Upload.Dragger>
      </div>

      {uploadResult && (
        <div className="card">
          <div className="card-title">
            差异摘要
            <span className="hint">结构校验通过 · {uploadResult.hash_match ? '版本一致' : '版本过期'}</span>
          </div>
          <DiffSummary diff={uploadResult.diff} />
          <div className="row-actions" style={{ marginTop: 14 }}>
            <button
              className="btn primary"
              disabled={!lockByMe || diffTotal === 0 || !!commitResult}
              onClick={() => setConfirmOpen(true)}
              title={!lockByMe ? '需要先获取编辑锁' : undefined}
            >
              确认覆盖
            </button>
            {!lockByMe && !commitResult && (
              <button className="btn" onClick={onAcquire}>获取编辑锁</button>
            )}
            {!commitResult && (
              <button className="btn ghost" onClick={() => { setUploadResult(null); setUploadId(null) }}>取消</button>
            )}
          </div>
          {commitResult && (
            <div className="banner info" style={{ marginTop: 12, marginBottom: 0 }}>
              <span className="ic">✓</span>
              <div>已写回 canonical，备份已保存：<code>{commitResult}</code></div>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-title">
          当前清单预览
          <span className="hint">只读 · {preview.data?.total ?? 0} 条事件</span>
        </div>
        <div className="toolbar-row">
          <input
            className="search"
            placeholder="搜索标题 / 关键词…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          />
          <select value={priority} onChange={(e) => { setPriority(e.target.value); setPage(1) }}>
            <option value="">全部优先级</option>
            <option value="High">High</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>No.</th>
                <th>Topic</th>
                <th>Headline</th>
                <th>日期</th>
                <th>Dates</th>
                <th>Priority</th>
                <th>关键词</th>
              </tr>
            </thead>
            <tbody>
              {preview.isLoading ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 30 }}><Spin /></td></tr>
              ) : (preview.data?.items || []).map((e) => (
                <tr key={e.no}>
                  <td>{e.no}</td>
                  <td>{e.topic}</td>
                  <td>{e.headline}</td>
                  <td>{e.start_date}{e.end_date && e.end_date !== e.start_date ? ` ~ ${e.end_date}` : ''}</td>
                  <td>{e.dates ? <span className="mono" style={{ color: '#4F46E5' }}>{e.dates}</span> : <span style={{ color: '#D1D5DB' }}>—</span>}</td>
                  <td><PriorityText p={e.priority} /></td>
                  <td>{e.keywords}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {preview.data && preview.data.total > PAGE_SIZE && (
          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <Pagination
              current={page}
              pageSize={PAGE_SIZE}
              total={preview.data.total}
              onChange={(p) => setPage(p)}
              showTotal={(t) => `共 ${t} 条`}
              size="small"
            />
          </div>
        )}
      </div>

      <Modal
        open={confirmOpen}
        title="⚠️ 确认覆盖人工审核清单？"
        okText="确认覆盖并写回"
        cancelText="取消"
        okButtonProps={{ disabled: !checked, loading: committing }}
        onOk={doCommit}
        onCancel={() => setConfirmOpen(false)}
      >
        <Typography.Paragraph style={{ fontSize: 13, color: '#6B7280' }}>
          将写入 <b>{uploadResult?.diff.added} 新增 / {uploadResult?.diff.deleted} 删除 / {uploadResult?.diff.modified} 修改</b>，
          覆盖前会自动备份当前版本。此操作会立即生效，Step 2 需要重新生成才能反映到日历页面。
        </Typography.Paragraph>
        <div className="checkline">
          <Checkbox checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          我已核对差异摘要，确认无误
        </div>
      </Modal>
    </div>
  )
}

function PriorityText({ p }: { p: string }) {
  const pl = p.toLowerCase()
  if (pl === 'high') return <span className="priority-high">High</span>
  if (p === '中') return <span className="priority-mid">中</span>
  if (p === '低') return <span className="priority-low">低</span>
  return <span>{p}</span>
}
