const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({console});
vm.runInContext(fs.readFileSync('legacy/Codigo.gs', 'utf8'), context);
vm.runInContext(fs.readFileSync('legacy/CrearTodosPDV.gs', 'utf8'), context);
const results = input.map(test => test.fn === 'sort' ? test.args[0].sort((a,b) => a.localeCompare(b, 'es', {numeric: test.args[1]})) : context[test.fn](...test.args));
process.stdout.write(JSON.stringify(results));
