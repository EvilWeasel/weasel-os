#!/usr/bin/env python3
"""Optional local Decisions/Responses evaluator. It has NO desktop input/capture tools."""
import argparse
import base64
import decimal
import hashlib
import http.client
import json
import math
import os
import pathlib
import re
import signal
import socket
import socketserver
import sqlite3
import ssl
import stat
import struct
import threading
import time
import uuid

VERSION='1.0'
MODEL='gpt-6-luna'
HOST='api.openai.com'
MAX_CALLS=200
MAX_BUDGET_MICROUSD=10_000_000
RESERVE_MICROUSD=50_000  # $0.05 retained for every dispatched request, even unknown failures.
MAX_TEXT_BYTES=8192
MAX_INSTRUCTIONS_BYTES=2048
MAX_IMAGE_BYTES=2_000_000
MAX_IMAGE_PIXELS=1_150_000
MAX_RESPONSE_BYTES=65536
PRICE_SOURCE='https://developers.openai.com/api/docs/guides/decisions'
GENERAL_PRICE_SOURCE='https://developers.openai.com/api/docs/pricing'
NAME=re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')

class Refusal(Exception):
    def __init__(self,code): self.code=code


def finite_probability(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
        raise Refusal('invalid_provider_probability')
    return float(value)


def bounded_text(value,limit,code):
    if not isinstance(value,str) or not value.strip() or len(value.encode('utf-8'))>limit:
        raise Refusal(code)
    return value


def validate_question(raw):
    if not isinstance(raw,dict) or set(raw)-{'type','name','instructions','choices'}:raise Refusal('invalid_question')
    kind=raw.get('type');name=raw.get('name','ui_state')
    if kind not in {'predicate','choice'} or not isinstance(name,str) or not NAME.fullmatch(name):raise Refusal('invalid_question')
    q={'type':kind,'name':name,'instructions':bounded_text(raw.get('instructions'),MAX_INSTRUCTIONS_BYTES,'invalid_instructions')}
    if kind=='choice':
        choices=raw.get('choices')
        if not isinstance(choices,list) or not 2<=len(choices)<=16:raise Refusal('invalid_choices')
        seen=set();out=[]
        for x in choices:
            if not isinstance(x,dict) or set(x)!={'value','description'}:raise Refusal('invalid_choices')
            value=x.get('value')
            if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',value) or value in seen:raise Refusal('invalid_choices')
            seen.add(value);out.append({'value':value,'description':bounded_text(x.get('description'),256,'invalid_choice_description')})
        q['choices']=out
    elif 'choices' in raw:raise Refusal('choices_not_allowed_for_predicate')
    return q


def image_dimensions(raw):
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)>=24:
        return 'image/png',*struct.unpack('>II',raw[16:24])
    if raw[:2]==b'\xff\xd8':
        p=2
        while p+4<=len(raw):
            if raw[p]!=255:break
            while p<len(raw) and raw[p]==255:p+=1
            marker=raw[p];p+=1
            if marker in {0xD8,0xD9}:continue
            if p+2>len(raw):break
            n=int.from_bytes(raw[p:p+2],'big')
            if n<2 or p+n>len(raw):break
            if marker in {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF} and n>=7:
                h,w=struct.unpack('>HH',raw[p+3:p+7]);return 'image/jpeg',w,h
            p+=n
    raise Refusal('unsupported_or_invalid_image')


def load_image(path,roots):
    # The caller names an existing PRIVATE capture/crop; this service never captures.
    if not isinstance(path,str) or not path.startswith('/') or len(path)>4096:raise Refusal('invalid_image_path')
    p=pathlib.Path(path).resolve(strict=True)
    allowed=False
    for root in roots:
        info=root.stat()
        if stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and not info.st_mode&0o077 and root in p.parents:allowed=True
    if not allowed:raise Refusal('image_outside_private_capture_roots')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or not 0<info.st_size<=MAX_IMAGE_BYTES:raise Refusal('invalid_image_file')
        raw=os.read(fd,MAX_IMAGE_BYTES+1)
    finally:os.close(fd)
    mime,w,h=image_dimensions(raw)
    if w<=0 or h<=0 or max(w,h)>1568 or w*h>MAX_IMAGE_PIXELS:raise Refusal('image_too_large_use_explicit_crop')
    return f'data:{mime};base64,{base64.b64encode(raw).decode("ascii")}',{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'width':w,'height':h,'mime':mime}


