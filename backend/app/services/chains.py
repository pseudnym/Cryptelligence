"""Case-sensitive Solana identifiers and explicit chain-derived entity IDs."""
import re
from ..models.domain import Entity
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def base58_bytes(value):
    if not isinstance(value, str) or not value or len(value) > 90 or any(c not in ALPHABET for c in value):
        raise ValueError("Invalid base58 identifier")
    number = 0
    for c in value: number = number * 58 + ALPHABET.index(c)
    return b"\0" * (len(value) - len(value.lstrip("1"))) + (number.to_bytes((number.bit_length()+7)//8,"big") if number else b"")

def solana_address(value):
    if len(base58_bytes(value)) != 32: raise ValueError("Solana address must decode to 32 bytes")
    return value

def solana_signature(value):
    if len(base58_bytes(value)) != 64: raise ValueError("Solana signature must decode to 64 bytes")
    return value

def chain_address(value):
    value = value.strip()
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", value): return "ethereum", value.lower()
    return "solana", solana_address(value)

def address_key(value):
    return value.lower() if re.fullmatch(r"0x[a-fA-F0-9]{40,64}", value) else value

def seed_entity(value):
    chain, value = chain_address(value)
    return Entity(id=("eth-" if chain == "ethereum" else "sol-")+value, entity_type="wallet", chain=chain,
                  label=value[:8]+"..."+value[-6:], value=value)

def sol_entity(value, program=False):
    return Entity(id="sol-"+solana_address(value), entity_type="contract" if program else "wallet", chain="solana",
                  label=value[:8]+"..."+value[-6:],value=value,metadata={"program":True} if program else {})

def transfer_statement(tx):
    sender = tx.sender[4:] if tx.sender.startswith(("eth-","sol-")) else tx.sender
    receiver = tx.receiver[4:] if tx.receiver.startswith(("eth-","sol-")) else tx.receiver
    return f"The collected {tx.chain.title()} record {tx.tx_hash} records {tx.amount} {tx.asset} from {sender} to {receiver}."
