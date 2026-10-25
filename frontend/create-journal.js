// Tab-local recovery of an explicitly confirmed command, never credentials.
// The backend still validates ownership, quote and idempotency on every retry.
const prefix='cloudhub.create.pending.v1:';
export function createJournal({storage,owner}){
  const key=()=>{const identity=owner();return identity?prefix+identity:null;};
  return {
    read(){try{const name=key(),value=name&&storage?.getItem(name);if(!value)return null;const record=JSON.parse(value);return record?.version===1&&typeof record.key==='string'&&record.request&&record.state?record:null;}catch{return null;}},
    write(value){const name=key();if(!name)throw Error('CREATE_JOURNAL_UNAVAILABLE');try{const raw=JSON.stringify({version:1,...value});storage.setItem(name,raw);if(storage.getItem(name)!==raw)throw Error();}catch{throw Error('CREATE_JOURNAL_UNAVAILABLE');}},
    clear(){try{const name=key();if(name)storage?.removeItem(name);}catch{/* Replaying an already accepted command remains safe. */}}
  };
}
