from pathlib import Path
import json, shutil, hashlib
out=Path(__file__).resolve().parent
src=out  # bundled public snapshot, independent of the original Downloads directory
out.mkdir(parents=True,exist_ok=True)
w=json.loads((out/'agent_inputs/base/world.json').read_text())
ids={k:{r[f]:i+1 for i,r in enumerate(w[k])} for k,f in [('cast','cast_id'),('locations','location_id'),('equipment_offers','offer_id')]}
date=w['project']['original_date']; locs=ids['locations'];eq=ids['equipment_offers'];cast=ids['cast']
def docid(s): return s.lower()
def q(v):
 if v is None:return 'NULL'
 if isinstance(v,bool):return str(v).lower()
 if isinstance(v,(int,float)):return str(v)
 if isinstance(v,(list,dict)):v=json.dumps(v,ensure_ascii=False)
 return "'"+str(v).replace("'","''")+"'"
def tm(n):return f'{n//60:02}:{n%60:02}'
tables={}
rows=['-- Generated from V3 public inputs. See README.md for the PM-only adapter boundary.']
def ins(table,cols,vals):
 tables.setdefault(table,[]).append(dict(zip(cols.split(),vals)))
 rows.append(f"INSERT INTO {table} ({', '.join(cols.split())}) VALUES ({', '.join(q(v) for v in vals)}) ON CONFLICT DO NOTHING;")
def node(key,typ,label,props):ins('ontology_nodes','node_id type label props',[key,typ,label,props])
def edge(a,rel,b):ins('ontology_edges','src relation dst created_by',[a,rel,b,'seed'])
ins('projects','id name block_budget_cap crew_weekly_hours_used',[1,w['project']['title']+' · V3 오후 블록 시연',600000,28])
ins('shoot_days','id project_id shoot_date call_time data_version notice crew_calls',[1,1,date,'08:00',1,'V3 연결: 오전 S001~S008 유지 / 오후 S009~S024 재계획. 전일 24씬 재배치·전체 비용 검증은 지원 범위 밖입니다.',[{'team':d+'팀','time':'08:00'} for d in ['연출','촬영','조명','동시녹음','미술']]])
for a in w['cast']:
 c=next(c for c in w['cast_calendar'] if c['cast_id']==a['cast_id'] and c['date']==date)
 hist=next((h for h in w['work_history'] if h['person_id']==a['cast_id']),{'days':[]})
 hours=sum(d['work_min'] for d in hist['days'] if d['date']<date)/60
 cid=f"contract-{a['cast_id'].lower()}-v{a['active_contract_version']}"
 ins('actors','id name available_from available_to weekly_hours_used contract_doc_id no_night max_daily_hours manager_phone',[cast[a['cast_id']],a['name'],tm(c['start_min']),tm(c['end_min']),hours,cid,True,c['max_duty_minutes']/60,a['phone_display']])
 node(f"ACTOR:{cast[a['cast_id']]}",'ACTOR',a['name'],dict(a,contractDocId=cid,calendar=c))
 node('CONTRACT:'+cid,'CONTRACT',a['name']+' 계약서',{'docId':cid,'sourceDocId':cid.upper()})
 edge(f"ACTOR:{cast[a['cast_id']]}",'계약','CONTRACT:'+cid)
for l in w['locations']:
 av=next(a for a in l['availability'] if a['date']==date)
 # MIXED is used here only for its interior stage; COVER stays exterior.
 indoor=l['kind'] in ['INT','MIXED'];dist=(sum(x*x for x in l['synthetic_coordinate_km']))**.5
 ins('locations','id name address indoor region open_from open_to permit_from permit_to cost no_fly_zone fit distance_km note',[locs[l['location_id']],l['name'],l.get('address','가상 주소'),indoor,'V3-'+l['location_id'],tm(av['shoot_start_min']),tm(av['shoot_end_min']),tm(av['shoot_start_min']),tm(av['shoot_end_min']),av['incremental_fee_krw'],False,l['creative_fit_score']/100,round(dist,1),l.get('notes','')+' / V3 원본 ID: '+l['location_id']])
 node(f"LOCATION:{locs[l['location_id']]}",'LOCATION',l['name'],l)
for e in w['equipment_offers']:
 available=e['booking_status']=='CONFIRMED' and e['compatibility_group']!='AUDIO_1CH'
 ins('equipment','id name available drone cost',[eq[e['offer_id']],e['name'],available,False,e['incremental_fee_by_date'][date]])
 node(f"EQUIPMENT:{eq[e['offer_id']]}",'EQUIPMENT',e['name'],e)
base=[eq[x] for x in w['original_equipment_offer_ids']]
for code,start,end,lid in [('AM','09:00','11:00','LOC-EXT'),('PM','13:00','17:00','LOC-INT')]:
 ins('blocks','shoot_day_id code start_time end_time duration_min location_id equipment_ids',[1,code,start,end,120 if code=='AM' else 240,locs[lid],base])
