"""Offline Solana RPC fixtures: synthetic signatures and amounts, no attribution."""
import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.chains import ALPHABET, solana_address, solana_signature, seed_entity
from app.services.solana_provider import SolanaSettings, SolanaRPCProvider, normalize_transaction
from app.services.ethereum_provider import ProviderError
from app.services.gemini import GeminiSettings
from app.services.gemini_tools import validate_request
from app.schemas.gemini import ToolRequest
from app.services.osint_extraction import exact_match, extract_identifiers
from test_ethereum import A, SETTINGS, normalized, record
from test_mvp import settle
from test_gemini import MockGemini, assessment_output, AI

S = "CxegPrfn2ge5dNiQberUrQJkHCcimeR4VXkeawcFBBka"
def encoded(value, length):
    data = bytes([value])*length
    number = int.from_bytes(data,"big")
    result=""
    while number:
        number, digit=divmod(number,58);result=ALPHABET[digit]+result
    return result
B,C,T1,T2,MINT = [encoded(n,32) for n in range(2,7)]
SIG,SIG2 = encoded(1,64),encoded(2,64)
SYSTEM="11111111111111111111111111111111"
TOKEN="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SOL=SolanaSettings(rpc_url="https://rpc.example/key-secret",max_signatures=3,retries=1)

def tx(signature=SIG,sender=S,receiver=B,version=0):
    return dict(slot=123456,blockTime=1700000000,version=version,
        transaction={"signatures":[signature],"message":{"accountKeys":[{"pubkey":a,"source":"transaction" if i<2 else "lookupTable","signer":i==0} for i,a in enumerate([sender,receiver,SYSTEM,T1,T2,MINT,TOKEN])],
            "instructions":[{"program":"system","programId":SYSTEM,"parsed":{"type":"transfer","info":{"source":sender,"destination":receiver,"lamports":1234567890}}}]}},
        meta={"err":None,"fee":5000,"preBalances":[2_000_000_000,0,0,0,0,0,0],"postBalances":[765427110,1234567890,0,0,0,0,0],
              "preTokenBalances":[],"postTokenBalances":[],"innerInstructions":[]})

def rpc_provider():
    def handler(request):
        body=json.loads(request.content)
        if body["method"]=="getSignaturesForAddress":
            rows=[{"signature":SIG2}] if body["params"][0]==B else [{"signature":SIG}]
            return httpx.Response(200,json={"jsonrpc":"2.0","id":1,"result":rows})
        assert body["method"]=="getTransaction"
        assert body["params"][1]["maxSupportedTransactionVersion"]==0
        signature=body["params"][0]
        result=tx(SIG2,B,C) if signature==SIG2 else tx()
        return httpx.Response(200,json={"jsonrpc":"2.0","id":1,"result":result})
    return SolanaRPCProvider(SOL,httpx.MockTransport(handler),sleeper=lambda _:None)

def client_for(**kwargs):
    return TestClient(create_app(":memory:",ethereum_provider=normalized([(record(),"normal")]),ethereum_settings=SETTINGS,
        solana_provider=rpc_provider(),solana_settings=SOL,**kwargs))

def create(client,seeds=(S,)):
    response=client.post('/investigations',json={"seeds":list(seeds),"mode":"live","question":"Investigate transfers and uncertain cross-chain relationships."})
    assert response.status_code==201,response.text
    return response.json()

def test_addresses_signatures_case_and_invalid_inputs():
    assert solana_address(S)==S
    assert seed_entity(S).value==S and seed_entity(S).chain=="solana"
    assert solana_signature(SIG)==SIG
    for invalid in ["0"*32,"1"*31,"1"*33,"invalid",SIG]:
        with pytest.raises(ValueError): solana_address(invalid)
    assert exact_match(S,S) and not exact_match(S.lower(),S)
    with client_for() as client:
        assert client.post('/investigations',json={"seeds":[S],"mode":"fixture","question":"Why?"}).status_code==422
        assert client.post('/investigations',json={"seeds":[S,S],"mode":"live","question":"Why?"}).status_code==422
        assert client.post('/investigations',json={"seeds":["invalid"],"mode":"live","question":"Why?"}).status_code==422