def input_content(text,image_url=None):
    if not image_url:return text
    return [{'role':'user','content':[{'type':'input_text','text':text},{'type':'input_image','image_url':image_url}]}]


def request_body(endpoint,q,text,image_url):
    if endpoint=='decisions':return {'model':MODEL,'input':input_content(text,image_url),'questions':[q]}
    # Same evidence/predicate. Responses generates a probability; Decisions supplies
    # native typed probability. These are not interchangeable calibrated confidences.
    if q['type']=='predicate':
        schema={'type':'object','properties':{'probability':{'type':'number','minimum':0,'maximum':1}},'required':['probability'],'additionalProperties':False}
    else:
        schema={'type':'object','properties':{'choice':{'type':'string','enum':[x['value'] for x in q['choices']]}},'required':['choice'],'additionalProperties':False}
    instructions='Evaluate the supplied evidence only. Do not plan or perform actions. Return the requested JSON object with no explanation.\n'+q['instructions']
    if q['type']=='choice':instructions+='\nAllowed choices: '+json.dumps(q['choices'],ensure_ascii=False)
    return {'model':MODEL,'instructions':instructions,'input':input_content(text,image_url),'max_output_tokens':128,'store':False,'service_tier':'default','text':{'format':{'type':'json_schema','name':'ui_decision','schema':schema,'strict':True}}}


def parse_answer(endpoint,q,response):
    if endpoint=='responses':
        parts=[]
        for item in response.get('output',[]):
            for piece in item.get('content',[]):
                if piece.get('type')=='refusal':raise Refusal('provider_refused')
                if piece.get('type')=='output_text':parts.append(piece.get('text',''))
        if response.get('status')!='completed':raise Refusal('provider_output_incomplete')
        try:x=json.loads(''.join(parts))
        except (ValueError,TypeError):raise Refusal('invalid_provider_answer')
        if q['type']=='predicate':return {'type':'predicate','name':q['name'],'probability':finite_probability(x.get('probability')),'probability_semantics':'generated_by_responses_not_native_decisions'}
        if x.get('choice') not in [z['value'] for z in q['choices']]:raise Refusal('provider_choice_outside_candidates')
        return {'type':'choice','name':q['name'],'choice':x['choice']}
    answers=response.get('answers')
    if not isinstance(answers,list) or len(answers)!=1 or not isinstance(answers[0],dict):raise Refusal('invalid_provider_answer')
    a=answers[0]
    if a.get('type')=='refusal':raise Refusal('provider_refused')
    if a.get('type')!=q['type'] or a.get('name')!=q['name']:raise Refusal('provider_answer_identity_mismatch')
    if q['type']=='predicate':return {'type':'predicate','name':q['name'],'probability':finite_probability(a.get('probability')),'probability_semantics':'native_decisions_estimate'}
    values=[z['value'] for z in q['choices']]
    if a.get('choice') not in values:raise Refusal('provider_choice_outside_candidates')
    probabilities=a.get('probabilities')
    if not isinstance(probabilities,list) or len(probabilities)!=len(values):raise Refusal('invalid_provider_distribution')
    items=[];seen=set()
    for x in probabilities:
        if not isinstance(x,dict) or x.get('value') not in values or x['value'] in seen:raise Refusal('invalid_provider_distribution')
        seen.add(x['value']);items.append({'value':x['value'],'probability':finite_probability(x.get('probability'))})
    if abs(sum(x['probability'] for x in items)-1)>0.02:raise Refusal('invalid_provider_distribution')
    result={'type':'choice','name':q['name'],'choice':a['choice'],'probabilities':items}
    if 'confidence' in a:result['confidence']=finite_probability(a['confidence'])
    return result