for s in w['scenes']:
 block='AM' if s['int_ext']=='EXT' else 'PM'
 ins('scenes','code shoot_day_id block_code title duration_min outdoor_intent location_id actor_ids sort',[s['scene_id'],1,block,s['title'],s['duration_minutes'],s['int_ext']=='EXT',None,[cast[x] for x in s['cast_ids']],s['scene_number']])
 node('SCENE:'+s['scene_id'],'SCENE',s['title'],s)
 for a in s['cast_ids']:edge('SCENE:'+s['scene_id'],'출연',f'ACTOR:{cast[a]}')
 edge('SCENE:'+s['scene_id'],'촬영지',f"LOCATION:{locs[s['original_location_id']]}")
 for eid in base:edge('SCENE:'+s['scene_id'],'사용',f'EQUIPMENT:{eid}')
# App options are explicitly adapted PM bundles, NOT V3's whole-day PLAN-1/2/3.
options=[('LOC-INT',base,'13:00','17:00'),('LOC-STUDIO',[eq[x] for x in ['CAM-B','LIGHT-BASE','SOUND-BASE','GRIP-BASE','POWER-BASE']],'13:00','17:00'),('LOC-HUB',[eq[x] for x in ['CAM-BASE','LIGHT-B','SOUND-BASE','GRIP-BASE','POWER-BASE']],'13:00','17:00')]
for i,(lid,gear,start,end) in enumerate(options,1):
 ins('plan_options','shoot_day_id block_code option_no location_id equipment_ids equipment_fit start_time end_time',[1,'PM',i,locs[lid],gear,1,start,end])
 node(f'PLAN:{i}','PLAN',f'V3 오후 어댑터 {i}안',{'adapter':True,'locationId':lid,'sourceFullDayPlan':False})
 edge(f'PLAN:{i}','포함',f'LOCATION:{locs[lid]}')
ins('callsheet_versions','shoot_day_id version_no proposal_id pm_location_id pm_equipment_ids pm_start pm_end pm_cost',[1,1,None,locs['LOC-INT'],base,'13:00','17:00',0])
for l in w['locations']:
 for h in range(8,19):ins('weather_forecasts','shoot_day_id location_id hour precip_prob',[1,locs[l['location_id']],h,0])
ins('reservations','id shoot_day_id location_id start_time end_time status provider',['V3-LOC-INT',1,locs['LOC-INT'],'08:00','18:00','HELD','OURPLACE'])
node('PROJECT:1','PROJECT',w['project']['title'],{'source':w['project'],'adapterScope':'fixed AM; replan PM only','notSupported':['whole-day reordering','full V3 cost/score/approval semantics','external fourth location','safety stop workflow']})
(out/'data.sql').write_text('\n'.join(rows)+'\n')
# DB read-only original snapshots make case injection and reset reproducible.
(out/'data.sql').write_text((out/'data.sql').read_text()+'''
CREATE TABLE IF NOT EXISTS v3_actor_seed AS SELECT * FROM actors;
CREATE TABLE IF NOT EXISTS v3_location_seed AS SELECT * FROM locations;
CREATE TABLE IF NOT EXISTS v3_equipment_seed AS SELECT * FROM equipment;
CREATE TABLE IF NOT EXISTS v3_weather_seed AS SELECT * FROM weather_forecasts;
''')
manifest={'source_sha256':hashlib.sha256((out/'agent_inputs/base/world.json').read_bytes()).hexdigest(),'source_version':w['project']['schema_version'],'date':date,'ids':ids,'changing_scenes':[s['scene_id'] for s in w['scenes'] if s['int_ext']=='INT'],'fixed_scenes':[s['scene_id'] for s in w['scenes'] if s['int_ext']=='EXT'],'scope':'PM_ADAPTER_NOT_FULL_V3_EVALUATION'}
(out/'app_snapshot.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2)+'\n')
(out/'mapping.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
# Export only allowed public regulation/contract documents to the MCP corpus.
corpus=out/'corpus';corpus.mkdir(exist_ok=True)
for d in json.loads((src/'agent_inputs/rag/documents.json').read_text()):
 if not d.get('index_in_rag'):continue
 did=docid(d['doc_id']);kind='CONTRACT' if did.startswith('contract-') else 'LAW' if did.startswith('law-') else 'PERMIT' if did.startswith('permit-') else 'SAFETY' if 'safety' in did else 'POLICY'
 body=(src/d['path']).read_text()
 (corpus/(did+'.md')).write_text(f"---\ndoc_id: {did}\ntitle: {d['title']}\ndoc_type: {kind}\nversion: v{d['version']}\n---\n\n"+body)
print('Created V3 public fixture, SQL, mapping and',len(list(corpus.glob('*.md'))),'RAG documents')
