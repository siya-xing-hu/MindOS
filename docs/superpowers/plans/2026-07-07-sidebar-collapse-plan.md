# 文档目录树折叠与自动展开实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 MindOS 文档页目录树默认全部折叠，并在从搜索/问答跳转时自动展开目标文件所在路径。

**Architecture:** 纯前端实现，仅修改 `src/templates/index.html`。通过调整 `renderTree` 默认折叠目录、为目录节点增加路径标识、新增 `expandToPath` 函数，在搜索/问答跳转时触发路径展开。

**Tech Stack:** HTML、原生 JavaScript、FastAPI（后端无改动）

## Global Constraints

- 仅修改 `src/templates/index.html`，后端接口与数据格式保持不变。
- 目录节点使用 `data-path` 属性标识路径。
- 手动点击目录仍可展开/折叠。

---

### Task 1: 目录树默认折叠

**Files:**
- Modify: `src/templates/index.html:343-357`

**Interfaces:**
- Consumes: `renderTree(node, parent, depth)` 现有签名不变。
- Produces: 目录节点默认不带 `open` 类，子容器默认隐藏。

- [ ] **Step 1: 修改 renderTree 默认折叠目录**

将 `dirDiv.className = 'tree-dir open';` 改为 `dirDiv.className = 'tree-dir';`，并将 `childContainer` 初始 `display` 设为 `none`。

```javascript
function renderTree(node, parent, depth) {
  for (const [name, child] of Object.entries(node.children || {})) {
    const dirDiv = document.createElement('div');
    dirDiv.className = 'tree-dir';
    dirDiv.style.marginLeft = (depth * 12) + 'px';
    dirDiv.textContent = name;
    parent.appendChild(dirDiv);
    const childContainer = document.createElement('div');
    childContainer.className = 'tree-node';
    childContainer.style.display = 'none';
    parent.appendChild(childContainer);
    dirDiv.addEventListener('click', () => {
      dirDiv.classList.toggle('open');
      childContainer.style.display = dirDiv.classList.contains('open') ? '' : 'none';
    });
    renderTree(child, childContainer, depth + 1);
  }
  // ... files unchanged
}
```

- [ ] **Step 2: 手动测试**

启动服务：`python -m src.server`
浏览器访问 `http://localhost:9000`，切换到文档页，确认所有文件夹默认折叠，点击可展开/折叠。

- [ ] **Step 3: 提交**

```bash
git add src/templates/index.html
git commit -m "feat: collapse directory tree by default"
```

---

### Task 2: 为目录节点添加路径标识

**Files:**
- Modify: `src/templates/index.html:343-357`

**Interfaces:**
- Consumes: `renderTree(node, parent, depth)` 接收当前节点路径。
- Produces: 每个目录 `div` 带有 `data-path` 属性，值为相对路径。

- [ ] **Step 1: 修改 renderTree 签名并设置 data-path**

将 `renderTree` 增加 `path` 参数，递归时传递当前目录路径。

```javascript
function renderTree(node, parent, depth, path = '') {
  for (const [name, child] of Object.entries(node.children || {})) {
    const childPath = path ? path + '/' + name : name;
    const dirDiv = document.createElement('div');
    dirDiv.className = 'tree-dir';
    dirDiv.dataset.path = childPath;
    dirDiv.style.marginLeft = (depth * 12) + 'px';
    dirDiv.textContent = name;
    parent.appendChild(dirDiv);
    const childContainer = document.createElement('div');
    childContainer.className = 'tree-node';
    childContainer.style.display = 'none';
    parent.appendChild(childContainer);
    dirDiv.addEventListener('click', () => {
      dirDiv.classList.toggle('open');
      childContainer.style.display = dirDiv.classList.contains('open') ? '' : 'none';
    });
    renderTree(child, childContainer, depth + 1, childPath);
  }
  // ... files unchanged
}
```

- [ ] **Step 2: 手动测试**

在浏览器开发者工具中检查目录节点，确认每个 `.tree-dir` 都有正确的 `data-path` 属性。

- [ ] **Step 3: 提交**

```bash
git add src/templates/index.html
git commit -m "feat: add data-path to directory nodes"
```

---

### Task 3: 实现 expandToPath 函数

**Files:**
- Modify: `src/templates/index.html:387-388` 附近

**Interfaces:**
- Consumes: 目录节点 `data-path` 属性。
- Produces: `expandToPath(filePath)` 函数，展开从根到文件所在目录的路径。

- [ ] **Step 1: 在 loadFile 附近新增 expandToPath**

```javascript
function expandToPath(filePath) {
  const parts = filePath.split('/');
  parts.pop(); // remove filename
  let currentPath = '';
  for (const part of parts) {
    currentPath = currentPath ? currentPath + '/' + part : part;
    const dir = document.querySelector(`.tree-dir[data-path="${CSS.escape(currentPath)}"]`);
    if (!dir) continue;
    const container = dir.nextElementSibling;
    if (container && container.classList.contains('tree-node')) {
      dir.classList.add('open');
      container.style.display = '';
    }
  }
}
```

