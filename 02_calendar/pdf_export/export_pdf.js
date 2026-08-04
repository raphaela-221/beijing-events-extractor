// 将 02_calendar 的 3 个 HTML 导出为「不分页」单页满高 PDF（用于做示例图）。
// 用系统 Chrome（不下载 chromium），puppeteer-core 本地依赖。
// 运行: node export_pdf.js
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const CAL_DIR = path.resolve(__dirname, '..'); // -> 02_calendar
const OUT_DIR = path.join(__dirname, 'output');

// timeline 是横向甘特图，.gantt/.g-scroll 会裁掉超宽时间轴；出 PDF 前先展开。
const UNFOLD_GANTT = `
  .gantt, .g-scroll { overflow: visible !important; }
  .g-track.scrolled { max-height: none !important; overflow: visible !important; }
`;

const PAGES = [
  { file: 'index.html',    out: '01_index.pdf',    width: 1280, unfold: false },
  { file: 'month.html',    out: '02_month.pdf',    width: 1280, unfold: false },
  { file: 'timeline.html', out: '03_timeline.pdf', width: 1280, unfold: true  },
];

async function renderPage(browser, p) {
  const page = await browser.newPage();
  await page.setViewport({ width: p.width, height: 900 });
  const url = 'file://' + path.join(CAL_DIR, p.file);
  console.log(`\nRendering ${p.file} ...`);
  await page.goto(url, { waitUntil: 'networkidle0', timeout: 60000 });
  // 等 JS 渲染 + CDN 字体/图标（Google Fonts + Phosphor）加载
  try { await page.evaluate(() => document.fonts.ready); } catch (e) { /* ignore */ }
  await new Promise(r => setTimeout(r, 2000));

  let pdfW = p.width;
  if (p.unfold) {
    await page.addStyleTag({ content: UNFOLD_GANTT });
    await new Promise(r => setTimeout(r, 600));
    // 量取甘特图完整宽度（axis/track 内联宽 = trackW，展开后 body scrollWidth 也应撑开）
    const measured = await page.evaluate(() => {
      const axis = document.querySelector('.g-axis');
      const track = document.querySelector('.g-track');
      const contentW = Math.max(axis ? axis.scrollWidth : 0, track ? track.scrollWidth : 0);
      const bodyW = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth);
      return Math.max(contentW, bodyW);
    });
    pdfW = Math.ceil(measured);
    // 把视口扩到满宽，让页头/工具栏按满宽布局，避免 PDF 右侧留白错位
    await page.setViewport({ width: pdfW, height: 900 });
    await new Promise(r => setTimeout(r, 800));
  }

  const dims = await page.evaluate(() => {
    const b = document.body;
    return {
      h: Math.max(document.documentElement.scrollHeight, b ? b.scrollHeight : 0, b ? b.offsetHeight : 0),
      w: Math.max(document.documentElement.scrollWidth, b ? b.scrollWidth : 0),
    };
  });
  const w = p.unfold ? Math.ceil(dims.w) : p.width;
  // +8px buffer 吸收底部 box-shadow/亚像素溢出，避免内容蹭到第 2 页
  const h = Math.ceil(dims.h) + 8;
  console.log(`  pdf size: ${w} x ${h} px`);

  // 出 PDF 前裁掉 html/body 溢出，确保单页
  await page.addStyleTag({ content: 'html,body{overflow:hidden!important;}' });
  await page.pdf({
    path: path.join(OUT_DIR, p.out),
    width: w + 'px',
    height: h + 'px',
    printBackground: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });
  const stat = fs.statSync(path.join(OUT_DIR, p.out));
  console.log(`  -> ${p.out}  (${(stat.size / 1024).toFixed(0)} KB)`);
  await page.close();
}

(async () => {
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });
  try {
    for (const p of PAGES) {
      await renderPage(browser, p);
    }
  } finally {
    await browser.close();
  }
  console.log('\nAll done. PDFs in: ' + OUT_DIR);
})().catch(e => { console.error('ERROR:', e); process.exit(1); });
