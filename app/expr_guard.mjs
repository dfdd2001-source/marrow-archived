/* Marrow 表达式守卫：explorable.outputs[].expr 求值前的白名单校验。
 *
 * 背景：expr 由提取流水线（LLM）生成，前端用 new Function 求值——
 * "数据即代码"的执行面必须有边界。本守卫把可执行表达式收窄为：
 *   参数标识符 + Math.<白名单方法/常量> + 数字/数组字面量 + 算术/比较/三元运算
 * 禁止：字符串与模板字面量、赋值、语句分隔、大括号、反斜杠，
 * 以及除 Math 成员外的任何属性访问（constructor 逃逸路径被封死）。
 * 校验不通过时求值方应显示 "?"（显式失败），绝不静默降级。
 *
 * node tests/expr_guard.test.mjs 直接以 ESM 导入本模块做回归
 * （存量 expr 零误伤 + 攻击向量全拒）。
 */

// Math 成员白名单：当前 expr 用到的 + 常见数学函数（新增成员时在此扩充）
const MATH_MEMBERS = /^(abs|ceil|floor|round|trunc|sign|sqrt|cbrt|pow|exp|log|log2|log10|max|min|hypot|atan|atan2|asin|acos|sin|cos|tan|PI|E|LN2|LN10|SQRT2)$/;

function isIdent(s) {
  return /^[A-Za-z_$][\w$]*$/.test(s);
}

// 返回 true = 允许求值；false = 拒绝。
// names: 允许出现的参数名（来自 explorable.parameters[].id）
export function check(expr, names) {
  if (typeof expr !== "string") return false;
  const s = expr.trim();
  if (!s || s.length > 1000) return false;
  // 语法面收窄：无字符串/模板/语句/对象字面量/转义
  if (/["'`\;\\{}]/.test(s)) return false;
  const allowed = { Math: true };
  (names || []).forEach(n => {
    if (isIdent(n)) allowed[n] = true;
  });
  // 标识符逐个检查：紧跟 '.' 的必须是 Math 白名单成员，其余必须是参数名或 Math；
  // Math 本身只允许出现在 "Math.成员" 形态（裸对象不放行）
  const idRe = /[A-Za-z_$][\w$]*/g;
  let m;
  while ((m = idRe.exec(s))) {
    if (s[m.index - 1] === ".") {
      if (!MATH_MEMBERS.test(m[0])) return false;
    } else if (m[0] === "Math") {
      if (s[m.index + 4] !== ".") return false;
    } else if (!allowed[m[0]]) {
      return false;
    }
  }
  // 剩余字符只允许：数字、运算符、比较/三元、括号、逗号、点、空白
  const residue = s
    .replace(/[A-Za-z_$][\w$]*/g, " ")
    .replace(/[\d+\-*/%(),.?:!<>=&|\[\]\s]/g, "");
  return residue === "";
}
