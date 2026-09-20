import hashlib
from .tools import Observation

def supplied_observation(case, source):
    url = str(source.url)
    id = "e-manual-" + hashlib.sha256((url + "\n" + source.text).encode()).hexdigest()[:20]
    return Observation(id=id, evidence_type="osint", title=source.title, description=source.text,
        source_type="analyst_supplied_public_web", source_url=url, source_identifier=url,
        raw_data={"excerpt": source.text, "fetched": False, "verified": False}, reproducible=False,
        linked_entity_ids=[e.id for e in case.entities if (e.value.lower() in source.text.lower() if e.chain == "ethereum" else e.value in source.text)])
