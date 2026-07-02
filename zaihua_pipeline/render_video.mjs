#!/usr/bin/env node
/**
 * Stage 2: Render video from HTML + Audio + SRT
 * 
 * Core fix: Instead of relying on audio timeupdate events (which are unreliable
 * at 15fps screenshot rate), we directly set the active slide before EACH frame.
 * 
 * This guarantees that every screenshot shows the correct slide.
 */

import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const puppeteer = require('/tmp/puprec/node_modules/puppeteer');
import { spawnSync } from 'child_process';
import { readFileSync, writeFileSync, mkdirSync, rmSync, statSync } from 'fs';

// Parse args
const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  args[process.argv[i]] = process.argv[i + 1];
}
const HTML = args['--html'] || process.argv[2];
const AUDIO = args['--audio'] || process.argv[3];
const PLAN = args['--plan'] || '';
const SRT = args['--srt'] || process.argv[4];
const OUT = args['--out'] || process.argv[5];

console.log('Args:', { HTML, AUDIO, PLAN, SRT, OUT });

// Parse plan JSON for slide timings
let planSlides = [];
let totalDuration = 0;
if (PLAN) {
  try {
    const plan = JSON.parse(readFileSync(PLAN, 'utf-8'));
    planSlides = plan.slides || [];
    totalDuration = plan.total_duration || 0;
  } catch (e) {
    console.warn('Warning: Could not parse plan file, using empty plan:', e.message);
  }
}
console.log(`Plan: ${planSlides.length} slides, ${totalDuration}s total`);

// Parse SRT (for captions)
function parseSrt(txt) {
  const items = [];
  for (const block of txt.replace(/\r/g, '').trim().split(/\n\n+/)) {
    const lines = block.split('\n');
    const m = lines.find(l => l.includes('-->'));
    if (!m) continue;
    const re = /(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)/;
    const mt = m.match(re);
    if (!mt) continue;
    const start = (+mt[1])*3600 + (+mt[2])*60 + (+mt[3]) + (+mt[4])/1000;
    const end   = (+mt[5])*3600 + (+mt[6])*60 + (+mt[7]) + (+mt[8])/1000;
    const text = lines.slice(lines.indexOf(m)+1).join(' ').trim();
    items.push({ start, end, text });
  }
  return items;
}

const srtItems = SRT ? parseSrt(readFileSync(SRT, 'utf-8')) : [];
console.log(`SRT: ${srtItems.length} segments`);

// Get audio duration using spawnSync
function getAudioDuration(audioPath) {
  const result = spawnSync('ffprobe', [
    '-v', 'error',
    '-show_entries', 'format=duration',
    '-of', 'csv=p=0',
    audioPath
  ], { encoding: 'utf-8' });
  if (result.error || result.status !== 0) {
    throw new Error(`ffprobe failed: ${result.stderr || result.error}`);
  }
  return parseFloat(result.stdout.trim());
}

const dur = getAudioDuration(AUDIO);
console.log(`Audio duration: ${dur.toFixed(2)}s`);

// Build a precomputed timeline: for each timestamp, which slide AND caption should be active
const FPS = 10;
const INTERVAL = 1000 / FPS;
const totalFrames = Math.ceil(dur * FPS);
const slideTimeline = [];
const captionTimeline = [];  // stores caption text for each frame

for (let i = 0; i < totalFrames; i++) {
  const t = i / FPS;
  
  // Which slide?
  let activeSlide = 0;
  for (let j = 0; j < planSlides.length; j++) {
    const s = planSlides[j].start;
    const e = planSlides[j].end;
    if (t >= s && t < e) {
      activeSlide = j;
      break;
    }
  }
  slideTimeline.push(activeSlide);
  
  // Which caption?
  let captionText = "";
  for (const c of srtItems) {
    if (t >= c.start && t < c.end) {
      captionText = c.text;
      break;
    }
  }
  captionTimeline.push(captionText);
}

console.log(`Timeline built: ${totalFrames} frames`);

// Create the HTML with injected control script
// We read the source HTML and inject a reliable setSlide function
let srcHtml = readFileSync(HTML, 'utf-8');

