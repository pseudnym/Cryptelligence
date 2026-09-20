"""Bounded Solana JSON-RPC collection; raw RPC stops at normalization."""
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from urllib.parse import urlsplit
import httpx
from .chains import solana_address, solana_signature, sol_entity
from .ethereum_provider import ProviderError
from .tools import ToolResult, Observation
from ..models.domain import TransactionEvent

@dataclass(frozen=True)
class SolanaSettings:
    rpc_url: str = field(default="https://api.mainnet-beta.solana.com", repr=False)
    cluster: str = "mainnet-beta"
    timeout: float = 15
    retries: int = 1
    max_signatures: int = 10
    case_limit: int = 1200
    @classmethod
    def from_env(cls):
        return cls(rpc_url=os.getenv("SOLANA_RPC_URL","https://api.mainnet-beta.solana.com"),
            cluster=os.getenv("SOLANA_CLUSTER","mainnet-beta"),
            timeout=max(1,min(60,float(os.getenv("SOLANA_TIMEOUT_SECONDS","15")))),
            retries=max(0,min(2,int(os.getenv("SOLANA_RETRIES","1")))),
            max_signatures=max(1,min(50,int(os.getenv("SOLANA_MAX_SIGNATURES","10")))),
            case_limit=max(1,min(5000,int(os.getenv("SOLANA_CASE_LIMIT","1200")))))

def source_url(signature, cluster):
    return "https://explorer.solana.com/tx/"+signature+("?cluster="+cluster if cluster != "mainnet-beta" else "")

