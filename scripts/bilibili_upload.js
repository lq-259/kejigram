const puppeteer = require('/tmp/puprec/node_modules/puppeteer');
const fs = require('fs');
const path = require('path');

// === Configuration ===
const DATE = '2026-07-02';
const VIDEO = '/root/opencode/科技简报/dates/2026-07-02/video_2026-07-02.mp4';
const COVER = '/root/opencode/科技简报/dates/2026-07-02/cover_image.jpg';
const TITLE = '苹果邮件漏洞可暴露真实邮箱；阿里6亿美元和解美国调查；Meta出售AI算力引发韩股大跌';
const DESC = `2026年7月2日科技新闻简报

本期重点：
• 苹果"隐藏邮件地址"功能存在隐私漏洞，攻击者可暴露真实邮箱
• 阿里巴巴及支付服务商支付6亿美元与美国司法部和解
• Meta计划出售多余AI算力，引发韩国股市大跌
• 张雪峰退出公司股东，股份转给11岁女儿
• OnePlus欧洲收缩，引导用户转购Oppo
• Cloudflare将拦截部分AI爬虫，点名Google
• 北京通报轻型飞机撞楼事件
• 证监会同意宇树科技科创板IPO
• 美团7月起骑手职伤险全覆盖

来源链接见视频简介。
科技新闻 | 每日更新`;
const TAGS = ['科技新闻', '苹果', '阿里巴巴', 'Meta', 'AI', '每日简报', '宇树科技', '美团'];

