const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const data = input.books;
class Range {
  constructor(book, title, row, col, rows=1, cols=1) {Object.assign(this,{book,title,row,col,rows,cols});}
  getValues() {return Array.from({length:this.rows},(_,i)=>Array.from({length:this.cols},(_,j)=>data[this.book][this.title][this.row+i-1]?.[this.col+j-1] ?? ''));}
  getDisplayValues() {return this.getValues().map(r=>r.map(String));}
  setValues(rows) {
    const target = data[this.book][this.title];
    rows.forEach((r,i)=>{while(target.length<this.row+i)target.push([]);r.forEach((v,j)=>{while(target[this.row+i-1].length<this.col+j)target[this.row+i-1].push('');target[this.row+i-1][this.col+j-1]=v;});});
    return this;
  }
  setValue(v) {return this.setValues([[v]]);}
  getValue() {return this.getValues()[0][0];}
  setBackground() {return this;}
  setFontColor() {return this;}
  setFontWeight() {return this;}
}
class Sheet {
  constructor(book,title){Object.assign(this,{book,title});}
  getName(){return this.title;}
  getLastRow(){return data[this.book][this.title].length;}
  getLastColumn(){return Math.max(0,...data[this.book][this.title].map(r=>r.length));}
  getRange(...args){return new Range(this.book,this.title,...args);}
  appendRow(row){this.getRange(this.getLastRow()+1,1,1,row.length).setValues([row]);return this;}
  clearContents(){data[this.book][this.title]=[];return this;}
  setFrozenRows(){return this;}
  autoResizeColumns(){return this;}
  setName(name){data[this.book][name]=data[this.book][this.title];delete data[this.book][this.title];this.title=name;return this;}
}
class Book {
  constructor(id){this.id=id;}
  getSheetByName(title){return Object.hasOwn(data[this.id],title)?new Sheet(this.id,title):null;}
  insertSheet(title){data[this.id][title]=[];return new Sheet(this.id,title);}
  getSheets(){return Object.keys(data[this.id]).map(title=>new Sheet(this.id,title));}
}
function open(url){return new Book(url.includes('1q34wHfO')?'master':url.includes('1_Kj9mXyd')?'general':url);}
const context = vm.createContext({console, Date, SpreadsheetApp:{openByUrl:open,flush(){}},
  Utilities:{getUuid:()=>'<UUID>',formatDate:(date)=>date.toISOString().slice(0,10)},
  Session:{getScriptTimeZone:()=> 'America/Bogota'},LockService:{getScriptLock:()=>({waitLock(){},releaseLock(){}})}});
vm.runInContext(fs.readFileSync('legacy/Codigo.gs','utf8'),context);
const result = context[input.function](...(input.args||[]));
function clean(v){if(v instanceof Date)return '<DATE>';if(Array.isArray(v))return v.map(clean);if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,clean(x)]));return v;}
process.stdout.write(JSON.stringify(clean({result,books:data})));
