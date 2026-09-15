import { useState, useEffect, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { App as AntdApp, Button, Card, Input, InputNumber, Modal, Popconfirm, Select, Spin, Table, Tag, Typography } from 'antd'
import { settingsApi, type SelfcheckResult, type Settings } from '../api/settings'
import { authApi, type Account } from '../api/auth'
import { useAuthStore } from '../stores/useAuthStore'
import { fmtBytes, fmtDateTime } from '../utils/format'

const CHECK_LABEL: Record<string, string> = {
  env_keys: 'LLM Key',
  canonical_exists: 'Canonical 存在',
  canonical_structure: 'Canonical 结构',
  dates_pending: '演唱会 Dates',
  data_freshness: '日历数据新鲜度',
  changed_months: '待重算月份',
  concert_state: '演唱会采集',
  disk_space: '磁盘空间',
}

export function Settings() {
  const isAdmin = useAuthStore((s) => s.user)?.role === 'admin'
  const qc = useQueryClient()
  const { message } = AntdApp.useApp()
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })
  const [retention, setRetention] = useState<number | null>(null)
  const [bakKeep, setBakKeep] = useState<number | null>(null)
  const [scResult, setScResult] = useState<SelfcheckResult | null>(null)

  const selfcheckMut = useMutation({
    mutationFn: settingsApi.selfcheck,
    onSuccess: (r) => {
      setScResult(r)
      qc.invalidateQueries({ queryKey: ['settings'] })
      message.success(
        r.ok ? `自检通过（${r.warn_count} 项警告）` : `自检发现 ${r.block_count} 项阻断、${r.warn_count} 项警告`
      )
    },
    onError: (e) => message.error((e as Error).message),
  })
  const cleanupMut = useMutation({
    mutationFn: settingsApi.cleanup,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      message.success(
        `已清理：回收站 ${r.purged_runs} 条 · .bak ${r.deleted_baks} 个 · 孤儿目录 ${r.orphans} 个 · 释放 ${fmtBytes(r.freed_bytes)}`
      )
    },
    onError: (e) => message.error((e as Error).message),
  })
  const saveMut = useMutation({
    mutationFn: settingsApi.update,
    onSuccess: () => {
      setRetention(null)
      setBakKeep(null)
      qc.invalidateQueries({ queryKey: ['settings'] })
      message.success('已保存')
    },
    onError: (e) => message.error((e as Error).message),
  })

  if (isLoading || !data) return <Spin style={{ display: 'block', padding: 60 }} />

  const sc = scResult || data.last_selfcheck
  const cl = data.last_cleanup
  const dirty = retention != null || bakKeep != null

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">设置</div>
          <div className="page-sub">运行配置、流程自检与自动清理。自检/清理/改规则仅管理员可操作。</div>
        </div>
      </div>

      {!isAdmin && (
        <div className="banner info" style={{ marginBottom: 14 }}>
          <span className="ic">🔒</span>
          <div>当前为操作员账号，仅可查看。自检、清理、修改规则需管理员登录。</div>
        </div>
      )}

      <Card
        title="流程自检"
        style={{ marginBottom: 16 }}
        extra={
          <Button disabled={!isAdmin} loading={selfcheckMut.isPending} onClick={() => selfcheckMut.mutate()}>
            立即自检
          </Button>
        }
      >
        <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
          {data.last_selfcheck
            ? `上次自检 ${fmtDateTime(data.last_selfcheck.at)}`
            : '尚未自检（启动 60 秒后自动首次自检）'}
          {data.last_selfcheck && (
            <Tag
              color={data.last_selfcheck.ok ? 'green' : data.last_selfcheck.block_count ? 'red' : 'orange'}
              style={{ marginLeft: 10 }}
            >
              {data.last_selfcheck.ok
                ? `通过 · ${data.last_selfcheck.warn_count} 警告`
                : `${data.last_selfcheck.block_count} 阻断 · ${data.last_selfcheck.warn_count} 警告`}
            </Tag>
          )}
        </Typography.Text>
        <div style={{ marginTop: 12 }}>
          {sc && 'checks' in sc && (sc as SelfcheckResult).checks ? (
            <div style={{ border: '1px solid #F0F0F0', borderRadius: 6, overflow: 'hidden' }}>
              {(sc as SelfcheckResult).checks.map((c) => (
                <div
                  key={c.id}
                  style={{
                    display: 'flex',
                    gap: 10,
                    padding: '7px 12px',
                    borderBottom: '1px solid #F5F5F5',
                    fontSize: 12.5,
                    alignItems: 'center',
                  }}
                >
                  <span style={{ flex: '0 0 130px', color: '#6B7280' }}>
                    {CHECK_LABEL[c.id] || c.id}
                  </span>
                  <Tag
                    color={c.status === 'ok' ? 'green' : c.status === 'warn' ? 'orange' : 'red'}
                    style={{ margin: 0 }}
                  >
                    {c.status === 'ok' ? '正常' : c.status === 'warn' ? '警告' : '阻断'}
                  </Tag>
                  <span style={{ color: '#374151' }}>{c.detail}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#9CA3AF' }}>
              点击「立即自检」查看 8 项检查详情（LLM Key / Canonical / Dates / 日历新鲜度 / 磁盘等）。
            </div>
          )}
        </div>
      </Card>

      <Card
        title="自动清理"
        style={{ marginBottom: 16 }}
        extra={
          <Popconfirm
            title="立即清理？"
            description={`将清理：回收站超 ${data.retention_days} 天记录 · .bak 删至 ${data.canonical_bak_keep} 份 · 孤儿 run 目录。`}
            okText="清理"
            cancelText="取消"
            disabled={!isAdmin}
            onConfirm={() => cleanupMut.mutate()}
          >
            <Button disabled={!isAdmin} loading={cleanupMut.isPending}>
              立即清理
            </Button>
          </Popconfirm>
        }
      >
        <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
          每日 03:00 自动执行：回收站超 {data.retention_days} 天 purge · .bak 保留{' '}
          {data.canonical_bak_keep} 份（超出删最旧）· 孤儿 run 目录清理。.bak 永不因 run 删除而动。
        </Typography.Text>
        {cl ? (
          <div
            style={{
              marginTop: 10,
              padding: 12,
              background: '#FAFAFC',
              borderRadius: 6,
              border: '1px solid #F0F0F0',
              fontSize: 13,
            }}
          >
            上次清理 {fmtDateTime(cl.at)}：回收站 purge {cl.purged_runs} 条 · .bak 删{' '}
            {cl.deleted_baks} 个 · 孤儿目录 {cl.orphans} 个 · 释放 {fmtBytes(cl.freed_bytes)}
          </div>
        ) : (
          <div style={{ marginTop: 10, fontSize: 13, color: '#9CA3AF' }}>
            尚未执行清理（下次 03:00 自动执行，或点「立即清理」）
          </div>
        )}
      </Card>

      <Card title="清理规则" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <div style={{ fontSize: 12.5, color: '#6B7280', marginBottom: 6 }}>
              回收站保留天数（超期自动 purge）
            </div>
            <InputNumber
              min={1}
              max={365}
              value={retention ?? data.retention_days}
              onChange={(v) => setRetention(v)}
              disabled={!isAdmin}
            />
          </div>
          <div>
            <div style={{ fontSize: 12.5, color: '#6B7280', marginBottom: 6 }}>
              canonical .bak 保留份数（超出删最旧）
            </div>
            <InputNumber
              min={1}
              max={100}
              value={bakKeep ?? data.canonical_bak_keep}
              onChange={(v) => setBakKeep(v)}
              disabled={!isAdmin}
            />
          </div>
          <Button
            type="primary"
            disabled={!isAdmin || !dirty}
            loading={saveMut.isPending}
            onClick={() => {
              const body: { retention_days?: number; canonical_bak_keep?: number } = {}
              if (retention != null) body.retention_days = retention
              if (bakKeep != null) body.canonical_bak_keep = bakKeep
              saveMut.mutate(body)
            }}
          >
            保存
          </Button>
        </div>
      </Card>

      <Card title="数据统计">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
          <Stat k="活跃运行记录" v={data.data_stats.runs_count} />
          <Stat k="回收站" v={data.data_stats.trash_count} />
          <Stat k=".bak 备份份数" v={data.data_stats.bak_count} />
          <Stat k="data 目录" v={fmtBytes(data.data_stats.data_size)} />
          <Stat k="数据库" v={fmtBytes(data.data_stats.db_size)} />
          <Stat k="磁盘可用" v={fmtBytes(data.data_stats.free_space)} />
        </div>
      </Card>

      <ChangePasswordCard />
      <UsersCard isAdmin={isAdmin} />
      <KeysCard isAdmin={isAdmin} />
    </div>
  )
}

function Stat({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div style={{ border: '1px solid #F0F0F0', borderRadius: 6, padding: '12px 14px', background: '#FAFAFC' }}>
      <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 6 }}>{k}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: '#1F2937' }}>{v}</div>
    </div>
  )
}

