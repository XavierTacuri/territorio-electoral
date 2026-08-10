import csv,io
from app.services.exceptions import BusinessRuleError
from app.importers.mappings import FORBIDDEN_HEADERS,PROFILES
def decode_csv(content:bytes,encoding:str|None=None):
 if not content:raise BusinessRuleError('Archivo vacío')
 candidates=[encoding] if encoding else ['utf-8-sig']
 if encoding=='latin-1':candidates=['latin-1']
 last=None
 for enc in candidates:
  try:return content.decode(enc),enc
  except UnicodeDecodeError as e:last=e
 raise BusinessRuleError('Codificación inválida') from last
def parse_csv(content:bytes,profile:str,encoding:str|None=None,delimiter:str|None=None,mapping:dict|None=None):
 text,used=decode_csv(content,encoding);sample=text[:4096]
 delim=delimiter or (';' if sample.count(';')>sample.count(',') else ',')
 if delim not in {',',';'}:raise BusinessRuleError('Delimitador inválido')
 reader=csv.DictReader(io.StringIO(text),delimiter=delim)
 if not reader.fieldnames:raise BusinessRuleError('Cabecera faltante')
 headers=[x.strip().lower() for x in reader.fieldnames]
 if set(headers)&FORBIDDEN_HEADERS:raise BusinessRuleError('Archivo rechazado: posibles microdatos')
 required=PROFILES.get(profile)
 if not required:raise BusinessRuleError('Perfil de mapeo inexistente')
 mapping=mapping or {};actual={key:mapping.get(key,key) for key in required};missing=[actual[x] for x in required if actual[x] not in reader.fieldnames]
 if missing:raise BusinessRuleError('Cabeceras faltantes: '+', '.join(missing[:10]))
 rows=[]
 for number,row in enumerate(reader,2):
  if any(len(str(v or ''))>10000 for v in row.values()):raise BusinessRuleError(f'Fila {number} demasiado larga')
  rows.append((number,{key:(row.get(column) or '').strip() for key,column in actual.items()}))
 return rows,used,delim
