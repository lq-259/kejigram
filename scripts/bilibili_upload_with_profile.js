const puppeteer = require('/tmp/puprec/node_modules/puppeteer');
const fs = require('fs');
const path = require('path');

// Parse command line arguments
const args = process.argv.slice(2);
const STOP_BEFORE_PUBLISH = args.includes('--stop-before-publish') || args.includes('--dry-run');

// === Configuration ===
const PROJECT_ROOT = path.dirname(__dirname);
const PROFILE_DIR = path.join(PROJECT_ROOT, 'bili_profile', 'account-b');

// Check if profile exists
if (!fs.existsSync(PROFILE_DIR)) {
  console.error(`[bili] Profile not found: ${PROFILE_DIR}`);
  console.error('[bili] Please run once with --stop-before-publish to login manually,');
  console.error('       then the profile will be saved automatically.');
  process.exit(1);
}

const DATE = process.env.BILI_DATE || '2026-07-02';
const VIDEO = process.env.BILI_VIDEO || path.join(PROJECT_ROOT, 'dates', DATE, `video_${DATE}.mp4`);
const COVER = process.env.BILI_COVER || path.join(PROJECT_ROOT, 'dates', DATE, 'cover_image.jpg');
const TITLE = process.env.BILI_TITLE || '科技新闻简报';
const DESC = process.env.BILI_DESC || `科技新闻简报 ${DATE}`;
const TAGS = (process.env.BILI_TAGS || '科技新闻,AI,每日简报').split(',');

(async () => {
  console.log(`[bili] Using profile: ${PROFILE_DIR}`);
  console.log(`[bili] Stop before publish: ${STOP_BEFORE_PUBLISH}`);
  
  const browser = await puppeteer.launch({
    headless: false,
    executablePath: '/usr/bin/chromium',
    userDataDir: PROFILE_DIR,
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
  console.log('[bili] Checking login status...');
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
    if (STOP_BEFORE_PUBLISH) {
      console.log('[bili] After login, close browser and profile will be saved.');
    }
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
  
  if (STOP_BEFORE_PUBLISH) {
    console.log('\n========================================');
    console.log('[bili] ✅ READY TO PUBLISH');
    console.log('[bili] ⏹️  STOPPED before clicking submit');
    console.log('========================================');
    console.log('[bili] Review the form in the browser.');
    console.log('[bili] If everything looks good, manually click:');
    console.log('        [立即投稿] button');
    console.log('[bili] Browser will stay open.');
    console.log('========================================\n');
    return;
  }
  
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
