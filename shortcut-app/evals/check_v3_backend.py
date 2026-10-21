"""Actual DB/backend checks only; does not call the Agent or change its eval criteria."""
from __future__ import annotations
import json,os
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo
import httpx

ROOT=Path(__file__).resolve().parent.parent

def main():
    settings={}
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k,v=line.split('=',1);settings[k.strip()]=v.strip().strip('\"\'')
    token=os.environ.get('INTERNAL_TOKEN') or settings['INTERNAL_TOKEN']
    base=os.environ.get('SHORTCUT_URL','http://localhost:18880')
    rows=[]
    with httpx.Client(base_url=base,headers={'X-Internal-Token':token},timeout=30) as api:
        def call(method,path,**kw):
            r=api.request(method,path,**kw);r.raise_for_status();return r.json() if r.content else None
        def setup(name):
            call('POST','/internal/test/reset');call('POST','/internal/test/v3/case',json={'name':name})
        def evaluate(extras=None):
            return call('POST','/internal/plans/evaluate',json={'shootDayId':1,'extraConstraints':extras or []})
        def feasible(result):return [x for x in result['candidates'] if x['feasible']]
        def check(name,fn):
            try:
                detail=fn();rows.append({'check':name,'ok':True,'detail':detail})
            except Exception as e:rows.append({'check':name,'ok':False,'error':str(e)})
        def baseline():
            setup('baseline');info=call('GET','/internal/test/v3/info');assert info['scenes']==24 and info['dataset']=='V3',info
            auth=call('POST','/api/auth/login',json={'username':'manager','password':'shortcut1234'})
            board=call('GET','/api/board/today',headers={'Authorization':'Bearer '+auth['accessToken']})
            assert board['shootDay']['date']=='2026-10-23',board['shootDay']
            blocks={b['code']:b for b in board['blocks']};assert len(blocks['AM']['scenes'])==8 and len(blocks['PM']['scenes'])==16
            assert sum(s['durationMin'] for b in blocks.values() for s in b['scenes'])==360
            return {'scenes':24,'date':board['shootDay']['date'],'fixedScenes':8,'changingScenes':16}
        check('V3 실제 시드·콜시트 연결',baseline)
        def selected(fixture,lid,extras=None,has_camera=None):
            setup(fixture);r=evaluate(extras);valid=feasible(r);assert valid,'no feasible candidate'
            best=valid[0];assert best['location']['id']==lid,best
            gear=[e['id'] for e in best['equipment']['items']]
            if has_camera is not None: assert has_camera in gear and 1 not in gear,gear
            return {'location':best['location']['name'],'locationId':lid,'equipmentIds':gear,'cost':best['cost'],'feasibleCount':r['feasibleCount']}
        check('소음 시 LOC-STUDIO 대체',lambda:selected('noise',4))
        check('장소 제외 제약 적용 시 LOC-HUB 대체',lambda:selected('noise',6,[{'type':'EXCLUDE_LOCATION','locationId':4}]))
        check('카메라 고장 시 실제 CAM-B 선택',lambda:selected('camera_failure',2,has_camera=2))
        check('카메라 A 제외 제약 적용',lambda:selected('noise',4,[{'type':'EXCLUDE_EQUIPMENT','equipmentId':1}],has_camera=2))
        def none(fixture,extras=None):
            setup(fixture);r=evaluate(extras);assert r['feasibleCount']==0,r;return {'feasibleCount':0}
        check('추가비 10만원 제한 시 후보 없음',lambda:none('noise',[{'type':'MAX_EXTRA_COST','amount':100000}]))
        check('실내 세 곳 사용 불가 시 후보 없음',lambda:none('no_interiors'))
        check('야외 완료 후 비 예보 시 기존 실내 유지',lambda:selected('rain_after_exteriors',2))
        def boundary():
            setup('baseline');r=evaluate();version=r['dataVersion'];results=[]
            for lid,gear,start,end in [(8,[1,4,7,10,12],'13:00','17:00'),(2,[1,4,9,10,12],'13:00','17:00'),(2,[1,4,7,10,12],'13:30','17:30')]:
                result=call('POST','/internal/plans/validate',json={'shootDayId':1,'dataVersion':version,'candidate':{'locationId':lid,'equipmentIds':gear,'start':start,'end':end}})
                assert not result['valid'],result;results.append([v['code'] for v in result['violations']])
            return {'rejectedViolationCodes':results}
        check('금지 장소·비호환 음향·시간 이탈 차단',boundary)
        def reset():
            setup('camera_failure');call('POST','/internal/test/reset');state=call('GET','/internal/shoot-days/1/availability')
            assert next(e for e in state['equipment'] if e['id']==1)['available']
            setup('noise');call('POST','/internal/test/reset');state=call('GET','/internal/shoot-days/1/availability')
            assert time.fromisoformat(next(l for l in state['locations'] if l['id']==2)['openTo'])==time(18,0)
            return {'equipmentRestored':True,'locationRestored':True}
        check('사건 초기화·가용 상태 복원',reset)
        def ontology():
            data=call('GET','/internal/ontology/impact',params={'nodeId':'EQUIPMENT:1','depth':1})
            scenes=[n for n in data['nodes'] if n['type']=='SCENE'];assert len(scenes)==24,len(scenes);return {'impactedScenes':len(scenes)}
        check('카메라와 24씬 영향 관계 연결',ontology)
        call('POST','/internal/test/reset')
    report={'kind':'ACTUAL_BACKEND_DB_CHECK_NOT_AGENT_EVAL','executedAt':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'baseUrl':base,'passed':sum(r['ok'] for r in rows),'total':len(rows),'checks':rows,'agentEvalStatus':'NOT_RUN_REQUIRES_OPENAI_API_KEY'}
    out=ROOT/'outputs';out.mkdir(exist_ok=True)
    (out/'v3_backend_actual.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# V3 실제 DB·백엔드 평가',f"\n통과: {report['passed']}/{report['total']}",'\nAgent/LLM 평가 결과가 아닙니다. API 키 미설정으로 Agent 9개 시나리오는 미실행입니다.','\n| 검사 | 결과 | 상세 |','|---|---|---|']
    for row in rows:lines.append('| '+row['check']+' | '+('PASS' if row['ok'] else 'FAIL')+' | '+json.dumps(row.get('detail',row.get('error')),ensure_ascii=False).replace('|','/')+' |')
    (out/'v3_backend_actual.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':raise SystemExit(main())
