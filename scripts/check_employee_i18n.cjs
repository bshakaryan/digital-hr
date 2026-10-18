/** Check copy coverage and lossless RU/KZ formatting without a browser/server. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = path.resolve(__dirname, '..');
const requireFrontend = Module.createRequire(path.join(root, 'frontend/package.json'));
const ts = requireFrontend('typescript');
function load(file, imports = {}) {
  const filename = path.join(root, file);
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const mod = new Module(filename);
  mod.require = name => name in imports ? imports[name] : requireFrontend(name);
  mod._compile(compiled, filename);
  return mod.exports;
}
const messages = load('frontend/lib/employee-messages.ts');
const { employeeI18n } = load('frontend/lib/employee-i18n.tsx', { './employee-messages': messages });
const ru = employeeI18n('ru'), kk = employeeI18n('kk');
const files = ['workspace', 'employee-home-dashboard', 'requests', 'request-lifecycle', 'leave-calendar', 'ui', 'documentolog', 'floating-jana'];
const used = new Set();
for (const file of files) {
  const source = ts.createSourceFile(file+'.tsx', fs.readFileSync(path.join(root, 'frontend/components/'+file+'.tsx'), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(source) === 't' && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) used.add(node.arguments[0].text.trim());
    ts.forEachChild(node, visit);
  }
  visit(source);
}
for (const key of used) assert.ok(messages.employeeMessages[key], `Missing Kazakh copy: ${key}`);
assert.equal(kk.t('Главная'), 'Басты бет');
assert.equal(kk.t('Заявка №{0}', 42), '№42 өтінім');
assert.equal(kk.t('Заявка №42 отправлена на согласование'), '№42 өтінім келісуге жіберілді');
assert.equal(kk.t('Недостаточно дней отпуска: требуется 28, доступно 25'), 'Демалыс күндері жеткіліксіз: қажеті 28, қолжетімдісі 25');
assert.equal(kk.t(' дн.'), ' күн');
assert.equal(kk.t('Сәлем,'), 'Сәлем,');
assert.equal(ru.t('Заявка №{0}', 42), 'Заявка №42');
assert.equal(ru.t(' Дата начала '), ' Дата начала ');
assert.equal(kk.t('User-entered comment: <script>$&</script>'), 'User-entered comment: <script>$&</script>');
assert.equal(kk.t(''), '');
assert.equal(kk.date('2026-10-25', true), '25 қазан 2026 ж.');
assert.equal(kk.month('2026-10-01'), '2026 ж. қазан');
assert.notEqual(kk.date('2026-10-25', true), ru.date('2026-10-25', true));
for (const [key, value] of Object.entries(messages.employeeMessages)) {
  assert.deepEqual((key.match(/\{\d+\}/g)||[]).sort(), (value.match(/\{\d+\}/g)||[]).sort(), `Template arguments differ: ${key}`);
}
console.log(`Employee RU/KZ: ${used.size} UI message keys covered; templates, errors, dates and RU preservation passed.`);
