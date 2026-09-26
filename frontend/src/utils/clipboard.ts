/**
 * 复制文本到剪贴板，带非安全上下文回退。
 *
 * `navigator.clipboard` 只在**安全上下文**（HTTPS 或 localhost）下存在——管理后台常通过
 * `http://<内网IP>:端口` 访问，此时它是 undefined，只写这一条路的话复制永远失败。
 * 回退方案：临时 textarea + `document.execCommand('copy')`（已废弃但仍是唯一覆盖
 * 非安全上下文的手段）。
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限被拒等场景，落到下面的回退再试一次
    }
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  // 必须可见但不在视野内：display:none 会让部分浏览器跳过选中
  textarea.style.position = 'fixed'
  textarea.style.top = '-9999px'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(textarea)
  return ok
}