注意：`CSS.escape` 在部分旧浏览器可能不存在，可用简单转义兜底：

```javascript
function escapePath(p) {
  return p.replace(/"/g, '\\"');
}
```

为兼容起见，使用更 robust 的遍历匹配：

```javascript
function expandToPath(filePath) {
  const parts = filePath.split('/');
  parts.pop();
  let currentPath = '';
  document.querySelectorAll('.tree-dir.open').forEach(d => d.classList.remove('open'));
  for (const part of parts) {
    currentPath = currentPath ? currentPath + '/' + part : part;
    const dir = Array.from(document.querySelectorAll('.tree-dir')).find(d => d.dataset.path === currentPath);
    if (!dir) continue;
    const container = dir.nextElementSibling;
    if (container && container.classList.contains('tree-node')) {
      dir.classList.add('open');
      container.style.display = '';
    }
  }
}
```

- [ ] **Step 2: 手动测试**

在浏览器控制台调用 `expandToPath('docs/guide/quickstart.md')`，确认对应路径被展开。

- [ ] **Step 3: 提交**

```bash
git add src/templates/index.html
git commit -m "feat: add expandToPath helper"
```

---

### Task 4: 搜索页结果可点击并自动展开路径

**Files:**
- Modify: `src/templates/index.html:450-456`

**Interfaces:**
- Consumes: `expandToPath(path)`、`loadFile(path)`、`showTab(tab)`。
- Produces: 搜索结果点击后跳转到文档页并展开路径。

- [ ] **Step 1: 为搜索结果添加点击事件**

```javascript
data.results.forEach(r => {
  const div = document.createElement('div');
  div.className = 'result';
  div.style.cursor = 'pointer';
  div.innerHTML = `<div class="result-meta"><span>${r.title || ''} › ${r.section || ''}</span><span class="score">score: ${r.score.toFixed(4)}</span></div><div class="result-text">${escapeHtml(r.text).replace(new RegExp(escapeReg(q), 'gi'), m => '<mark>'+m+'</mark>')}</div>`;
  div.addEventListener('click', () => {
    showTab('docs');
    setTimeout(() => {
      expandToPath(r.path);
      loadFile(r.path);
      // highlight file node
      document.querySelectorAll('.tree-file').forEach(el => el.classList.remove('selected'));
      const fileNode = Array.from(document.querySelectorAll('.tree-file')).find(el => {
        const cb = el.querySelector('.checkbox');
        return cb && cb.dataset.path === r.path;
      });
      if (fileNode) fileNode.classList.add('selected');
    }, 100);
  });
  container.appendChild(div);
});
```

- [ ] **Step 2: 手动测试**

在搜索页输入关键词，点击结果，确认跳转到文档页、路径展开、文件内容加载。

- [ ] **Step 3: 提交**

```bash
git add src/templates/index.html
git commit -m "feat: search results navigate to file and expand path"
```

---

### Task 5: 问答页来源点击自动展开路径

**Files:**
- Modify: `src/templates/index.html:493-496`

**Interfaces:**
- Consumes: `expandToPath(path)`、`loadFile(path)`、`showTab(tab)`。
- Produces: 来源点击后跳转到文档页并展开路径。

- [ ] **Step 1: 修改 source-item 点击逻辑**

```javascript
d.addEventListener('click', () => {
  showTab('docs');
  setTimeout(() => {
    expandToPath(s.path);
    loadFile(s.path);
    document.querySelectorAll('.tree-file').forEach(el => el.classList.remove('selected'));
    const fileNode = Array.from(document.querySelectorAll('.tree-file')).find(el => {
      const cb = el.querySelector('.checkbox');
      return cb && cb.dataset.path === s.path;
    });
    if (fileNode) fileNode.classList.add('selected');
  }, 100);
});
```

- [ ] **Step 2: 手动测试**

在问答页提问，等待来源出现后点击来源，确认跳转到文档页、路径展开、文件内容加载。

- [ ] **Step 3: 提交**

```bash
git add src/templates/index.html
git commit -m "feat: Q\u0026A sources navigate to file and expand path"
```

---

## Self-Review

**1. Spec coverage:**
- 默认折叠：Task 1
- 手动展开：Task 1（保留 click 事件）
- 搜索跳转自动展开路径：Task 4
- 问答跳转自动展开路径：Task 5
- 其他目录默认关闭：Task 1 + Task 3（仅展开目标路径）

**2. Placeholder scan:**
- 无 TBD/TODO。
- 所有代码块完整。
- 所有命令和预期输出明确。

**3. Type一致性：**
- `expandToPath` 在 Task 3 定义，Task 4/5 使用相同签名。
- `renderTree` 新增 `path` 参数有默认值，不影响 Task 1 调用。
