import type { DiffSummary as DiffData } from '../../api/canonical'

// 差异摘要：+新增/-删除/~修改 芯片 + 明细表（变化/No./Headline/字段/改动）。
export function DiffSummary({ diff }: { diff: DiffData }) {
  const empty = diff.added === 0 && diff.deleted === 0 && diff.modified === 0
  if (empty) {
    return <div className="page-sub">无差异（上传文件与当前清单一致）</div>
  }
  return (
    <>
      <div className="diff-summary">
        <div className="diff-chip add"><span className="n">+{diff.added}</span>新增</div>
        <div className="diff-chip del"><span className="n">-{diff.deleted}</span>删除</div>
        <div className="diff-chip mod"><span className="n">~{diff.modified}</span>修改</div>
      </div>
      <div className="table-wrap" style={{ maxHeight: 280 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>变化</th>
              <th>No.</th>
              <th>Headline</th>
              <th>字段</th>
              <th>改动</th>
            </tr>
          </thead>
          <tbody>
            {diff.items.slice(0, 50).map((it, i) => (
              <tr key={i}>
                <td>
                  <span className={`badge ${it.type === 'add' ? 'success' : it.type === 'del' ? 'error' : 'warn'}`}>
                    {it.type === 'add' ? '新增' : it.type === 'del' ? '删除' : '修改'}
                  </span>
                </td>
                <td>{it.no}</td>
                <td>{it.headline}</td>
                <td>{it.field}</td>
                <td>{it.change}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {diff.items.length > 50 && (
        <div className="page-sub" style={{ margin: '8px 0' }}>
          显示 50 / {diff.items.length} 条改动
        </div>
      )}
    </>
  )
}
