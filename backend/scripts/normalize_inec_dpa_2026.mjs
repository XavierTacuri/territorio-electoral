import { readFileSync, writeFileSync } from 'node:fs';

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Uso: node normalize_inec_dpa_2026.mjs <origen.csv> <destino.csv>');

function rows(text) {
  const result = [];
  let row = [], field = '', quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted && char === '"' && text[index + 1] === '"') { field += '"'; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (!quoted && char === ',') { row.push(field); field = ''; }
    else if (!quoted && (char === '\n' || char === '\r')) {
      if (char === '\r' && text[index + 1] === '\n') index += 1;
      row.push(field); result.push(row); row = []; field = '';
    } else field += char;
  }
  if (field || row.length) { row.push(field); result.push(row); }
  return result;
}

const clean = (value) => String(value ?? '').replace(/^\*+\s*/, '').replace(/\s+/g, ' ').trim();
const title = (value) => clean(value)
  .toLocaleLowerCase('es-EC')
  .replace(/(^|[ (/-])\p{L}/gu, (match) => match.toLocaleUpperCase('es-EC'))
  .replace(/\b(De|Del|La|Las|Los|En|Y)\b/g, (word, _match, offset) => offset === 0 ? word : word.toLocaleLowerCase('es-EC'));
const sourceRows = rows(readFileSync(input, 'utf8'));
const provinces = new Map(), cantons = new Map(), parishes = new Map();
let parishType = 'URBAN';
const lastByColumn = new Map();

for (const row of sourceRows) {
  const line = row.join(' ');
  if (/PARROQUIAS URBANAS/i.test(line)) parishType = 'URBAN';
  if (/PARROQUIAS RURALES/i.test(line)) parishType = 'RURAL';

  const provinceCode = clean(row[1]).padStart(2, '0');
  const provinceLabel = clean(row[4]);
  if (/^\d{2}$/.test(provinceCode) && Number(provinceCode) <= 24 && /^PROVINCIA (?:DEL?|DE LA) /i.test(provinceLabel)) {
    provinces.set(provinceCode, title(provinceLabel.replace(/^PROVINCIA (?:DEL?|DE LA) /i, '')));
  }

  const cantonCode = clean(row[2]).padStart(2, '0');
  if (/^\d{2}$/.test(provinceCode) && /^\d{2}$/.test(cantonCode) && /CANT[ÓO]N /i.test(provinceLabel)) {
    const dpa = provinceCode + cantonCode;
    const historical = /^\*/.test(String(row[4] ?? '').trim()) && dpa !== '2302';
    if (Number(provinceCode) <= 24 && !historical) {
      cantons.set(dpa, { province: provinceCode, name: title(provinceLabel.replace(/^\**\s*CANT[ÓO]N\s+/i, '')) });
    }
    parishType = 'URBAN';
  }

  for (let start = 1; start + 3 < row.length; start += 4) {
    const province = clean(row[start]).padStart(2, '0');
    const canton = clean(row[start + 1]).padStart(2, '0');
    const code = clean(row[start + 2]).padStart(2, '0');
    const rawName = String(row[start + 3] ?? '').trim();
    if (/^\d{2}$/.test(province) && /^\d{2}$/.test(canton) && /^\d{2}$/.test(code) && code !== '00' && rawName && Number(province) <= 24) {
      const cantonDpa = province + canton;
      if (!cantons.has(cantonDpa) || /^\*/.test(rawName)) continue;
      const dpa = cantonDpa + code;
      const currentName = rawName
        .replace(/,?\s+CABECERA CANTONAL.*$/i, '')
        .replace(/\s*\(CAB\.\s+EN[^)]*\)\s*$/i, '');
      const item = { canton: cantonDpa, type: Number(code) >= 51 ? 'RURAL' : parishType, name: title(currentName) };
      parishes.set(dpa, item);
      lastByColumn.set(start + 3, dpa);
    } else if (!clean(row[start]) && !clean(row[start + 1]) && !clean(row[start + 2]) && rawName && lastByColumn.has(start + 3)) {
      const dpa = lastByColumn.get(start + 3), item = parishes.get(dpa);
      const openParentheses = (item?.name.match(/\(/g) ?? []).length;
      const closeParentheses = (item?.name.match(/\)/g) ?? []).length;
      if (item && openParentheses > closeParentheses && !/^(COMPRENDE|CON SUS|Y LAS)/i.test(rawName)) {
        item.name = title(`${item.name} ${rawName}`);
      }
    }
  }
}

const quote = (value) => `"${String(value).replaceAll('"', '""')}"`;
const outputRows = [['level','dpa_code','parent_dpa_code','name','parish_type']];
for (const [dpa, name] of [...provinces].sort()) outputRows.push(['PROVINCE', dpa, '', name, '']);
for (const [dpa, item] of [...cantons].sort()) outputRows.push(['CANTON', dpa, item.province, item.name, '']);
for (const [dpa, item] of [...parishes].sort()) outputRows.push(['PARISH', dpa, item.canton, item.name, item.type]);
writeFileSync(output, outputRows.map((row) => row.map(quote).join(',')).join('\n') + '\n', 'utf8');
console.log(JSON.stringify({ provinces: provinces.size, cantons: cantons.size, parishes: parishes.size }));
