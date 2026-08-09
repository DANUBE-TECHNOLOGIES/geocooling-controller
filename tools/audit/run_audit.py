#!/usr/bin/env python3
from __future__ import annotations
import ast, hashlib, json, os, re, subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')
OUT = ROOT / 'audits' / f'enterprise-{STAMP}'
IGNORE = {'.git','.next','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.venv','venv','backups','audits','dist','build','coverage'}
SRC = {'.py','.ts','.tsx','.js','.jsx','.mjs','.cjs','.sh','.yaml','.yml','.json','.toml','.sql'}
TERMS = ('brain','weather','thermal','predict','learning','adaptive','intelligence','histor','runtime','hardware','mqtt','modbus','safety','controller','autopilot','forecast','simulation','digital','condensation')
ROUTE_RE = re.compile(r'@\s*(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']', re.I)
PREFIX_RE = re.compile(r'APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', re.S)
API_RES = [re.compile(r'fetch\s*\(\s*[`"\']([^`"\']+)'), re.compile(r'axios\.(?:get|post|put|patch|delete)\s*\(\s*[`"\']([^`"\']+)'), re.compile(r'[`"\'](/api/[^`"\' ?]+)')]
ENV_RES = [re.compile(r'os\.getenv\(\s*["\']([^"\']+)["\']'), re.compile(r'os\.environ(?:\.get)?\(\s*["\']([^"\']+)["\']'), re.compile(r'process\.env\.([A-Z0-9_]+)'), re.compile(r'process\.env\[\s*["\']([^"\']+)["\']\s*\]')]

def cmd(args:list[str], timeout:int=30)->dict[str,Any]:
    try:
        r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=timeout,check=False)
        return {'returncode':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr.strip()}
    except Exception as e:
        return {'returncode':999,'stdout':'','stderr':str(e)}

def files(suffixes:set[str]|None=None):
    for current,dirs,names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORE]
        for name in names:
            p=Path(current)/name
            if suffixes is None or p.suffix in suffixes: yield p

def rel(p:Path)->str:
    return str(p.relative_to(ROOT))

def text(p:Path)->str:
    try:return p.read_text(encoding='utf-8')
    except UnicodeDecodeError:return p.read_text(encoding='utf-8',errors='replace')
    except Exception:return ''

def digest(p:Path)->str:
    try:return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:return ''

def mlist(values:list[str],limit:int=100)->str:
    if not values:return '_Aucun._'
    out='\n'.join(f'- `{v}`' for v in values[:limit])
    return out + (f'\n- … {len(values)-limit} autre(s)' if len(values)>limit else '')

def mtable(headers:list[str],rows:list[list[Any]])->str:
    if not rows:return '_Aucune donnée._'
    out=['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']
    out += ['| '+' | '.join(str(v).replace('|','\\|') for v in row)+' |' for row in rows]
    return '\n'.join(out)

OUT.mkdir(parents=True,exist_ok=False)
py=sorted(files({'.py'})); front=sorted(files({'.ts','.tsx','.js','.jsx','.mjs','.cjs'})); source=sorted(files(SRC))
git={'branch':cmd(['git','branch','--show-current']),'status':cmd(['git','status','--short']),'commit':cmd(['git','log','-1','--pretty=%H%n%s%n%ci']),'remote':cmd(['git','remote','-v'])}
docker={'containers':cmd(['docker','ps','--format','{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}']),'compose':cmd(['docker','compose','config','--services'])}
syntax=[]; classes=[]; functions=[]; imports={}; modules={}; routes=[]; prefixes={}
for p in py:
    r=rel(p); t=text(p); mod=r.removesuffix('.py').replace('/','.')
    if '.app.' in mod:mod=mod.split('.app.',1)[1]
    if mod.endswith('.__init__'):mod=mod.removesuffix('.__init__')
    modules[mod]=r
    m=PREFIX_RE.search(t)
    if m:prefixes[r]=m.group(1)
    for x in ROUTE_RE.finditer(t):routes.append({'method':x.group(1).upper(),'path':x.group(2),'prefix':prefixes.get(r,''),'file':r,'line':t[:x.start()].count('\n')+1})
    try:tree=ast.parse(t,filename=r)
    except SyntaxError as e:syntax.append({'file':r,'line':e.lineno,'message':e.msg});continue
    imp=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):imp.extend(a.name for a in n.names)
        elif isinstance(n,ast.ImportFrom) and n.module:imp.append(n.module)
        elif isinstance(n,ast.ClassDef):classes.append({'name':n.name,'file':r,'line':n.lineno})
        elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):functions.append({'name':n.name,'file':r,'line':n.lineno})
    imports[r]=sorted(set(imp))
