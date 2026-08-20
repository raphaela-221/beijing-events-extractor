import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntdApp, Checkbox, Modal, Radio, Spin } from 'antd'
import { runsApi, type PurgeFilters } from '../../api/runs'
import { useAuthStore } from '../../stores/useAuthStore'
import { fmtBytes } from '../../utils/format'

export function PurgePreviewModal({
  open,
  onClose,
  filters,
}: {
  open: boolean
  onClose: () => void
  filters: PurgeFilters
}) {
  const { message } = AntdApp.useApp()
  const qc = useQueryClient()
  const isAdmin = useAuthStore((s) => s.user)?.role === 'admin'
  const [mode, setMode] = useState<'trash' | 'purge'>('trash')
  const [deleteArtifacts, setDeleteArtifacts] = useState(false)
  const [busy, setBusy] = useState(false)

  const { data: preview, isLoading } = useQuery({
    queryKey: ['purge-preview', filters],
    queryFn: () => runsApi.purgePreview(filters),
    enabled: open,
  })

  useEffect(() => {
    if (!open) {
      setMode('trash')
      setDeleteArtifacts(false)
      setBusy(false)
    }
  }, [open])

  const doBulk = async () => {
    if (mode === 'purge' && !isAdmin) {
      message.error('彻底删除需要管理员权限')
      return
    }
    if (!preview || preview.count === 0) return
    setBusy(true)
    try {
      const res = await runsApi.bulkDelete(filters, mode, deleteArtifacts)
      message.success(
        `已${mode === 'purge' ? '彻底删除' : '移入回收站'} ${res.deleted_count} 条` +
          (res.freed_bytes ? `，释放 ${fmtBytes(res.freed_bytes)}` : ''),
      )
      qc.invalidateQueries({ queryKey: ['runs-list'] })
      qc.invalidateQueries({ queryKey: ['runs-trash'] })
      onClose()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      title="按条件批量删除"
      onCancel={onClose}
      onOk={doBulk}
      okText={mode === 'purge' ? '彻底删除' : '移入回收站'}
      okButtonProps={{ danger: mode === 'purge', loading: busy }}
      cancelText="取消"
      width={560}
    >
      {isLoading || !preview ? (
        <Spin />
      ) : preview.count === 0 ? (
        <div className="page-sub">没有符合条件的可删记录（已排除置顶与最后成功记录）。</div>
      ) : (
        <div>
          <div className="banner warn" style={{ marginBottom: 12 }}>
            <span className="ic">🗑</span>
            <div>
              将{mode === 'purge' ? '彻底删除' : '移入回收站'} <b>{preview.count}</b> 条记录
              {preview.freed_bytes ? `，释放约 ${fmtBytes(preview.freed_bytes)}` : ''}。
            </div>
          </div>
          {(preview.pinned_count > 0 || preview.last_success_count > 0) && (
            <div className="page-sub" style={{ marginBottom: 12 }}>
              其中
              {preview.pinned_count > 0 && `${preview.pinned_count} 条已置顶`}
              {preview.pinned_count > 0 && preview.last_success_count > 0 && '、'}
              {preview.last_success_count > 0 && `${preview.last_success_count} 条为某操作最后成功记录`}
              ，<b>已自动跳过</b>。
            </div>
          )}
          {preview.sample.length > 0 && (
            <div className="kv-list" style={{ marginBottom: 12 }}>
              <div className="row">
                <span className="l">抽样</span>
                <span className="r">
                  {preview.sample
                    .map((s) => `${s.started_at.slice(0, 10)} ${s.op_label}（${s.status}）`)
                    .join('、')}
                </span>
              </div>
            </div>
          )}
          <div style={{ marginBottom: 8 }}>
            <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
              <Radio value="trash">移入回收站（30 天可恢复）</Radio>
              <Radio value="purge" disabled={!isAdmin}>
                彻底删除{!isAdmin ? '（需管理员）' : ''}
              </Radio>
            </Radio.Group>
          </div>
          {mode === 'purge' && (
            <label className="rr-check">
              <Checkbox
                checked={deleteArtifacts}
                onChange={(e) => setDeleteArtifacts(e.target.checked)}
              />{' '}
              同时删除产物文件（.bak 永不删）
            </label>
          )}
        </div>
      )}
    </Modal>
  )
}
