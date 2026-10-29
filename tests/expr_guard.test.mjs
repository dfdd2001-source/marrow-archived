// Marrow 表达式守卫回归测试（node tests/expr_guard.test.mjs）
// 两组断言：
//   1) cores/ 里现存全部 outputs[].expr 必须通过（零误伤）
//   2) 已知逃逸/注入向量必须全部拒绝
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

import * as guard from "../app/expr_guard.mjs";
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

// —— 1) 存量表达式零误伤：从 cores/ 收集全部 expr，参数名按各 core 的
//        explorable.parameters 动态取（与生产调用方式一致） ——
const exprs = [];  // {expr, names}
for (const f of readdirSync(join(ROOT, "cores"))) {
  if (!f.endsWith(".json")) continue;
  const core = JSON.parse(readFileSync(join(ROOT, "cores", f), "utf-8"));
  for (const e of core.explorable || []) {
    if (e && typeof e === "object") {
      const names = (e.parameters || []).map(p => p.id);
      for (const o of e.outputs || []) if (o && o.expr) exprs.push({ expr: o.expr, names });
    }
  }
}

const PARAMS = ["a", "b", "c", "d", "ux", "uy", "vx", "vy", "bx", "by", "v1x", "v1y",
  "v2x", "v2y", "m11", "m12", "m22", "lambda", "s1", "s2", "x", "y", "z"];

test(`存量表达式全部通过守卫（共 ${exprs.length} 个）`, () => {
  // 零误伤是不变量；条数随仓库内容变化（私有全量 70+，公开演示 2），不设大阈值
  assert.ok(exprs.length >= 1, `应至少收集到 1 个表达式`);
  for (const { expr, names } of exprs) {
    assert.equal(guard.check(expr, names), true, `存量表达式被误拒: ${expr}`);
  }
});

// —— 2) 攻击向量全部拒绝 ——
const ATTACKS = [
  'fetch("http://evil")',                 // 未知标识符 + 字符串
  'alert(1)',                             // 未知标识符
  'Function("return process.env")()',     // 构造器逃逸
  'constructor.constructor("x")()',       // constructor 链
  'a.constructor',                        // 属性访问越权
  'Math.constructor',                     // Math.constructor
  'Math.toString',                        // 非 白名单成员
  '"a"',                                  // 字符串字面量
  "'a'",                                  // 字符串字面量
  "`a${x}`",                              // 模板字符串
  "a=alert",                              // 赋值 + 未知标识符
  "import('node:fs')",                    // 动态 import
  "a;b",                                  // 语句分隔（b 为参数也不允许分号）
  "globalThis", "window", "document", "eval", "process",  // 全局对象
  "Math",                                 // Math 本体（函数对象可被调用拼接）——只允许其成员
  "x[fetch]",                             // 括号内未知标识符
  "a{b:1}",                               // 对象字面量语法
];

test("攻击向量全部拒绝", () => {
  for (const e of ATTACKS) {
    assert.equal(guard.check(e, PARAMS), false, `攻击向量未被拒绝: ${e}`);
  }
});

// —— 3) 边界：非字符串 / 空 / 超长 ——
test("边界输入", () => {
  assert.equal(guard.check(null, PARAMS), false);
  assert.equal(guard.check("", PARAMS), false);
  assert.equal(guard.check("  ", PARAMS), false);
  assert.equal(guard.check("a+".repeat(600) + "1", PARAMS), false);  // 超长
  assert.equal(guard.check("Math.hypot(ux, uy)", PARAMS), true);
  assert.equal(guard.check("Math.PI", PARAMS), true);
  assert.equal(guard.check("not_a_param", PARAMS), false);           // 未知参数
  assert.equal(guard.check("a**2===4 ? 1 : 0", PARAMS), true);       // 幂/全等/三元
  assert.equal(guard.check("[[a,b],[c,d]]", PARAMS), true);          // 嵌套数组
});
