import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntdApp, Modal, Input } from 'antd'
import { publishApi } from '../api/publish'

const PREVIEW_TABS = [
  { id: 'index', label: '总览页', path: '/preview/index.html' },
  { id: 'month', label: '月历页', path: '/preview/month.html' },
  { id: 'timeline', label: '时间轴页', path: '/preview/timeline.html' },
] as const

type TabId = (typeof PREVIEW_TABS)[number]['id']

export function Publish() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { message } = AntdApp.useApp()
  const [tab, setTab] = useState<TabId>('index')
  const [makingZip, setMakingZip] = useState(false)
  const [markModal, setMarkModal] = useState(false)
  const [note, setNote] = useState('')
  const [pathModal, setPathModal] = useState(false)
  const [pathVal, setPathVal] = useState('')
  const [savingPath, setSavingPath] = useState(false)

  const { data: state } = useQuery({ queryKey: ['publish-state'], queryFn: publishApi.state })
  const { data: history } = useQuery({ queryKey: ['publish-history'], queryFn: publishApi.history })

  const previewUrl = state ? `${window.location.origin}${state.preview_path}` : ''
  const externalUrl = state?.external_url || ''
  const externalIsSelf = state?.external_url_source === 'self'
  const platformUrl = state?.platform_upload_url || ''
  const canonicalOk = state?.canonical_ok ?? true
  const latestZip = state?.latest_zip ?? null
  const hasZip = !!latestZip

  const copy = async (text: string) => {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      message.success('已复制')
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }

  const makeZip = async () => {
    setMakingZip(true)
    try {
      await publishApi.zip()
      await qc.invalidateQueries({ queryKey: ['publish-state'] })
      message.success('zip 已生成')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setMakingZip(false)
    }
  }

  const openMark = () => {
    setNote('')
    setMarkModal(true)
  }

  const openPathModal = () => {
    setPathVal(state?.share_path || '')
    setPathModal(true)
  }

  const savePath = async () => {
    setSavingPath(true)
    try {
      await publishApi.setSharePath(pathVal)
      await qc.invalidateQueries({ queryKey: ['publish-state'] })
      message.success('路径已更新（立即生效，旧链接即刻失效）')
      setPathModal(false)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSavingPath(false)
    }
  }

  const confirmMark = async () => {
    try {
      await publishApi.markDone({ zip_name: latestZip?.name, note: note || undefined })
      await qc.invalidateQueries({ queryKey: ['publish-history'] })
      message.success('已记录到发布历史')
      setMarkModal(false)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">预览与发布</div>
          <div className="page-sub">发布前先在内置预览核对，确认无误后推送更新到对外日历</div>
        </div>
        <button className="btn ghost sm" onClick={() => nav('/dashboard')}>← 返回总览</button>
      </div>

      {/* 链接 */}
      <div className="card">
        <div className="card-title">链接</div>
        <div className="field-row">
          <label>内置预览 URL（操作台内托管，用于发布前核对）</label>
          <div className="copy-field">
            <span className="path">{previewUrl || '加载中…'}</span>
            <button className="btn ghost sm" onClick={() => copy(previewUrl)} disabled={!previewUrl}>复制</button>
            <button className="btn ghost sm" onClick={() => state && window.open(state.preview_path, '_blank')} disabled={!state}>在浏览器打开</button>
          </div>
        </div>
        <div className="field-row" style={{ marginBottom: 0 }}>
          <label>
            对外分享 URL
            {externalIsSelf ? '（本机托管直链，免登录可访问）' : '（项目管理平台，固定不变）'}
          </label>
          <div className="copy-field">
            <span className="path">{externalUrl || '未配置（在 .env 设 EXTERNAL_SHARE_URL）'}</span>
            <button className="btn ghost sm" onClick={() => copy(externalUrl)} disabled={!externalUrl}>复制</button>
            <button className="btn ghost sm" onClick={() => window.open(externalUrl, '_blank')} disabled={!externalUrl}>在浏览器打开</button>
            {externalIsSelf && <button className="btn ghost sm" onClick={openPathModal}>改路径名</button>}
          </div>
        </div>
      </div>

      {/* 预览 */}
      <div className="card">
        <div className="card-title" style={{ display: 'flex', alignItems: 'center' }}>
          预览
          <span className="pill-tabs" style={{ marginLeft: 'auto' }}>
            {PREVIEW_TABS.map((t) => (
              <span
                key={t.id}
                className={`pill${tab === t.id ? ' active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </span>
            ))}
          </span>
        </div>
        <div className="browser-frame">
          <div className="browser-bar">
            <div className="dots"><span></span><span></span><span></span></div>
            <div className="url">{PREVIEW_TABS.find((t) => t.id === tab)!.path}</div>
          </div>
          <div className="browser-body">
            <iframe
              key={tab}
              src={PREVIEW_TABS.find((t) => t.id === tab)!.path}
              style={{ width: '100%', height: 480, border: 'none', display: 'block' }}
              title="日历预览"
            />
          </div>
        </div>
      </div>

      {/* 发布 */}
      <div className="card">
        <div className="card-title">发布到对外日历 <span className="hint">v1 手动上传</span></div>
        {!canonicalOk && (
          <div className="banner danger" style={{ marginBottom: 12 }}>
            <span className="ic">⚠</span>
            <div>
              <b>canonical 结构损坏，发布已阻断</b>。请先到人工核对页修复（用 .bak 恢复或重新生成），再生成 zip。
            </div>
          </div>
        )}
        <div className="publish-steps">
          <div className="publish-step">
            <div className="ps-num">1</div>
            <div className="ps-body">
              生成发布 zip
              <div className="ps-desc">
                打包 02_web_output/ 下全部文件{latestZip ? `（当前：${latestZip.name} · ${(latestZip.size_bytes / 1024).toFixed(0)} KB）` : ''}
              </div>
            </div>
            <button
              className="btn primary sm"
              onClick={makeZip}
              disabled={!canonicalOk || makingZip}
            >
              {makingZip ? '生成中…' : '生成 zip'}
            </button>
          </div>

          <div className="publish-step">
            <div className="ps-num">2</div>
            <div className="ps-body">
              下载 zip 并上传到项目管理平台
              <div className="ps-desc">替换原文件，对外 URL 不变</div>
            </div>
            {hasZip ? (
              <a className="btn ghost sm" href={publishApi.downloadUrl(latestZip!.name)} download>
                ↓ 下载 zip
              </a>
            ) : (
              <button className="btn ghost sm" disabled>↓ 下载 zip</button>
            )}
          </div>

          <div className="publish-step">
            <div className="ps-num">3</div>
            <div className="ps-body">
              打开平台上传页
              <div className="ps-desc">在新标签页打开项目管理平台对应项目{platformUrl ? '' : '（未配置 PLATFORM_UPLOAD_URL）'}</div>
            </div>
            <button
              className="btn ghost sm"
              onClick={() => window.open(platformUrl, '_blank')}
              disabled={!hasZip || !platformUrl}
            >
              打开平台上传页
            </button>
          </div>

          <div className="publish-step">
            <div className="ps-num">4</div>
            <div className="ps-body">
              确认已在平台完成上传后
              <div className="ps-desc">标记本次发布完成，记录进发布历史</div>
            </div>
            <button className="btn ghost sm" onClick={openMark} disabled={!hasZip}>
              标记已发布
            </button>
          </div>
        </div>
      </div>

      {/* 发布历史 */}
      <div className="card">
        <div className="card-title">发布历史</div>
        <table className="data-table history-table">
          <thead>
            <tr><th>时间</th><th>操作人</th><th>备注</th></tr>
          </thead>
          <tbody>
            {history && history.length > 0 ? (
              history.map((h) => (
                <tr key={h.publish_id}>
                  <td>{h.created_at}</td>
                  <td>{h.operator}</td>
                  <td>{h.note || '-'}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3} style={{ textAlign: 'center', color: '#9CA3AF' }}>暂无发布记录</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal title="标记已发布" open={markModal} onOk={confirmMark} onCancel={() => setMarkModal(false)} okText="确认记录" cancelText="取消">
        <div style={{ marginBottom: 8, fontSize: 12.5, color: '#6B7280' }}>
          确认已在项目管理平台完成上传后，记录本次发布（可选填备注）：
        </div>
        <Input.TextArea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="如：常规月度更新"
          rows={3}
        />
      </Modal>

      <Modal
        title="修改对外分享路径名"
        open={pathModal}
        onOk={savePath}
        onCancel={() => setPathModal(false)}
        okText="保存"
        cancelText="取消"
        confirmLoading={savingPath}
      >
        <div style={{ marginBottom: 8, fontSize: 12.5, color: '#6B7280' }}>
          只能含字母/数字/短横线（1-64 位，开头须为字母或数字）。清空 = 恢复默认
          beijing-events-calendar；填 - 关闭别名（回退 /preview 直链）。
          保存后立即生效，<b>旧链接马上失效</b>，请通知已拿到旧链接的同事。
        </div>
        <Input
          value={pathVal}
          onChange={(e) => setPathVal(e.target.value)}
          placeholder="beijing-events-calendar"
          maxLength={64}
        />
      </Modal>
    </div>
  )
}
