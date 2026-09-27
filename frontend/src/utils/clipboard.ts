/**
 * 复制文本到剪贴板，带非安全上下文回退。
 *
 * `navigator.clipboard` 只在**安全上下文**（HTTPS 或 localhost）下存在——管理后台常通过
 * `http://<内网IP>:端口` 访问，此时它是 undefined，只写这一条路的话复制永远失败。
 * 回退方案是 `document.execCommand('copy')`（已废弃但仍是唯一覆盖非安全上下文的手段），
 * 必须在点击等用户操作的同步调用链里执行。
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
  return legacyCopy(text)
}

function legacyCopy(text: string): boolean {
  // 在 copy 事件里直接写入剪贴板数据，不依赖选区：Element Plus 弹窗的焦点陷阱会把焦点
  // 从弹窗外的 textarea 拉回弹窗，选区随之丢失，只靠选区的写法在弹窗里拷不到任何东西
  const onCopy = (event: ClipboardEvent) => {
    event.clipboardData?.setData('text/plain', text)
    event.preventDefault()
  }
  // 部分浏览器没有选区时不触发 copy 事件，所以仍放一个选中的 textarea；挂在当前焦点所在的
  // 弹窗里，焦点陷阱就不会把焦点拉走
  const previous = document.activeElement as HTMLElement | null
  const host = previous?.closest<HTMLElement>('[role="dialog"]') ?? document.body
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
  host.appendChild(textarea)
  textarea.focus()
  textarea.setSelectionRange(0, text.length)

  document.addEventListener('copy', onCopy)
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.removeEventListener('copy', onCopy)
  host.removeChild(textarea)
  previous?.focus()
  return ok
}