function KeysCard({ isAdmin }: { isAdmin: boolean }) {
  const qc = useQueryClient()
  const { message } = AntdApp.useApp()
  const { data: keys, isLoading } = useQuery({
    queryKey: ['settings-keys'],
    queryFn: settingsApi.getKeys,
  })
  const [dsKey, setDsKey] = useState('')
  const [arkKey, setArkKey] = useState('')
  const [mlampKey, setMlampKey] = useState('')
  const [dsBaseUrl, setDsBaseUrl] = useState('')
  const [dsModel, setDsModel] = useState('')
  const [arkBaseUrl, setArkBaseUrl] = useState('')
  const [arkModel, setArkModel] = useState('')
  const [mlampBaseUrl, setMlampBaseUrl] = useState('')
  const [mlampModel, setMlampModel] = useState('')

  useEffect(() => {
    if (keys) {
      setDsBaseUrl(keys.deepseek.base_url)
      setDsModel(keys.deepseek.model)
      setArkBaseUrl(keys.ark.base_url)
      setArkModel(keys.ark.model)
      setMlampBaseUrl(keys.mlamp.base_url)
      setMlampModel(keys.mlamp.model)
    }
  }, [keys])

  const saveMut = useMutation({
    mutationFn: settingsApi.updateKeys,
    onSuccess: () => {
      setDsKey('')
      setArkKey('')
      setMlampKey('')
      qc.invalidateQueries({ queryKey: ['settings-keys'] })
      message.success('已保存，立即生效（注入环境变量，无需重启）')
    },
    onError: (e) => message.error((e as Error).message),
  })

  if (isLoading || !keys) return <Card title="LLM Key 配置" style={{ marginTop: 16 }}><Spin /></Card>

  const onSave = () => {
    const body: {
      deepseek?: { key?: string; base_url?: string; model?: string }
      ark?: { key?: string; base_url?: string; model?: string }
      mlamp?: { key?: string; base_url?: string; model?: string }
    } = {}
    const ds: { key?: string; base_url?: string; model?: string } = {}
    if (dsKey) ds.key = dsKey
    if (dsBaseUrl !== keys.deepseek.base_url) ds.base_url = dsBaseUrl
    if (dsModel !== keys.deepseek.model) ds.model = dsModel
    if (Object.keys(ds).length) body.deepseek = ds
    const ark: { key?: string; base_url?: string; model?: string } = {}
    if (arkKey) ark.key = arkKey
    if (arkBaseUrl !== keys.ark.base_url) ark.base_url = arkBaseUrl
    if (arkModel !== keys.ark.model) ark.model = arkModel
    if (Object.keys(ark).length) body.ark = ark
    const mlamp: { key?: string; base_url?: string; model?: string } = {}
    if (mlampKey) mlamp.key = mlampKey
    if (mlampBaseUrl !== keys.mlamp.base_url) mlamp.base_url = mlampBaseUrl
    if (mlampModel !== keys.mlamp.model) mlamp.model = mlampModel
    if (Object.keys(mlamp).length) body.mlamp = mlamp
    if (!Object.keys(body).length) {
      message.info('无改动')
      return
    }
    saveMut.mutate(body)
  }

  return (
    <Card title="LLM Key 配置" style={{ marginTop: 16 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        抽取用三套兜底：DeepSeek（主）+ Ark（兜底）+ mlamp（终极兜底），失败自动逐级切换。
        key 保存到 <span className="mono">config/llm_keys.json</span>（gitignored），注入环境变量立即生效，不碰 .env。Key 留空=不改。
      </Typography.Text>

      <ProviderBlock
        title="DeepSeek（主 · 直连）"
        isAdmin={isAdmin}
        keyVal={dsKey}
        setKey={setDsKey}
        masked={keys.deepseek.masked}
        configured={keys.deepseek.configured}
        baseUrl={dsBaseUrl}
        setBaseUrl={setDsBaseUrl}
        model={dsModel}
        setModel={setDsModel}
      />
      <ProviderBlock
        title="Ark 火山引擎（兜底 · Agent Plan）"
        isAdmin={isAdmin}
        keyVal={arkKey}
        setKey={setArkKey}
        masked={keys.ark.masked}
        configured={keys.ark.configured}
        baseUrl={arkBaseUrl}
        setBaseUrl={setArkBaseUrl}
        model={arkModel}
        setModel={setArkModel}
      />
      <ProviderBlock
        title="mlamp 明略网关（终极兜底 · OpenAI 兼容）"
        isAdmin={isAdmin}
        keyVal={mlampKey}
        setKey={setMlampKey}
        masked={keys.mlamp.masked}
        configured={keys.mlamp.configured}
        baseUrl={mlampBaseUrl}
        setBaseUrl={setMlampBaseUrl}
        model={mlampModel}
        setModel={setMlampModel}
      />

      <div style={{ marginTop: 16, padding: 14, border: '1px solid #F0F0F0', borderRadius: 6, background: '#FAFAFC' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <Typography.Text style={{ fontSize: 13, fontWeight: 600 }}>Qwen 月度总结</Typography.Text>
          <Tag color={keys.qwen.enabled ? 'green' : 'default'}>
            {keys.qwen.enabled ? '✅ 已开启' : '❌ 未开启'}
          </Tag>
        </div>
        <div style={{ fontSize: 12.5, color: '#6B7280' }}>
          {keys.qwen.reason}。走公司内部端点（pomp.ubrmbqa.com），免 key；无自动 backup（Qwen 失败该月主题失败）。
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <Button type="primary" disabled={!isAdmin} loading={saveMut.isPending} onClick={onSave}>
          保存
        </Button>
      </div>
    </Card>
  )
}

function ProviderBlock({
  title,
  isAdmin,
  keyVal,
  setKey,
  masked,
  configured,
  baseUrl,
  setBaseUrl,
  model,
  setModel,
}: {
  title: string
  isAdmin: boolean
  keyVal: string
  setKey: (v: string) => void
  masked: string
  configured: boolean
  baseUrl: string
  setBaseUrl: (v: string) => void
  model: string
  setModel: (v: string) => void
}) {
  return (
    <div
      style={{
        marginTop: 16,
        padding: 14,
        border: '1px solid #F0F0F0',
        borderRadius: 6,
        background: '#FAFAFC',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <Typography.Text style={{ fontSize: 13, fontWeight: 600 }}>{title}</Typography.Text>
        {configured ? <Tag color="green">已配置 · {masked}</Tag> : <Tag color="default">未配置</Tag>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>API Key（留空不改）</div>
          <Input.Password
            value={keyVal}
            onChange={(e) => setKey(e.target.value)}
            placeholder={configured ? `已配置 · ${masked}，输入新值替换` : '输入 API Key'}
            disabled={!isAdmin}
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>Base URL</div>
          <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} disabled={!isAdmin} />
        </div>
        <div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>Model</div>
          <Input value={model} onChange={(e) => setModel(e.target.value)} disabled={!isAdmin} />
        </div>
      </div>
    </div>
  )
}

function ChangePasswordCard() {
  const nav = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const { message } = AntdApp.useApp()
  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const mut = useMutation({
    mutationFn: () => authApi.changePassword(oldPw, newPw),
    onSuccess: async () => {
      message.success('密码已修改，请用新密码重新登录')
      setOldPw('')
      setNewPw('')
      setConfirmPw('')
      await logout()
      nav('/login', { replace: true })
    },
    onError: (e) => message.error((e as Error).message),
  })
  const canSubmit = !!oldPw && newPw.length >= 6 && newPw === confirmPw
  return (
    <Card title="修改密码" style={{ marginTop: 16 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        修改当前账号密码。新密码至少 6 位。改成功后需用新密码重新登录。
      </Typography.Text>
      <div style={{ display: 'grid', gap: 12, marginTop: 14, maxWidth: 420 }}>
        <div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>旧密码</div>
          <Input.Password value={oldPw} onChange={(e) => setOldPw(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>新密码（至少 6 位）</div>
          <Input.Password value={newPw} onChange={(e) => setNewPw(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>确认新密码</div>
          <Input.Password value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} />
        </div>
        {confirmPw && newPw !== confirmPw && (
          <div style={{ fontSize: 12, color: '#EF4444' }}>两次输入的新密码不一致</div>
        )}
        <div>
          <Button type="primary" disabled={!canSubmit} loading={mut.isPending} onClick={() => mut.mutate()}>
            修改密码
          </Button>
        </div>
      </div>
    </Card>
  )
}

function UsersCard({ isAdmin }: { isAdmin: boolean }) {
  const qc = useQueryClient()
  const { message } = AntdApp.useApp()
  const { data, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: authApi.listUsers,
    enabled: isAdmin,
  })
  const [createOpen, setCreateOpen] = useState(false)
  const [resetTarget, setResetTarget] = useState<Account | null>(null)
  const [cUsername, setCUsername] = useState('')
  const [cPassword, setCPassword] = useState('')
  const [cDisplay, setCDisplay] = useState('')
  const [cRole, setCRole] = useState<'admin' | 'operator'>('operator')
  const [rPassword, setRPassword] = useState('')

  const createMut = useMutation({
    mutationFn: () =>
      authApi.createUser({
        username: cUsername.trim(),
        password: cPassword,
        display_name: cDisplay.trim() || undefined,
        role: cRole,
      }),
    onSuccess: () => {
      message.success(`已创建 ${cUsername.trim()}`)
      setCreateOpen(false)
      setCUsername('')
      setCPassword('')
      setCDisplay('')
      setCRole('operator')
      qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => message.error((e as Error).message),
  })
  const resetMut = useMutation({
    mutationFn: () => authApi.updateUser(resetTarget!.username, { password: rPassword }),
    onSuccess: () => {
      message.success(`已重置 ${resetTarget!.username} 的密码`)
      setResetTarget(null)
      setRPassword('')
      qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => message.error((e as Error).message),
  })
  const roleMut = useMutation({
    mutationFn: (args: { username: string; role: 'admin' | 'operator' }) =>
      authApi.updateUser(args.username, { role: args.role }),
    onSuccess: () => {
      message.success('已更新角色')
      qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => message.error((e as Error).message),
  })

  if (!isAdmin) return null
  return (
    <Card
      title="账号管理"
      style={{ marginTop: 16 }}
      extra={
        <Button onClick={() => setCreateOpen(true)}>新增账号</Button>
      }
    >
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        管理员可见。新增账号默认 operator 角色。暂不支持删除账号（避免误删管理员）。
      </Typography.Text>
      {isLoading ? (
        <Spin style={{ display: 'block', padding: 20 }} />
      ) : (
        <Table<Account>
          size="small"
          style={{ marginTop: 14 }}
          rowKey="username"
          dataSource={data?.items || []}
          pagination={false}
          columns={[
            { title: '用户名', dataIndex: 'username', key: 'username' },
            { title: '显示名', dataIndex: 'display_name', key: 'display_name' },
            {
              title: '角色',
              dataIndex: 'role',
              key: 'role',
              width: 140,
              render: (role: any, rec: Account) => (
                <Select
                  size="small"
                  value={role}
                  style={{ width: 110 }}
                  onChange={(v) => roleMut.mutate({ username: rec.username, role: v as 'admin' | 'operator' })}
                  options={[
                    { value: 'admin', label: '管理员' },
                    { value: 'operator', label: '操作员' },
                  ]}
                />
              ),
            },
            {
              title: '操作',
              key: 'op',
              width: 120,
              render: (_: any, rec: Account) => (
                <Button
                  size="small"
                  onClick={() => {
                    setResetTarget(rec)
                    setRPassword('')
                  }}
                >
                  重置密码
                </Button>
              ),
            },
          ]}
        />
      )}

      <Modal
        title="新增账号"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createMut.mutate()}
        okText="创建"
        cancelText="取消"
        okButtonProps={{ disabled: !cUsername.trim() || cPassword.length < 6, loading: createMut.isPending }}
      >
        <div style={{ display: 'grid', gap: 12, padding: '8px 0' }}>
          <div>
            <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>用户名</div>
            <Input value={cUsername} onChange={(e) => setCUsername(e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>密码（至少 6 位）</div>
            <Input.Password value={cPassword} onChange={(e) => setCPassword(e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>显示名（可选）</div>
            <Input value={cDisplay} onChange={(e) => setCDisplay(e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>角色</div>
            <Select
              value={cRole}
              onChange={(v) => setCRole(v as 'admin' | 'operator')}
              style={{ width: '100%' }}
              options={[
                { value: 'admin', label: '管理员' },
                { value: 'operator', label: '操作员' },
              ]}
            />
          </div>
        </div>
      </Modal>

      <Modal
        title={`重置 ${resetTarget?.username} 的密码`}
        open={!!resetTarget}
        onCancel={() => setResetTarget(null)}
        onOk={() => resetMut.mutate()}
        okText="重置"
        cancelText="取消"
        okButtonProps={{ disabled: rPassword.length < 6, loading: resetMut.isPending }}
      >
        <div style={{ padding: '8px 0' }}>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>新密码（至少 6 位）</div>
          <Input.Password value={rPassword} onChange={(e) => setRPassword(e.target.value)} />
        </div>
      </Modal>
    </Card>
  )
}
