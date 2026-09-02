// 仓库自包含版 —— 请放到 <uni-app 仓库根>/scripts/normalize-app-manifest.js
// 用法（package.json 里一行相对路径就够了）：
//   "build:app": "uni build -p app && node scripts/normalize-app-manifest.js"
//
// 行为：
//   1) 对 dist/build/app-plus、dist/build/app 下的 manifest.json：删除 plus.distribute + 按 HBuilderX 单行紧凑格式写回
//   2) 把 dist/build/app-plus（优先）或 dist/build/app 全量镜像到 unpackage/resources/<appid>/www
//      (目录结构和 HBuilderX "发行→生成本地打包APP资源" 输出完全一致)
//   3) 控制台打印归一化前后 MD5、就位信息
// 零依赖，纯 Node.js 内置模块。支持 src/manifest.json 为 JSONC（// 行注释、/* */ 块注释、JSON5 尾逗号、键名 appid 或 id）。

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ====== 仓库根自定位：脚本位于 <repo>/scripts，所以 __dirname/.. 就是仓库根 ======
const PROJECT_ROOT = path.resolve(__dirname, '..');
const SRC_MANIFEST = path.join(PROJECT_ROOT, 'src', 'manifest.json');

function md5File(p) {
  return crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex');
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function rmrf(target) {
  if (!fs.existsSync(target)) return;
  const stat = fs.lstatSync(target);
  if (stat.isDirectory()) {
    for (const name of fs.readdirSync(target)) rmrf(path.join(target, name));
    fs.rmdirSync(target);
  } else {
    fs.unlinkSync(target);
  }
}

function copytree(src, dst) {
  ensureDir(dst);
  for (const name of fs.readdirSync(src)) {
    const s = path.join(src, name);
    const d = path.join(dst, name);
    const st = fs.lstatSync(s);
    if (st.isDirectory()) copytree(s, d);
    else fs.copyFileSync(s, d);
  }
}

// 仅移除 JSON 语法空白（字符串字面量内部空格、中文等原样保留）——等价于 Python 的 separators=(',',':')
function compactJson(raw) {
  let out = '';
  let inStr = false;
  let esc = false;
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (inStr) {
      out += c;
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
    } else {
      if (c === '"') { inStr = true; out += c; continue; }
      if (c === ' ' || c === '\n' || c === '\r' || c === '\t') continue;
      out += c;
    }
  }
  return out;
}

// 移除 // 行注释 与 /* */ 块注释（保留字符串字面量内部原样）
function stripJsComments(text) {
  let out = '';
  let inStr = false;
  let esc = false;
  let inBlock = false;
  let inLine = false;
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    const n = text[i + 1];
    if (inLine) {
      if (c === '\n') { inLine = false; out += c; }
      i++; continue;
    }
    if (inBlock) {
      if (c === '*' && n === '/') { inBlock = false; i += 2; continue; }
      i++; continue;
    }
    if (inStr) {
      out += c;
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      i++; continue;
    }
    if (c === '/' && n === '/') { inLine = true; i += 2; continue; }
    if (c === '/' && n === '*') { inBlock = true; i += 2; continue; }
    if (c === '"') inStr = true;
    out += c;
    i++;
  }
  return out;
}

// 移除 } 或 ] 前的多余逗号（保留字符串字面量内部原样）
function stripTrailingCommas(text) {
  let out = '';
  let inStr = false;
  let esc = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      out += c;
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; out += c; continue; }
    if (c === ',') {
      let j = i + 1;
      while (j < text.length && /\s/.test(text[j])) j++;
      if (j < text.length && (text[j] === ']' || text[j] === '}')) continue;
    }
    out += c;
  }
  return out;
}

function normalizeManifest(manifestPath) {
  if (!fs.existsSync(manifestPath)) return null;
  const before = md5File(manifestPath);
  const obj = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (obj && typeof obj === 'object' && obj.plus && Object.prototype.hasOwnProperty.call(obj.plus, 'distribute')) {
    delete obj.plus.distribute;
  }
  fs.writeFileSync(manifestPath, compactJson(JSON.stringify(obj)), 'utf8');
  return { before, after: md5File(manifestPath), size: fs.statSync(manifestPath).size };
}

function readAppId() {
  const raw = fs.readFileSync(SRC_MANIFEST, 'utf8');
  let obj;
  try {
    obj = JSON.parse(raw);
  } catch (_) {
    try {
      obj = JSON.parse(stripTrailingCommas(stripJsComments(raw)));
    } catch (e) {
      console.error('[normalize-app-manifest] src/manifest.json 解析失败（不是合法 JSON / JSONC / JSON5）:', SRC_MANIFEST, e.message);
      process.exit(1);
    }
  }
  const id = (obj && (obj.id || obj.appid)) || '';
  if (!id) {
    console.error('[normalize-app-manifest] src/manifest.json 里未找到 appid/id 字段');
    process.exit(1);
  }
  return id;
}

function main() {
  if (!fs.existsSync(SRC_MANIFEST)) {
    console.error('[normalize-app-manifest] 找不到 src/manifest.json:', SRC_MANIFEST);
    console.error('  请确认本脚本放置在 <仓库>/scripts/ 下。当前 PROJECT_ROOT=' + PROJECT_ROOT);
    process.exit(1);
  }
  const distDirs = [
    path.join(PROJECT_ROOT, 'dist', 'build', 'app-plus'),
    path.join(PROJECT_ROOT, 'dist', 'build', 'app'),
  ].filter((d) => fs.existsSync(d) && fs.statSync(d).isDirectory());

  if (distDirs.length === 0) {
    console.error('[normalize-app-manifest] 未找到 dist/build/app 或 dist/build/app-plus，请先执行 npm run build:app');
    process.exit(1);
  }

  console.log('\n=== normalize-app-manifest: manifest 归一化 + 资源就位  (%s) ===', path.basename(PROJECT_ROOT));
  for (const dir of distDirs) {
    const mp = path.join(dir, 'manifest.json');
    const r = normalizeManifest(mp);
    if (r) {
      console.log('  ✓ %s 归一化完成', path.relative(PROJECT_ROOT, dir));
      console.log('      manifest MD5_before=%s  →  MD5_after=%s  bytes=%s', r.before, r.after, r.size);
    }
  }

  const source = distDirs.includes(path.join(PROJECT_ROOT, 'dist', 'build', 'app-plus'))
    ? path.join(PROJECT_ROOT, 'dist', 'build', 'app-plus')
    : distDirs[0];
  const appid = readAppId();
  const wwwDir = path.join(PROJECT_ROOT, 'unpackage', 'resources', appid, 'www');
  console.log('\n  复制 %s  →  unpackage/resources/%s/www', path.relative(PROJECT_ROOT, source), appid);
  if (fs.existsSync(wwwDir)) rmrf(wwwDir);
  copytree(source, wwwDir);

  const finalManifest = path.join(wwwDir, 'manifest.json');
  if (!fs.existsSync(finalManifest)) {
    console.error('[normalize-app-manifest] 复制后未找到 manifest.json:', finalManifest);
    process.exit(1);
  }
  console.log('  ✓ 就位完成');
  console.log('      %s  MD5=%s  bytes=%s\n', path.relative(PROJECT_ROOT, finalManifest), md5File(finalManifest), fs.statSync(finalManifest).size);
}

main();