// Remove the initial active class from markup only; keep CSS selectors intact.
srcHtml = srcHtml.replace(/class="([^"]*\bslide\b[^"]*)\bis-active\b([^"]*)"/, (_m, before, after) => {
  return `class="${before}${after}"`.replace(/\s+/g, ' ');
});

// Inject the control script BEFORE </body>
const controlScript = `
<script>
(function() {
  const _slides = document.querySelectorAll('.slide');
  window._setSlide = function(index, now) {
    _slides.forEach((sl, k) => {
      const pop = sl.querySelector('.image-popover');
      if (k === index) {
        sl.classList.add('is-active');
        sl.style.display = 'flex';
        sl.style.opacity = '1';
        if (pop) {
          const start = parseFloat(sl.dataset.start || '0');
          const rel = Math.max(0, (now || 0) - start);
          const popStart = parseFloat(pop.dataset.popStart || sl.dataset.popStart || '0');
          const popEnd = parseFloat(pop.dataset.popEnd || sl.dataset.popEnd || '0');
          pop.classList.toggle('on', rel >= popStart && rel < popEnd);
        }
      } else {
        sl.classList.remove('is-active');
        sl.style.display = 'none';
        sl.style.opacity = '0';
        if (pop) pop.classList.remove('on');
      }
    });
  };
  // Initialize first slide
  window._setSlide(0, 0);
})();
</script>`;

if (!srcHtml.includes('_setSlide')) {
  srcHtml = srcHtml.replace('</body>', controlScript + '\n</body>');
}

const injHtml = '/tmp/zaihua_render.html';
writeFileSync(injHtml, srcHtml);