all_imports={i for vals in imports.values() for i in vals}
orphans=[]
for mod,r in modules.items():
    if mod.rsplit('.',1)[-1] in {'main','config','settings','models','schemas','database','dependencies'}:continue
    if not any(i==mod or i.startswith(mod+'.') or mod.startswith(i+'.') for i in all_imports):orphans.append({'module':mod,'file':r})
class_groups=defaultdict(list)
for c in classes:class_groups[c['name']].append(c)
dup_classes={k:v for k,v in class_groups.items() if len(v)>1}
pages=[]; components=[]; calls=[]
for p in front:
    r=rel(p); t=text(p)
    if re.search(r'/src/app/.+/page\.(tsx|ts|jsx|js)$','/'+r):pages.append(r)
    if '/components/' in '/'+r:components.append(r)
    seen=set()
    for pattern in API_RES:
        for m in pattern.finditer(t):
            v=m.group(1)
            if v not in seen:seen.add(v);calls.append({'path':v,'file':r,'line':t[:m.start()].count('\n')+1})
backend=set()
for r in routes:
    pre=r['prefix'].rstrip('/'); path=r['path']; backend.add((pre+path) if pre else path)
frontend={c['path'].split('?',1)[0] for c in calls if c['path'].startswith('/')}
unused=[]
for route in sorted(backend):
    expected='/api'+route if route.startswith('/geocooling') else route
    if not any(expected.startswith(c) or c.startswith(expected) for c in frontend):unused.append(route)
missing=[]
for c in sorted(frontend):
    if c.startswith('/api/geocooling'):
        expected=c.removeprefix('/api')
        if not any(expected.startswith(r) or r.startswith(expected) for r in backend):missing.append(c)
interesting=defaultdict(list)
for p in py+front:
    r=rel(p); low=r.lower()
    for term in TERMS:
        if term in low:interesting[term].append(r)
env_usage=defaultdict(list)
for p in source:
    t=text(p); r=rel(p)
    for pattern in ENV_RES:
        for m in pattern.finditer(t):env_usage[m.group(1)].append(r)
env_files=sorted(p for p in ROOT.rglob('.env*') if p.is_file() and not any(part in IGNORE for part in p.parts))
configured=defaultdict(list)
for p in env_files:
    for line in text(p).splitlines():
        s=line.strip()
        if s and not s.startswith('#') and '=' in s:
            key=s.split('=',1)[0].strip()
            if key:configured[key].append(rel(p))
configured_unused=sorted(set(configured)-set(env_usage)); used_unconfigured=sorted(set(env_usage)-set(configured)); dup_env={k:v for k,v in configured.items() if len(set(v))>1}
hashes=defaultdict(list)
for p in source:
    d=digest(p)
    if d:hashes[d].append(rel(p))
exact=[v for v in hashes.values() if len(v)>1]
backups=sorted(rel(p) for p in ROOT.rglob('*') if p.is_file() and ('.bak' in p.name or p.name.endswith('~')) and not any(part in IGNORE for part in p.parts))
large=[]
for p in py+front:
    n=len(text(p).splitlines())
    if n>=600:large.append({'file':rel(p),'lines':n})
large.sort(key=lambda x:x['lines'],reverse=True)
tests=sorted(rel(p) for p in py+front if p.name.startswith('test_') or p.name.endswith('_test.py') or '.test.' in p.name or '.spec.' in p.name or '/tests/' in '/'+rel(p))
critical=[]; warnings=[]
if syntax:critical.append(f'{len(syntax)} erreur(s) de syntaxe Python')
if git['status']['stdout']:warnings.append('Arbre Git non propre')
if orphans:warnings.append(f'{len(orphans)} module(s) Python potentiellement orphelin(s)')
if dup_classes:warnings.append(f'{len(dup_classes)} nom(s) de classe dupliqué(s)')
if missing:warnings.append(f'{len(missing)} appel(s) frontend sans route backend évidente')
if dup_env:warnings.append(f'{len(dup_env)} variable(s) d’environnement définie(s) dans plusieurs fichiers')
if backups:warnings.append(f'{len(backups)} fichier(s) de sauvegarde dans le dépôt')
if not tests:warnings.append('Aucun test automatisé détecté')
status='BLOCKED' if critical else 'REVIEW' if warnings else 'READY'; score=max(0,100-len(critical)*30-len(warnings)*6)
report={'generated_at':datetime.now(timezone.utc).isoformat(),'status':status,'score':score,'git':git,'docker':docker,'inventory':{'python_files':len(py),'frontend_files':len(front),'frontend_pages':len(pages),'frontend_components':len(components),'classes':len(classes),'functions':len(functions),'routes':len(routes),'frontend_api_calls':len(calls),'tests':len(tests)},'critical':critical,'warnings':warnings,'syntax_errors':syntax,'interesting_modules':interesting,'routes':routes,'frontend_api_calls':calls,'possibly_unused_backend_routes':unused,'possibly_missing_backend_routes':missing,'possible_orphan_modules':orphans,'duplicate_classes':dup_classes,'environment':{'configured_unused':configured_unused,'used_unconfigured':used_unconfigured,'duplicate_keys':dup_env},'exact_duplicate_files':exact,'backup_files':backups,'large_files':large,'test_files':tests}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
route_rows=[]
for r in routes:
    pre=r['prefix'].rstrip('/'); full=(pre+r['path']) if pre else r['path']; route_rows.append([r['method'],full,r['file'],r['line']])