@pytest.mark.parametrize("version",["legacy",0])
def test_sol_transfer_signature_slot_time_version_and_provenance(version):
    batch=normalize_transaction(tx(version=version),SIG)
    transfer=batch.transactions[0]
    assert transfer.amount==Decimal('1.234567890')
    assert transfer.chain=="solana" and transfer.tx_hash==SIG and transfer.block_number==123456
    assert transfer.sender=="sol-"+S and transfer.receiver=="sol-"+B
    assert transfer.timestamp.tzinfo
    assert batch.observations[0].source_url=='https://explorer.solana.com/tx/'+SIG
    assert batch.observations[-1].raw_data["program_ids"]==[SYSTEM]
    assert "key-secret" not in str(batch)

def test_multiple_spl_inner_instructions_stay_distinct_with_exact_amounts():
    data=tx()
    data['meta']['preTokenBalances']=[dict(accountIndex=3,mint=MINT,owner=S,uiTokenAmount={"amount":"999999999999999999999999","decimals":6}),
                                      dict(accountIndex=4,mint=MINT,owner=B,uiTokenAmount={"amount":"0","decimals":6})]
    instruction={"program":"spl-token","programId":TOKEN,"parsed":{"type":"transferChecked","info":{"source":T1,"destination":T2,"mint":MINT,"tokenAmount":{"amount":"999999999999999999999999","decimals":6}}}}
    data['meta']['innerInstructions']=[{"index":0,"instructions":[instruction,instruction]}]
    batch=normalize_transaction(data,SIG)
    assert len(batch.transactions)==3 and len({t.id for t in batch.transactions})==3
    assert batch.transactions[1].amount==Decimal('999999999999999999.999999')
    assert batch.transactions[1].sender=='sol-'+S
    assert batch.transactions[1].metadata['source_token_account']==T1
    assert batch.transactions[1].asset=='SPL@'+MINT

def test_failed_missing_time_and_balance_changes_never_invent_transfers():
    data=tx();data['meta']['err']={"InstructionError":[0,"failure"]}
    assert not normalize_transaction(data,SIG).transactions
    data=tx();data['blockTime']=None
    batch=normalize_transaction(data,SIG)
    assert not batch.transactions and batch.warnings
    data=tx();data['transaction']['message']['instructions']=[]
    batch=normalize_transaction(data,SIG)
    assert not batch.transactions and batch.observations[-1].raw_data['balance_deltas']

def test_mixed_case_pivot_provenance_and_no_automatic_cross_link():
    with client_for() as client:
        state=settle(client,create(client,[A,S]))
        assert state['investigation']['status']=='AWAITING_ACTION',state.get('error')
        assert {t['chain'] for t in state['transactions']}=={'ethereum','solana'}
        assert not state['relationships']
        assert not any(e['data'].get('kind')=='inference' for e in state['graph']['edges'])
        assert any(n['data']['chain']=='solana' for n in state['graph']['nodes'])
        path='/investigations/'+state['investigation']['id']
        after=settle(client,client.post(path+'/expand',json={'entity_id':'sol-'+B,'direction':'outbound'}).json())
        assert after['revision']==2 and len(after['transactions'])>len(state['transactions'])
        assert client.post(path+'/expand',json={'entity_id':'sol-'+B,'direction':'outbound'}).json()==after
        assert all(e['source_url'].startswith('https://explorer.solana.com') for e in after['evidence'] if e['source_type']=='solana_rpc' and e['source_url'])
        assert not any('attacker' in c['statement'] for c in after['claims'])

def test_add_solana_to_existing_ethereum_case_and_relationship_validation():
    with client_for() as client:
        state=settle(client,create(client,[A]))
        path='/investigations/'+state['investigation']['id']
        result=settle(client,client.post(path+'/seeds',json={'address':S}).json())
        assert result['investigation']['id']==state['investigation']['id'] and result['revision']==2
        assert {t['chain'] for t in result['transactions']}=={'ethereum','solana'}
        body=dict(source_entity_id='eth-'+A,target_entity_id='sol-'+S,evidence_ids=['invented'],statement='Analyst proposes a possible transition; no verified bridge match.')
        assert client.post(path+'/relationships',json=body).status_code==404
        body['evidence_ids']=[result['evidence'][0]['id']]
        related=settle(client,client.post(path+'/relationships',json=body).json())
        relation=related['relationships'][0]
        assert relation['reasoning_category']=='INFERENCE' and len(relation['evidence_ids'])==2
        edge=next(e for e in related['graph']['edges'] if e['data'].get('kind')=='inference')
        assert edge['data']['evidence_ids']==relation['evidence_ids']