// Build wrapper: iframe + caption layer + audio
// NOTE: NO timeupdate listener! Caption is controlled exclusively by the screenshot loop.
const wrapper = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1280px;height:720px;overflow:hidden;background:#000;font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif}
iframe{border:0;width:1920px;height:1080px;position:absolute;top:0;left:0;z-index:1;transform:scale(0.667);transform-origin:0 0}
#cap{position:absolute;bottom:0;left:0;right:0;z-index:5;display:flex;justify-content:center;align-items:flex-end;padding:0 40px 50px;pointer-events:none}
#cap .bubble{background:rgba(0,0,0,.82);color:#fff;padding:14px 30px;font-size:32px;font-weight:600;line-height:1.5;text-align:center;border-radius:8px;max-width:1800px;letter-spacing:.02em;display:none;text-shadow:0 2px 8px rgba(0,0,0,.6)}
#cap .bubble.on{display:inline-block}
</style></head>
<body>
<iframe id="f" src="file://${injHtml}"></iframe>
<div id="cap"><div class="bubble" id="bub"></div></div>
<audio id="bgm" src="file://${AUDIO}" preload="auto"></audio>
<script>
const bub = document.getElementById('bgm');
const ifr = document.getElementById('f');
ifr.addEventListener('load', () => {
  setTimeout(() => { bub.currentTime = 0; bub.play().catch(()=>{}); }, 300);
});
</script>
</body></html>`;

const tmpHtml = '/tmp/zaihua_wrapper.html';
writeFileSync(tmpHtml, wrapper);

// Screenshot loop: render in chunks with browser restarts to avoid OOM
const CHROME = '/usr/bin/chromium';
const framesDir = '/tmp/zaihua_video_frames';
// Optional start/end frame range for split rendering
const rangeStart = args['--start'] ? parseInt(args['--start']) : 0;
const rangeEnd = args['--end'] ? parseInt(args['--end']) : totalFrames;
if (rangeStart === 0) {
  rmSync(framesDir, { recursive: true, force: true });
}
mkdirSync(framesDir, { recursive: true });
const CHUNK = 50; // frames per browser session
const renderFrames = rangeEnd - rangeStart;
console.log(`Recording ${renderFrames} frames (${rangeStart}-${rangeEnd - 1}) at ${FPS} fps in chunks of ${CHUNK}...`);

let t0 = Date.now();
let totalSuccess = 0;
let totalFailed = 0;
for (let chunkStart = rangeStart; chunkStart < rangeEnd; chunkStart += CHUNK) {
  const chunkEnd = Math.min(chunkStart + CHUNK, rangeEnd);
  
  // Launch fresh browser for each chunk
  let chunkBrowser;
  try {
    chunkBrowser = await puppeteer.launch({
      headless: 'new',
      executablePath: CHROME,
      args: [
        '--no-sandbox', '--disable-setuid-sandbox',
        '--disable-dev-shm-usage', '--disable-gpu',
        '--single-process',
        '--disable-features=IsolateOrigins,site-per-process,TranslateUI',
        '--memory-pressure-off',
      ],
      defaultViewport: { width: 1280, height: 720 },
    });
  } catch (launchErr) {
    console.error(`Failed to launch browser for chunk ${chunkStart}-${chunkEnd}:`, launchErr.message);
    totalFailed += (chunkEnd - chunkStart);
    continue;
  }
  
  try {
    const chunkPage = await chunkBrowser.newPage();
    await chunkPage.setViewport({ width: 1280, height: 720 });
    await chunkPage.goto('file://' + tmpHtml, { waitUntil: 'domcontentloaded', timeout: 0 });
    await new Promise(r => setTimeout(r, 500));
    
    const chunkIh = await chunkPage.$('iframe#f');
    let chunkIframe = null;
    if (chunkIh) chunkIframe = await chunkIh.contentFrame();
    
    for (let i = chunkStart; i < chunkEnd; i++) {
      const targetSlide = slideTimeline[i];
      const targetCaption = captionTimeline[i];
      
      try {
        if (chunkIframe) {
          await chunkIframe.evaluate((idx, t) => {
            if (window._setSlide) window._setSlide(idx, t);
          }, targetSlide, i / FPS);
        } else {
          await chunkPage.evaluate((idx, t) => {
            const ifr = document.getElementById('f');
            if (ifr && ifr.contentWindow && ifr.contentWindow._setSlide) {
              ifr.contentWindow._setSlide(idx, t);
            }
          }, targetSlide, i / FPS);
        }
        
        if (targetCaption) {
          await chunkPage.evaluate((text) => {
            const bub = document.getElementById('bub');
            if (bub) { bub.textContent = text; bub.classList.add('on'); }
          }, targetCaption);
        } else {
          await chunkPage.evaluate(() => {
            const bub = document.getElementById('bub');
            if (bub) bub.classList.remove('on');
          });
        }
        
        const fp = `${framesDir}/f_${String(i).padStart(5,'0')}.png`;
        await chunkPage.screenshot({ path: fp, type: 'png' });
        totalSuccess++;
        
        if (i % 50 === 0 && i > chunkStart) {
          await chunkPage.evaluate(() => { if (window.gc) window.gc(); });
        }
        
        if (i % 60 === 0) {
          const t = (i / FPS).toFixed(1);
          process.stdout.write(`  frame ${i}/${totalFrames}  t=${t}s  slide=${targetSlide}\n`);
        }
      } catch (frameErr) {
        console.error(`  frame ${i} failed:`, frameErr.message);
        totalFailed++;
      }
    }
  } catch (chunkErr) {
    console.error(`Chunk ${chunkStart}-${chunkEnd} failed:`, chunkErr.message);
    totalFailed += (chunkEnd - chunkStart);
  } finally {
    await chunkBrowser.close();
    if (global.gc) global.gc();
    await new Promise(r => setTimeout(r, 2000)); // allow OS to reclaim memory
    process.stdout.write(`  chunk ${chunkStart}-${chunkEnd - 1} done\n`);
  }
}

console.log(`Captured ${totalSuccess} frames, ${totalFailed} failed`);
// browser already closed via chunk loop

if (rangeStart === 0 && rangeEnd === totalFrames) {
  console.log('Muxing...');
  const ffmpegResult = spawnSync('ffmpeg', [
    '-y',
    '-framerate', String(FPS),
    '-i', `${framesDir}/f_%05d.png`,
    '-i', AUDIO,
    '-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '128k',
    '-shortest',
    '-movflags', '+faststart',
    OUT,
  ], { stdio: 'inherit' });
  if (ffmpegResult.status !== 0) {
    throw new Error(`ffmpeg mux failed with code ${ffmpegResult.status}`);
  }
  console.log(`\nDone: ${OUT}`);
  const stats = statSync(OUT);
  console.log(`Size: ${(stats.size / 1024 / 1024).toFixed(2)}MB`);
} else {
  console.log('Frames captured, skip mux (partial range)');
}
