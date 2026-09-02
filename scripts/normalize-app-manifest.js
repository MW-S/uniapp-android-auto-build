// 放置在流水线项目里，用法：
//   node scripts/normalize-app-manifest.js <仓库根绝对路径>
// 执行：
//   1) 对 <repo>/dist/build/app-plus/manifest.json 和 dist/build/app/manifest.json
//      删除 plus.distribute 节点并按 HBuilderX 单行紧凑格式写回（仅 JSON 语法空白，字符串内空格保留）
//   2) 把 dist/build/app-plus（优先）全量镜像到 unpackage/resources/<appid>/www
//   3) 控制台打印归一化前后 MD5、就位完成信息

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

if (process.argv.length < 3) {
  console.error('用法: node scripts/normalize-app-manifest.js <仓库根绝对路径>');
  process.exit(1);
}

const PROJECT_ROOT = path.resolve(process.argv[2]);
const SRC_MANIFEST = path.join(PROJECT_ROOT, 'src', 'manifest.json');
if (!fs.existsSync(SRC_MANIFEST)) {
  console.error('[normalize-app-manifest] 找不到 src/manifest.json:', SRC_MANIFEST);
  process.exit(1);
}

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

// 移除 JSON 字符串字面量"外"的所有空白（等价于 JSON.stringify 的 separators=(',',':')）
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

function stripJsComments(text) {
  // 移除 JSONC / JSON5 风格的 // 行注释 与 /* ... */ 块注释（保留字符串字面量内部原样）
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

function stripTrailingCommas(text) {
  // JSON5 允许在 } 或 ] 前有多余逗号，解析前做一个保守的移除（保留字符串字面量内部原样）
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
      // 向后跳过空白，若下一个有效字符是 ] 或 } 则丢弃这个逗号
      let j = i + 1;
      while (j < text.length && /\s/.test(text[j])) j++;
      if (j < text.length && (text[j] === ']' || text[j] === '}')) continue;
    }
    out += c;
  }
  return out;
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
      console.error('[normalize-app-manifest] src/manifest.json 解析失败（不是合法 JSON / JSONC）:', SRC_MANIFEST, e.message);
      process.exit(1);
    }
  }
  // 同时兼容 "id"（DCloud unpackage 资源目录命名字段）和 "appid"（src/manifest.json 常见键名）
  const id = (obj && (obj.id || obj.appid)) || '';
  if (!id) {
    console.error('[normalize-app-manifest] src/manifest.json 里未找到 appid/id 字段');
    process.exit(1);
  }
  return id;
}

function main() {
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
      console.log('  ✓ dist %s 归一化完成', path.relative(PROJECT_ROOT, dir));
      console.log('      manifest: MD5_before=%s  →  MD5_after=%s  bytes=%s', r.before, r.after, r.size);
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
  console.log('      www/manifest.json  MD5=%s  bytes=%s\n', md5File(finalManifest), fs.statSync(finalManifest).size);
}

main();