def usage_and_estimate(endpoint,response):
    raw=response.get('usage',{});usage={}
    for k in ['input_tokens','output_tokens','total_tokens']:
        v=raw.get(k)
        if isinstance(v,int) and not isinstance(v,bool) and v>=0:usage[k]=v
    if 'input_tokens' not in usage or endpoint=='responses' and 'output_tokens' not in usage:return usage,None
    # Bounded inputs are short context. Record a visible warning if upstream usage
    # ever escapes that assumption; reservations still remain consumed.
    long=usage['input_tokens']>272000
    inp=decimal.Decimal('0.20' if long else '0.10')
    out=decimal.Decimal('0' if endpoint=='decisions' else ('0.75' if long else '0.50'))
    estimate=(inp*usage['input_tokens']+out*usage.get('output_tokens',0))/decimal.Decimal(1000000)
    return usage,str(estimate)


class Ledger:
    def __init__(self,directory,job,max_calls,budget_micro,prior_calls=0):
        directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        info=directory.stat()
        if info.st_uid!=os.getuid() or info.st_mode&0o077:raise Refusal('ledger_directory_not_private')
        path=directory/'ledger.sqlite3'
        if path.is_symlink():raise Refusal('ledger_symlink_refused')
        self.db=sqlite3.connect(path,check_same_thread=False);os.chmod(path,0o600);self.lock=threading.Lock();self.job=job
        self.db.executescript('CREATE TABLE IF NOT EXISTS jobs(job TEXT PRIMARY KEY,max_calls INTEGER,budget_micro INTEGER,prior_calls INTEGER); CREATE TABLE IF NOT EXISTS requests(job TEXT,request_id TEXT,request_hash TEXT,status TEXT,endpoint TEXT,result TEXT,reserved_micro INTEGER,PRIMARY KEY(job,request_id)); CREATE TABLE IF NOT EXISTS halted_jobs(job TEXT PRIMARY KEY,reason TEXT);')
        try:
            with self.db:
                row=self.db.execute('SELECT max_calls,budget_micro,prior_calls FROM jobs WHERE job=?',(job,)).fetchone()
                if row is None:self.db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(job,max_calls,budget_micro,prior_calls))
                elif tuple(row)!=(max_calls,budget_micro,prior_calls):raise Refusal('persisted_job_policy_mismatch')
        except Exception:self.db.close();raise
        self.max_calls=max_calls;self.budget_micro=budget_micro;self.prior_calls=prior_calls

    def snapshot(self):
        with self.lock:
            n,reserved=self.db.execute('SELECT COUNT(*),COALESCE(SUM(reserved_micro),0) FROM requests WHERE job=?',(self.job,)).fetchone()
            halt=self.db.execute('SELECT reason FROM halted_jobs WHERE job=?',(self.job,)).fetchone()
            rows=self.db.execute('SELECT result FROM requests WHERE job=?',(self.job,)).fetchall()
            totals={'input_tokens':0,'output_tokens':0};estimate=decimal.Decimal(0);missing=0
            for row in rows:
                result=json.loads(row[0]) if row[0] else {}
                for key in totals:totals[key]+=result.get('usage',{}).get(key,0)
                if result.get('estimated_cost_usd') is not None:estimate+=decimal.Decimal(result['estimated_cost_usd'])
                else:missing+=1
            return {'job_id':self.job,'calls_reserved':n+self.prior_calls,'max_calls':self.max_calls,'reserved_usd':(reserved+self.prior_calls*RESERVE_MICROUSD)/1e6,'budget_usd':self.budget_micro/1e6,'reservation_per_call_usd':0.05,'actual_billed_usd':None,'documented_price_estimate_usd':str(estimate),'observed_tokens':totals,'missing_usage_calls':missing,'prior_calls_usage_unavailable':self.prior_calls,'automatic_retries':False,'halted':bool(halt),'halt_reason':halt[0] if halt else None}

    def reserve(self,request_id,digest,endpoint):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old=self.db.execute('SELECT request_hash,status,result FROM requests WHERE job=? AND request_id=?',(self.job,request_id)).fetchone()
                if old:
                    if old[0]!=digest:raise Refusal('request_id_payload_conflict')
                    if old[1]=='dispatching':raise Refusal('prior_dispatch_uncertain_do_not_replay')
                    result=json.loads(old[2]);result['cached_receipt']=True;self.db.commit();return result
                if self.db.execute('SELECT 1 FROM halted_jobs WHERE job=?',(self.job,)).fetchone():raise Refusal('job_halted_review_ledger_before_new_requests')
                n,reserved=self.db.execute('SELECT COUNT(*),COALESCE(SUM(reserved_micro),0) FROM requests WHERE job=?',(self.job,)).fetchone()
                if n+self.prior_calls>=self.max_calls or reserved+(self.prior_calls+1)*RESERVE_MICROUSD>self.budget_micro:raise Refusal('job_request_or_budget_cap_reached')
                self.db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',(self.job,request_id,digest,'dispatching',endpoint,None,RESERVE_MICROUSD));self.db.commit();return None
            except BaseException:self.db.rollback();raise

    def complete(self,request_id,result):
        with self.lock,self.db:
            self.db.execute('UPDATE requests SET status=?,result=? WHERE job=? AND request_id=?',('completed',json.dumps(result,separators=(',',':')),self.job,request_id))

    def halt(self,reason):
        with self.lock,self.db:self.db.execute('INSERT OR IGNORE INTO halted_jobs VALUES(?,?)',(self.job,reason))