// Connect to existing browser (should be running with remote debugging)
(async () => {
  console.log('[bili] Connecting to browser...');
  
  let browser;
  try {
    browser = await puppeteer.connect({
      browserURL: 'http://127.0.0.1:9223',
      defaultViewport: { width: 1440, height: 1100 }
    });
  } catch (e) {
    console.error('[bili] Cannot connect to browser. Please start Chromium with:');
    console.error('  chromium --remote-debugging-port=9223 &');
    process.exit(1);
  }
  
  const pages = await browser.pages();
  const page = pages[0];
  await page.setViewport({ width: 1440, height: 1100 });
  
  console.log('[bili] Navigating to upload page...');
  await page.goto('https://member.bilibili.com/platform/upload/video/frame', {
    waitUntil: 'domcontentloaded',
    timeout: 60000
  });
  await new Promise(r => setTimeout(r, 4000));
  
  // Check login
  console.log('[bili] Checking login status...');
  const nav = await page.evaluate(async () => {
    const r = await fetch('https://api.bilibili.com/x/web-interface/nav', { credentials: 'include' });
    const j = await r.json();
    return { isLogin: !!j.data?.isLogin, mid: j.data?.mid, uname: j.data?.uname };
  });
  
  if (!nav.isLogin) {
    console.error('[bili] Not logged in!');
    console.error('[bili] Please login manually in the browser first.');
    await browser.disconnect();
    process.exit(1);
  }
  
  console.log(`[bili] Logged in as: ${nav.uname} (mid: ${nav.mid})`);
  
  // Upload video
  console.log('[bili] Uploading video...');
  const fileInputs = await page.$$('input[type=file]');
  await fileInputs[0].uploadFile(VIDEO);
  
  // Wait for upload to complete (check for "分区" text)
  console.log('[bili] Waiting for upload...');
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const hasPartition = await page.evaluate(() => 
      document.body.innerText.includes('分区')
    );
    if (hasPartition) {
      console.log('[bili] Upload complete!');
      break;
    }
    process.stdout.write('.');
  }
  
  // Fill title
  console.log('[bili] Filling title...');
  const titleInput = await page.$('input[placeholder="请输入稿件标题"]');
  await titleInput.scrollIntoView({ block: 'center' });
  await new Promise(r => setTimeout(r, 300));
  await titleInput.click({ clickCount: 3 });
  await page.keyboard.type(TITLE, { delay: 5 });
  
  // Select "内容无需标注"
  console.log('[bili] Selecting declaration...');
  const declInput = await page.$('input[placeholder="请选择符合您视频内容的创作声明"]');
  await declInput.click();
  await new Promise(r => setTimeout(r, 800));
  await page.evaluate(() => {
    const option = Array.from(document.querySelectorAll('.bcc-option'))
      .find(e => e.innerText.trim() === '内容无需标注');
    if (option) option.click();
  });
  
  // Fill description
  console.log('[bili] Filling description...');
  await page.evaluate(desc => {
    const editor = Array.from(document.querySelectorAll('.ql-editor'))
      .find(e => e.offsetWidth || e.offsetHeight || e.getClientRects().length);
    if (editor) {
      editor.innerText = desc;
      editor.classList.remove('ql-blank');
      editor.dispatchEvent(new InputEvent('input', { bubbles: true }));
    }
  }, DESC);
  
  // Remove bad tags
  console.log('[bili] Cleaning tags...');
  const BAD = new Set(['娱乐', '二次元', '校园', '生活记录', '学习', '自用', '游戏', '教程攻略', '搞笑', '英雄联盟', '记录', '喵星人']);
  for (let i = 0; i < 5; i++) {
    const toRemove = await page.evaluate(bad => 
      Array.from(document.querySelectorAll('#tag-container .label-item-v2-container'))
        .map(e => {
          const text = e.querySelector('.label-item-v2-content')?.innerText?.trim();
          const close = e.querySelector('.close');
          const rect = close?.getBoundingClientRect();
          return text && bad.includes(text) && rect && rect.width 
            ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } 
            : null;
        }).filter(Boolean),
      Array.from(BAD));
    
    if (!toRemove.length) break;
    for (const item of toRemove) {
      await page.mouse.click(item.x, item.y);
      await new Promise(r => setTimeout(r, 500));
    }
  }
  
  // Add good tags
  console.log('[bili] Adding tags...');
  for (const tag of TAGS) {
    const tagInput = await page.$('input[placeholder="按回车键Enter创建标签"]');
    if (tagInput) {
      await tagInput.click({ clickCount: 3 });
      await page.keyboard.type(tag);
      await page.keyboard.press('Enter');
      await new Promise(r => setTimeout(r, 600));
    }
  }
  
  // Upload cover image
  console.log('[bili] Uploading cover...');
  // Look for cover upload area
  const coverInput = await page.evaluateHandle(() => {
    const inputs = Array.from(document.querySelectorAll('input[type=file]'));
    return inputs[1] || inputs[0]; // Usually second file input
  });
  if (coverInput) {
    await coverInput.uploadFile(COVER);
    await new Promise(r => setTimeout(r, 2000));
  }
  
  // Scroll to submit button
  console.log('[bili] Scrolling to submit...');
  await page.evaluate(() => {
    const btn = document.querySelector('.submit-add');
    if (btn) btn.scrollIntoView({ block: 'center' });
  });
  await new Promise(r => setTimeout(r, 500));
  
  // ===== STOP BEFORE PUBLISHING =====
  console.log('\n========================================');
  console.log('[bili] ✅ READY TO PUBLISH');
  console.log('[bili] ⏹️  STOPPED before clicking submit');
  console.log('========================================');
  console.log('[bili] Review the form in the browser.');
  console.log('[bili] If everything looks good, manually click:');
  console.log('        [立即投稿] button');
  console.log('[bili] Or run the following to auto-submit:');
  console.log('        await page.click(".submit-add")');
  console.log('========================================\n');
  
  // Keep browser open
  console.log('[bili] Browser will stay open for manual review.');
  console.log('[bili] Press Ctrl+C to close.');
  
  // Keep alive
  setInterval(() => {}, 1000);
  
})().catch(e => {
  console.error('[bili] Error:', e.stack || e);
  process.exit(1);
});