def normalize_transaction(data, signature, cluster="mainnet-beta"):
    signature = solana_signature(signature)
    if not isinstance(data,dict) or not isinstance(data.get("meta"),dict): raise ValueError("Missing transaction metadata")
    meta = data["meta"]
    if "err" not in meta: raise ValueError("Missing execution status")
    message = data["transaction"]["message"]
    if signature not in data["transaction"]["signatures"]: raise ValueError("Mismatched signature")
    if data.get("version","legacy") not in ("legacy",0): raise ValueError("Unsupported version")
    accounts = [solana_address(a["pubkey"] if isinstance(a,dict) else a) for a in message["accountKeys"]]
    if not accounts: raise ValueError("Missing accounts")
    slot = int(data["slot"])
    if slot < 0: raise ValueError("Invalid slot")
    timestamp = datetime.fromtimestamp(data["blockTime"],timezone.utc) if data.get("blockTime") is not None else None
    success = meta.get("err") is None
    result = ToolResult(entities=[sol_entity(a) for a in accounts])
    url = source_url(signature,cluster)
    base = dict(chain="solana", signature=signature, slot=slot, version=data.get("version","legacy"),
                timestamp=timestamp.isoformat() if timestamp else None, status="success" if success else "failed",
                cluster=cluster, commitment="finalized", source_provider="solana_rpc")
    balances = {}
    for row in meta.get("preTokenBalances",[]) + meta.get("postTokenBalances",[]):
        index = int(row["accountIndex"])
        if not 0 <= index < len(accounts): raise ValueError("Invalid token account index")
        balances[accounts[index]] = dict(mint=solana_address(row["mint"]),decimals=int(row["uiTokenAmount"]["decimals"]),
            owner=solana_address(row["owner"]) if row.get("owner") else None)
    indexed = [("outer-"+str(i), inst) for i,inst in enumerate(message["instructions"])]
    for group in meta.get("innerInstructions") or []:
        indexed += [("inner-"+str(group["index"])+"-"+str(i),inst) for i,inst in enumerate(group["instructions"])]
    programs = set()
    skipped = 0
    for index, inst in indexed:
        program = inst.get("programId")
        if not program and "programIdIndex" in inst: program = accounts[inst["programIdIndex"]]
        if program: programs.add(solana_address(program))
        parsed = inst.get("parsed")
        if not success or not timestamp or not isinstance(parsed,dict): continue
        info = parsed.get("info",{})
        if parsed.get("type") not in {"transfer","transferChecked"}: continue
        try:
            source, destination = solana_address(info["source"]),solana_address(info["destination"])
            metadata = {**base,"instruction_index":index,"program_id":program,"status":"success", "contract_interaction":False}
            if inst.get("program") == "system" and program == "11111111111111111111111111111111":
                raw,decimals,asset,kind = info["lamports"],9,"SOL","normal"
            elif inst.get("program") in {"spl-token","spl-token-2022"} and program in {"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}:
                token = info.get("tokenAmount")
                balance = balances.get(source) or balances.get(destination)
                mint = info.get("mint") or (balance or {}).get("mint")
                if not mint: raise ValueError("Missing token mint")
                decimals = int(token["decimals"] if token else balance["decimals"])
                raw = token["amount"] if token else info["amount"]
                asset,kind = "SPL@"+solana_address(mint),"token"
                metadata.update(source_token_account=source,destination_token_account=destination,mint=mint)
                # RPC token balance owner fields establish account ownership at this
                # transaction, not the real-world identity of a wallet controller.
                source = (balances.get(source) or {}).get("owner") or source
                destination = (balances.get(destination) or {}).get("owner") or destination
            else: continue
            if not str(raw).isdigit() or not 0 <= decimals <= 255: raise ValueError("Invalid amount")
            with localcontext() as ctx:
                ctx.prec = max(100,len(str(raw))+decimals+1)
                amount = Decimal(str(raw)).scaleb(-decimals)
            sender,receiver = sol_entity(source),sol_entity(destination)
            result.entities.extend([sender,receiver])
            metadata.update(record_kind=kind,raw_quantity=str(raw),decimals=decimals)
            tx = TransactionEvent(id="sol-tx-"+signature+"-"+index,chain="solana",tx_hash=signature,
                timestamp=timestamp,sender=sender.id,receiver=receiver.id,asset=asset,amount=amount,block_number=slot,
                protocol=None,metadata=metadata)
            result.transactions.append(tx)
            result.observations.append(Observation(id="e-"+tx.id,evidence_type="blockchain_observation",
                title="Solana parsed transfer: "+asset,description=f"Parsed instruction records {amount} {asset}; no identity attribution.",
                source_type="solana_rpc",source_identifier=tx.id,source_url=url,
                raw_data={"chain":"solana","transaction_id":tx.id,"transaction":tx.model_dump(mode="json"),"source_provider":"solana_rpc"},
                reliability="HIGH",directness="direct",linked_entity_ids=[sender.id,receiver.id]))
        except (ValueError,KeyError,TypeError): skipped += 1
    for program in sorted(programs): result.entities.append(sol_entity(program,True))
    result.entities = list({e.id:e for e in result.entities}.values())
    # Balance changes include fees, rent, swaps and many-party activity. They are
    # recorded as context, never reverse-engineered into invented transfer edges.
    deltas = []
    pre,post = meta.get("preBalances",[]),meta.get("postBalances",[])
    if len(pre)==len(post)==len(accounts):
        deltas = [dict(account=a,lamport_delta=str(int(post[i])-int(pre[i]))) for i,a in enumerate(accounts) if pre[i]!=post[i]][:100]
    result.observations.append(Observation(id="sol-execution-"+signature,evidence_type="blockchain_observation",
        title="Solana execution and program interactions",description="Successful transaction execution." if success else "Failed transaction; no completed transfers inferred.",
        source_type="solana_rpc",source_identifier="solana:"+cluster+":"+signature,source_url=url,
        raw_data={**base,"program_ids":sorted(programs),"balance_deltas":deltas,"fee_lamports":str(meta.get("fee",0)),
                  "normalization_limits":"Parsed system/SPL transfers only; balance deltas are not transfers; no protocol attribution."},
        reliability="HIGH",directness="direct",linked_entity_ids=[e.id for e in result.entities]))
    if not timestamp: result.warnings.append("Missing blockTime: no timestamp or transfer event was fabricated.")
    if skipped: result.warnings.append(f"{skipped} unsupported or incomplete parsed transfers excluded.")
    return result

class SolanaRPCProvider:
    name = "solana_rpc"
    def __init__(self,settings,transport=None,sleeper=time.sleep):
        self.settings,self.transport,self.sleeper=settings,transport,sleeper
    def rpc(self,method,params):
        parsed=urlsplit(self.settings.rpc_url)
        if parsed.scheme != "https" or not parsed.hostname or self.settings.cluster not in {"mainnet-beta","devnet","testnet"}:
            raise ProviderError("configuration","Configure an HTTPS SOLANA_RPC_URL and supported SOLANA_CLUSTER.")
        for attempt in range(self.settings.retries+1):
            try:
                with httpx.Client(timeout=self.settings.timeout,transport=self.transport) as client:
                    response=client.post(self.settings.rpc_url,json={"jsonrpc":"2.0","id":1,"method":method,"params":params})
                if response.status_code in {401,403}: raise ProviderError("authentication","Solana provider denied access. Check SOLANA_RPC_URL configuration.")
                if response.status_code==429 or response.status_code>=500:
                    error=ProviderError("rate_limit","Solana provider is rate limited or unavailable. Retry later.")
                elif response.status_code!=200: raise ProviderError("provider","Solana provider rejected the request.")
                else:
                    try:
                        data=response.json()
                        if not isinstance(data,dict): raise ValueError()
                        if data.get("error"):
                            code=data["error"].get("code")
                            if code in {429,-32005}: error=ProviderError("rate_limit","Solana RPC is busy. Retry later.")
                            else: raise ProviderError("rpc","Solana RPC could not serve this request; history or transaction version may be unavailable.")
                        elif "result" in data: return data["result"]
                        else: raise ValueError()
                    except (ValueError,TypeError,AttributeError): raise ProviderError("malformed","Solana RPC returned malformed JSON.") from None
            except httpx.TimeoutException: error=ProviderError("timeout","Solana RPC timed out. Retry collection.")
            except httpx.HTTPError: error=ProviderError("connection","Solana RPC connection failed.")
            if attempt==self.settings.retries: raise error from None
            self.sleeper(min(4,.5*2**attempt))
    def signatures(self,wallet):
        rows=self.rpc("getSignaturesForAddress",[solana_address(wallet),{"limit":self.settings.max_signatures,"commitment":"finalized"}])
        if not isinstance(rows,list): raise ProviderError("malformed","Solana signature list is malformed.")
        try: return list(dict.fromkeys(solana_signature(row["signature"]) for row in rows[:self.settings.max_signatures]))
        except (ValueError,KeyError,TypeError): raise ProviderError("malformed","Solana signature record is malformed.") from None
    def transaction(self,signature):
        data=self.rpc("getTransaction",[solana_signature(signature),{"encoding":"jsonParsed","maxSupportedTransactionVersion":0,"commitment":"finalized"}])
        if data is None: raise ProviderError("unavailable","Solana transaction is missing from the provider's available history.")
        try: return normalize_transaction(data,signature,self.settings.cluster)
        except (ValueError,KeyError,TypeError,IndexError,OverflowError): raise ProviderError("malformed","Solana transaction could not be normalized; no transfer was invented.") from None