class HTTPSKeepalive:
    def __init__(self,key):
        if not isinstance(key,str) or not key or any(ord(c)<33 or ord(c)>126 for c in key):raise Refusal('api_key_missing_or_invalid_environment')
        self.key=key;self.connection=None;self.worker=None

    def post(self,endpoint,body,timeout):
        if self.worker is not None and self.worker.is_alive():raise Refusal('previous_transport_pending_no_new_dispatch')
        if self.connection is None:self.connection=http.client.HTTPSConnection(HOST,timeout=timeout,context=ssl.create_default_context())
        connection=self.connection;connection.timeout=timeout
        if connection.sock:connection.sock.settimeout(timeout)
        expired=threading.Event();finished=threading.Event();outcome=[]
        def abort():
            expired.set()
            try:
                if connection.sock:connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        def run():
            try:
                # DNS may outlast socket timeouts. The caller still receives a bounded
                # timeout, and an expired connect must never start a later POST.
                if connection.sock is None:connection.connect()
                if expired.is_set():raise Refusal('provider_request_timeout_billing_uncertain')
                connection.request('POST','/v1/'+endpoint,body=json.dumps(body,separators=(',',':')).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json','Connection':'keep-alive'})
                response=connection.getresponse();status=response.status;raw=response.read(MAX_RESPONSE_BYTES+1)
                if expired.is_set():raise Refusal('provider_request_timeout_billing_uncertain')
                if len(raw)>MAX_RESPONSE_BYTES:raise Refusal('provider_response_too_large_billing_uncertain')
                if status!=200:outcome.append((status,{}))
                else:
                    try:value=json.loads(raw)
                    except (ValueError,UnicodeError):raise Refusal('invalid_provider_json_billing_uncertain')
                    if not isinstance(value,dict):raise Refusal('invalid_provider_json_billing_uncertain')
                    outcome.append((status,value))
            except Exception as error:
                connection.close();self.connection=None;outcome.append(error)
            finally:finished.set()
        self.worker=threading.Thread(target=run,daemon=True);self.worker.start()
        if not finished.wait(timeout):
            abort();self.connection=None;raise Refusal('provider_request_timeout_billing_uncertain')
        if isinstance(outcome[0],Exception):raise outcome[0]
        return outcome[0]


class Service:
    def __init__(self,ledger,transport,image_roots=()):
        self.ledger=ledger;self.transport=transport;self.image_roots=[pathlib.Path(p).resolve(strict=True) for p in image_roots];self.gate=threading.Lock();self.stopping=threading.Event()

    def handle(self,request):
        start=time.monotonic_ns();rid=None;reserved=False
        try:
            if not isinstance(request,dict) or request.get('schema_version')!=VERSION:raise Refusal('unsupported_schema_version')
            op=request.get('op')
            if op=='status':return {'schema_version':VERSION,'status':'ok','capabilities':['predicate','choice'],'model':MODEL,'input_actions':False,'capture_actions':False,'ledger':self.ledger.snapshot()}
            if self.stopping.is_set():raise Refusal('optional_evaluator_stopping_no_dispatch')
            if op not in {'decide','benchmark_responses'}:raise Refusal('unknown_operation')
            q=validate_question(request.get('question'));text=bounded_text(request.get('text'),MAX_TEXT_BYTES,'invalid_evidence_text')
            rid=request.get('request_id') or uuid.uuid4().hex
            for value in [rid,request.get('task_id'),request.get('observation_id')]:
                if not isinstance(value,str) or not NAME.fullmatch(value):raise Refusal('invalid_request_task_or_observation_id')
            timeout_ms=request.get('timeout_ms',8000)
            if isinstance(timeout_ms,bool) or not isinstance(timeout_ms,int) or not 500<=timeout_ms<=15000:raise Refusal('invalid_timeout')
            image_url=None;image_info=None
            if request.get('image_path') is not None:image_url,image_info=load_image(request['image_path'],self.image_roots)
            endpoint='decisions' if op=='decide' else 'responses'
            fingerprint={'question':q,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'image':image_info,'endpoint':endpoint,'observation_id':request['observation_id'],'task_id':request['task_id'],'timeout_ms':timeout_ms}
            digest=hashlib.sha256(json.dumps(fingerprint,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            deadline=start/1e9+timeout_ms/1000
            if not self.gate.acquire(timeout=max(0,deadline-time.monotonic())):raise Refusal('decision_queue_timeout_no_dispatch')
            try:
                if self.stopping.is_set():raise Refusal('optional_evaluator_stopping_no_dispatch')
                old=self.ledger.reserve(rid,digest,endpoint)
                if old:return old
                reserved=True;dispatch=time.monotonic_ns();remaining=deadline-time.monotonic()
                if remaining<=0:raise Refusal('decision_deadline_expired_no_dispatch_reservation_retained')
                code,response=self.transport.post(endpoint,request_body(endpoint,q,text,image_url),remaining)
                done=time.monotonic_ns();usage,estimate=usage_and_estimate(endpoint,response)
                common={'schema_version':VERSION,'request_id':rid,'task_id':request['task_id'],'observation_id':request['observation_id'],'endpoint':endpoint,'model':MODEL,'cached_receipt':False,'http_status':code,'timing':{'requested_monotonic_ns':start,'dispatch_monotonic_ns':dispatch,'response_monotonic_ns':done,'queue_and_preparation_ms':(dispatch-start)/1e6,'api_ms':(done-dispatch)/1e6,'total_ms':(done-start)/1e6},'usage':usage,'estimated_cost_usd':estimate,'actual_billed_usd':None,'price_source':PRICE_SOURCE if endpoint=='decisions' else GENERAL_PRICE_SOURCE,'price_date':'2026-10-09','regional_premium_included':False,'image':image_info,'reservation_retained_usd':0.05,'automatic_retries':False}
                if code!=200:result={**common,'status':'failed','error':'provider_http_error','billing_uncertain':True}
                else:
                    try:answer=parse_answer(endpoint,q,response);result={**common,'status':'ok','answer':answer,'billing_uncertain':estimate is None}
                    except Refusal as e:result={**common,'status':'failed','error':e.code,'billing_uncertain':estimate is None}
                if estimate is not None and decimal.Decimal(estimate)>decimal.Decimal('0.05'):
                    result['status']='uncertain';result['error']='documented_price_estimate_exceeds_reserved_ceiling_stop_job'
                    self.ledger.halt(result['error'])
                self.ledger.complete(rid,result);return result
            finally:self.gate.release()
        except Refusal as error:
            result={'schema_version':VERSION,'status':'uncertain' if reserved else 'failed','request_id':rid,'error':error.code,'billing_uncertain':reserved,'automatic_retries':False,'actual_billed_usd':None}
        except Exception as error:
            # No exception message/repr or upstream body is emitted or persisted.
            result={'schema_version':VERSION,'status':'uncertain' if reserved else 'failed','request_id':rid,'error':'transport_or_validation_failure','error_class':type(error).__name__,'billing_uncertain':reserved,'automatic_retries':False,'actual_billed_usd':None}
        if reserved:self.ledger.complete(rid,result)
        return result


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(18)
        peer=self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
        _,uid,_=struct.unpack('3i',peer)
        if uid!=os.getuid():return
        while True:
            raw=self.rfile.readline(65537)
            if not raw:return
            if len(raw)>65536:return
            try:request=json.loads(raw)
            except (ValueError,UnicodeError):request={}
            result=self.server.service.handle(request)
            self.wfile.write(json.dumps(result,separators=(',',':')).encode()+b'\n');self.wfile.flush()

class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
    def handle_error(self,request,client_address):
        # No traceback, request body, prompt, credential, or exception message.
        print(json.dumps({'status':'failed','error':'local_connection_closed'}),flush=True)


def client_call(path,request,timeout=18):
    raw=json.dumps(request,separators=(',',':')).encode()+b'\n'
    if len(raw)>65536:raise Refusal('local_request_too_large')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout);sock.connect(str(path));sock.sendall(raw);f=sock.makefile('rb');line=f.readline(65537)
        if len(line)>65536:raise Refusal('local_response_too_large')
        return json.loads(line)


def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve');serve.add_argument('--socket',required=True);serve.add_argument('--state-dir',required=True);serve.add_argument('--job-id',required=True);serve.add_argument('--image-root',action='append',default=[]);serve.add_argument('--budget-usd',default='10');serve.add_argument('--max-calls',type=int,default=200);serve.add_argument('--prior-calls',type=int,default=0)
    cli=sub.add_parser('status');cli.add_argument('--socket',required=True)
    args=ap.parse_args()
    if args.command=='status':print(json.dumps(client_call(args.socket,{'schema_version':VERSION,'op':'status'}),indent=2));return
    key=os.environ.pop('OPENAI_API_KEY',None)  # Received only by masked child-process injection.
    budget=int(decimal.Decimal(args.budget_usd)*1_000_000)
    if not 0<budget<=MAX_BUDGET_MICROUSD or not 0<args.max_calls<=MAX_CALLS or not 0<=args.prior_calls<=args.max_calls or not NAME.fullmatch(args.job_id):raise Refusal('invalid_job_policy')
    path=pathlib.Path(args.socket);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    info=path.parent.stat()
    if not path.is_absolute() or info.st_uid!=os.getuid() or info.st_mode&0o077:raise Refusal('socket_parent_not_private')
    # Never replace an existing socket/file, including abandoned generations.
    if path.exists() or path.is_symlink():raise Refusal('socket_exists_resolve_owned_instance_first')
    ledger=Ledger(args.state_dir,args.job_id,args.max_calls,budget,args.prior_calls)
    service=Service(ledger,HTTPSKeepalive(key),args.image_root)
    with Server(str(path),Handler) as server:
        os.chmod(path,0o600);identity=path.stat();server.service=service
        previous_sigterm=signal.getsignal(signal.SIGTERM)
        def stop(signum,frame):
            service.stopping.set()
            threading.Thread(target=server.shutdown,daemon=True).start()
        signal.signal(signal.SIGTERM,stop)
        try:
            print(json.dumps({'schema_version':VERSION,'status':'ready','socket':str(path),'job_id':args.job_id,'input_actions':False}),flush=True)
            server.serve_forever()
        finally:
            service.stopping.set()
            # Finish at most one already-dispatched bounded evaluator receipt before
            # exiting. Crash/forced-kill entries remain dispatching and cannot replay.
            if service.gate.acquire(timeout=16):
                service.gate.release()
                ledger.db.close()
            signal.signal(signal.SIGTERM,previous_sigterm)
            try:
                current=path.lstat()
                if (current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino):path.unlink()
            except FileNotFoundError:pass

if __name__=='__main__':
    try:main()
    except Refusal as error:print(json.dumps({'status':'failed','error':error.code}),flush=True);raise SystemExit(1)
    except KeyboardInterrupt:raise SystemExit(130)
    except Exception as error:print(json.dumps({'status':'failed','error':'startup_failure','error_class':type(error).__name__}),flush=True);raise SystemExit(1)
