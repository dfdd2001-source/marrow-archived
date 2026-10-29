/* Marrow 共享工具：HTML 转义。 */

// 文本与普通属性值通用的转义（属性注入点一律走 data-* 委托，不再有 JS 字符串拼接）
export function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