dup_rows=[[name,len(items),'<br>'.join(f"`{i['file']}:{i['line']}`" for i in items)] for name,items in sorted(dup_classes.items())]
md=f'''# Audit Enterprise GeoCooling

**Date :** {report['generated_at']}  
**Statut :** **{status}**  
**Score indicatif :** **{score}/100**  
**Mode :** analyse statique et lecture seule

## Résumé

| Élément | Résultat |
|---|---:|
| Fichiers Python | {len(py)} |
| Fichiers frontend | {len(front)} |
| Pages frontend | {len(pages)} |
| Composants frontend | {len(components)} |
| Classes Python | {len(classes)} |
| Fonctions Python | {len(functions)} |
| Routes FastAPI | {len(routes)} |
| Appels API frontend | {len(calls)} |
| Tests détectés | {len(tests)} |

## Anomalies critiques

{mlist(critical)}

## Avertissements

{mlist(warnings)}

## Git

**Branche :** `{git['branch']['stdout'] or 'Inconnue'}`

**Dernier commit :**

```text
{git['commit']['stdout'] or 'Indisponible'}
```

**État local :**

```text
{git['status']['stdout'] or 'Arbre propre'}
```

## Erreurs Python

{mtable(['Fichier','Ligne','Erreur'],[[i['file'],i['line'],i['message']] for i in syntax])}

## Modules importants détectés
'''
for term in TERMS:
    vals=sorted(interesting.get(term,[]))
    if vals:md+=f'\n### {term}\n\n{mlist(vals)}\n'
md+=f'''\n## Routes backend

{mtable(['Méthode','Route','Fichier','Ligne'],route_rows)}

## Appels API frontend

{mtable(['Chemin','Fichier','Ligne'],[[i['path'],i['file'],i['line']] for i in calls])}

## Routes backend sans consommateur frontend évident

{mlist(unused)}

Certaines routes peuvent être utilisées par Home Assistant, MQTT, des scripts ou des consommateurs externes.

## Appels frontend sans route backend évidente

{mlist(missing)}

## Modules Python potentiellement orphelins

{mtable(['Module','Fichier'],[[i['module'],i['file']] for i in orphans])}

## Classes dupliquées

{mtable(['Classe','Occurrences','Emplacements'],dup_rows)}

## Variables configurées mais non utilisées

{mlist(configured_unused)}

## Variables utilisées mais non configurées

{mlist(used_unconfigured)}

## Variables définies dans plusieurs fichiers

{mtable(['Variable','Fichiers'],[[k,'<br>'.join(f'`{f}`' for f in sorted(set(v)))] for k,v in sorted(dup_env.items())])}

## Fichiers strictement identiques

{mtable(['Groupe','Fichiers'],[[i,'<br>'.join(f'`{f}`' for f in group)] for i,group in enumerate(exact,start=1)])}

## Fichiers de sauvegarde détectés

{mlist(backups)}

## Fichiers source de plus de 600 lignes

{mtable(['Fichier','Lignes'],[[i['file'],i['lines']] for i in large])}

## Tests automatisés

{mlist(tests)}

## Docker

```text
{docker['containers']['stdout'] or docker['containers']['stderr'] or 'Indisponible'}
```

## Conclusion automatique

'''
md += '**BLOQUÉ :** une anomalie critique doit être corrigée avant les essais terrain.\n' if status=='BLOCKED' else '**REVUE NÉCESSAIRE :** aucune erreur critique évidente, mais les avertissements doivent être classés avant la Release Candidate.\n' if status=='REVIEW' else '**PRÊT :** aucune anomalie statique majeure détectée. Les essais dynamiques restent obligatoires.\n'
(OUT/'REPORT.md').write_text(md,encoding='utf-8')
latest=ROOT/'audits'/'latest'
if latest.is_symlink() or latest.exists():latest.unlink()
latest.symlink_to(OUT.name,target_is_directory=True)
print('============================================================');print(' AUDIT ENTERPRISE TERMINÉ');print('============================================================');print();print('Statut :',status);print('Score  :',f'{score}/100');print();print('Critiques      :',len(critical));print('Avertissements :',len(warnings));print();print('Python         :',len(py));print('Frontend       :',len(front));print('Routes backend :',len(routes));print('Appels frontend:',len(calls));print('Tests          :',len(tests));print();print('Rapport :',OUT/'REPORT.md');print('JSON    :',OUT/'report.json')
