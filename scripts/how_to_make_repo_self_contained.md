# 让 uni-app 仓库"npm run build:app 就直接搞定 normalize+就位"的步骤

> 目标：仓库里完全不依赖绝对路径，clone 到任何机器/路径直接 `npm run build:app` 即可。

## 步骤 1：把脚本放进仓库（两个仓库各放一次）

把本目录下 `REPO__normalize-app-manifest.self-contained.js` **复制**到：

```
I:\Work\20260615\pda-submit\scripts\normalize-app-manifest.js
I:\Work\20260615\Jinchang-Pad\scripts\normalize-app-manifest.js
```

（脚本放在 `<repo>/scripts/` 下，`__dirname/..` 自动定位到仓库根，所以换机器换路径都好使。）

然后记得把这个新文件提交到 git。

## 步骤 2：改 package.json 里的 build:app（两个仓库各改 1 行）

把脚本 `build:app` 从：

```json
"build:app": "uni build -p app"
```

替换为：

```json
"build:app": "uni build -p app && node scripts/normalize-app-manifest.js"
```

保存。Windows CMD/PowerShell 和 macOS/Linux bash/sh 都支持 `&&`。

## 验证（任选一个仓库）

```powershell
cd I:\Work\20260615\pda-submit
npm run build:app
```

期望输出末尾包含：

```
=== normalize-app-manifest: manifest 归一化 + 资源就位  (pda-submit) ===
  ✓ dist\build\app 归一化完成
  ✓ dist\build\app-plus 归一化完成（如果存在）
  复制 dist\build\app-plus  →  unpackage/resources/__UNI__1A1EF9F/www
  ✓ 就位完成
      unpackage/resources/__UNI__1A1EF9F/www/manifest.json  MD5=2b24c4cdb8bd8082e229ccb3918f92e2  bytes=1053
```

## 流水线侧（uniapp-android-auto-build）会怎样？

流水线 `pipeline/hbuilderx_step.py` 现在的优先级是：
1. **优先**用仓库自带的 `scripts/normalize-app-manifest.js`（不传参，相对路径模式）
2. 否则 fallback 到流水线项目内 `scripts/normalize-app-manifest.js`（显式传 <repo_dir>，兼容模式）

所以仓库做好步骤 1+2 之后，流水线自动切到"仓库自包含"方式，不再依赖流水线项目的绝对路径。clone 到任意机器，流水线也能照常运行。