@pytest.mark.parametrize('failure',['timeout','rate','rpc_rate','auth','malformed','missing'])
def test_rpc_failures_bounded_sanitized(failure):
    calls=[];sleeps=[]
    def handler(request):
        calls.append(1)
        if failure=='timeout':raise httpx.ReadTimeout('key-secret',request=request)
        if failure=='rate':return httpx.Response(429)
        if failure=='auth':return httpx.Response(403)
        return httpx.Response(200,json={'error':{'code':-32005,'message':'key-secret'}} if failure=='rpc_rate' else {'result':None} if failure=='missing' else ['bad'])
    provider=SolanaRPCProvider(SOL,httpx.MockTransport(handler),sleeper=sleeps.append)
    with pytest.raises(ProviderError) as caught: provider.transaction(SIG)
    assert 'key-secret' not in str(caught.value)
    assert len(calls)==(2 if failure in {'timeout','rate','rpc_rate'} else 1)

def test_solana_osint_identifier_extraction_and_gemini_chain_validation():
    ids=extract_identifiers(S+' '+SIG,'Public source',[])[2]
    assert {'solana_wallet','solana_signature'} <= {i['kind'] for i in ids}
    with client_for() as client:
        state=settle(client,create(client))
        case=client.app.state.orchestrator.get(state['investigation']['id'])
        assert validate_request(case,ToolRequest(capability='trace_solana_outbound',target_id='sol-'+S)).value==S
        with pytest.raises(ValueError): validate_request(case,ToolRequest(capability='trace_outbound',target_id='sol-'+S))
        request=ToolRequest(capability='inspect_solana_transaction',target_id=case.transactions[0].id)
        assert validate_request(case,request).value==SIG

class SolanaGemini(MockGemini):
    def generate(self,task,context,schema,correction=None):
        if task=='plan':
            out={'steps':[dict(title='Inspect Solana activity',investigative_question='What happened on Solana?',reason='Collect actual instructions.',
                request=dict(capability='inspect_solana_address',target_id=context['seed_ids'][0]),expected_evidence_type='blockchain_observation')]}
        else:
            out=assessment_output(context)
            out['candidate_actions'][0]['request']={'capability':'trace_solana_outbound','target_id':'sol-'+B}
        return json.dumps(out),{'totalTokenCount':50}

def test_gemini_solana_plan_tool_execution_and_reanalysis():
    with client_for(gemini_client=SolanaGemini(),gemini_settings=replace(AI,max_auto_steps=1)) as client:
        state=settle(client,create(client))
        assert state['investigation']['status']=='AWAITING_ACTION',state.get('error')
        assert state['plan']['steps'][0]['capability']=='inspect_solana_address'
        assert any(c['reasoning_category']=='FACT' and 'Solana' in c['statement'] for c in state['claims'])
        best=state['analysis']['ranked_actions'][0]
        assert best['action_type']=='trace_solana_outbound'
        result=settle(client,client.post('/investigations/'+state['investigation']['id']+'/actions/'+best['id']+'/execute').json())
        assert result['revision']==2 and len(result['transactions'])==2


def test_missing_execution_status_and_spoofed_token_program_do_not_create_facts():
    data=tx();del data['meta']['err']
    with pytest.raises(ValueError,match='execution status'):normalize_transaction(data,SIG)
    data=tx()
    data['transaction']['message']['instructions']=[{'program':'spl-token','programId':SYSTEM,'parsed':{'type':'transferChecked','info':{'source':S,'destination':B,'mint':MINT,'tokenAmount':{'amount':'1000','decimals':3}}}}]
    assert not normalize_transaction(data,SIG).transactions


def test_gemini_receives_normalized_program_execution_without_raw_rpc():
    from app.services.gemini_context import context_for
    with client_for() as client:
        state=settle(client,create(client))
        case=client.app.state.orchestrator.get(state['investigation']['id'])
        context=context_for(case)
        execution=next(e['execution'] for e in context['evidence'] if 'execution' in e)
        assert execution['program_ids']==[SYSTEM] and execution['status']=='success'
        assert execution['signature']==SIG and execution['slot']==123456
        assert 'accountKeys' not in json.dumps(context) and 'key-secret' not in json.dumps(context)
