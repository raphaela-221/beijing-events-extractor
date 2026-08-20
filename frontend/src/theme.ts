import type { ThemeConfig } from 'antd'

// 数值照抄 mockups/shared.css 的 :root 变量，不重新设计。
export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#4F46E5',
    colorSuccess: '#16A34A',
    colorWarning: '#D97706',
    colorError: '#DC2626',
    colorInfo: '#2563EB',
    borderRadius: 8,
    colorBgLayout: '#F5F6F8',
    fontSize: 14,
    colorText: '#1F2937',
    colorTextSecondary: '#6B7280',
    colorTextTertiary: '#9CA3AF',
    colorBorder: '#E5E7EB',
    colorBorderSecondary: '#F0F0F0',
    fontFamily:
      '"PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
  },
  components: {
    Layout: {
      siderBg: '#1E1B3A',
      headerBg: '#FFFFFF',
      headerHeight: 48,
      bodyBg: '#F5F6F8',
    },
    Menu: {
      darkItemBg: '#1E1B3A',
      darkSubMenuItemBg: '#1E1B3A',
      darkItemSelectedBg: 'rgba(255,255,255,0.08)',
      darkItemColor: '#C7C6E0',
      darkItemSelectedColor: '#fff',
    },
    Card: { headerBg: 'transparent' },
  },
}
