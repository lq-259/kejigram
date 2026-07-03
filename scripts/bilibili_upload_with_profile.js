const puppeteer = require('/tmp/puprec/node_modules/puppeteer');
const fs = require('fs');

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
• 美团7月起骑手职伤险全覆盖`;
const TAGS = ['科技新闻', '苹果', '阿里巴巴', 'Meta', 'AI', '每日简报'];

(async () => {
  console.log('[bili] Starting browser with saved profile...');
  
  const browser = await puppeteer.launch({
    headless: false,
    executablePath: '/usr/bin/chromium',
    userDataDir: '/tmp/bili_profile/account-b',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1440,1100'
    ],
    defaultViewport: { width: 1440, height: 1100 }
  });

  const page = await browser.newPage();
  
  console.log('[bili] Navigating to upload page...');
  await page.goto('https://member.bilibili.com/platform/upload/video/frame', {
    waitUntil: 'domcontentloaded',
    timeout: 60000
  });
  await new Promise(r => setTimeout(r, 4000));
  
  // Check if logged in
  const nav = await page.evaluate(async () => {
    try {
      const r = await fetch('https://api.bilibili.com/x/web-interface/nav', { credentials: 'include' });
      const j = await r.json();
      return { isLogin: !!j.data?.isLogin, mid: j.data?.mid, uname: j.data?.uname };
    } catch (e) {
      return { isLogin: false };
    }
  });
  
  if (!nav.isLogin) {
    console.error('[bili] Not logged in!');
    console.error('[bili] Please login manually in the browser.');
    console.error('[bili] Browser will stay open.');
    // Keep browser open
    return;
  }
  
  console.log(`[bili] Logged in as: ${nav.uname} (mid: ${nav.mid})`);
  
  // Upload video
  console.log('[bili] Uploading video...');
  const fileInputs = await page.$$('input[type=file]');
  await fileInputs[0].uploadFile(VIDEO);
  
  // Wait for upload
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
  
  // Add tags
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
  
  // Scroll to submit
  console.log('[bili] Scrolling to submit...');
  await page.evaluate(() => {
    const btn = document.querySelector('.submit-add');
    if (btn) btn.scrollIntoView({ block: 'center' });
  });
  await new Promise(r => setTimeout(r, 500));
  
  // Click submit
  console.log('[bili] Clicking submit...');
  const submitBtn = await page.$('.submit-add');
  if (submitBtn) {
    await submitBtn.click();
    console.log('[bili] Submit clicked!');
  } else {
    console.error('[bili] Submit button not found!');
  }
  
  // Wait for submission result
  console.log('[bili] Waiting for submission result...');
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 1500));
    const status = await page.evaluate(() => ({
      ok: /恭喜你上传第一个稿件|查看进度|再投一个|稿件投递成功/.test(document.body.innerText),
      risk: /验证码|短信验证|实名认证/.test(document.body.innerText),
      text: document.body.innerText.slice(0, 500)
    }));
    
    if (status.ok) {
      console.log('[bili] ✅ Upload successful!');
      break;
    }
    if (status.risk) {
      console.log('[bili] ⚠️ Risk control detected, needs manual intervention');
      break;
    }
  }
  
  console.log('[bili] Done!');
  await browser.close();
  
})().catch(e => {
  console.error('[bili] Error:', e.stack || e);
  process.exit(1);
});
