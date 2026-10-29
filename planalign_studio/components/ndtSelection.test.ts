import { expect, it } from 'vitest';
import { combineNDTAvailability, createNDTRequestGate } from './ndtSelection';
it('intersects years across designs and does not borrow an absent population', () => {
 const a = { years: [2024, 2025], default_year: 2025, plan_design_ids: ['A', 'B'] };
 const b = { years: [2025, 2026], default_year: 2026, plan_design_ids: ['B', 'C'] };
 expect(combineNDTAvailability([a,b])).toEqual({years:[2025],designs:['A','B','C']});
 expect(combineNDTAvailability([a,{...b,years:[]}]).years).toEqual([]);
 expect(combineNDTAvailability([])).toEqual({years:[],designs:[]});
});
it('rejects delayed results after A to B to A and newer requests', async () => {
 const gate=createNDTRequestGate(); gate.select('A'); const old=gate.begin();
 let finish!:()=>void; const pending=new Promise<void>(resolve=>{finish=resolve;});
 const shown:string[]=[];
 const response=pending.then(()=>{if(gate.isCurrent(old)) shown.push('old A');});
 gate.select('B');gate.select('A');const current=gate.begin();
 if(gate.isCurrent(current)) shown.push('new A');finish();await response;
 expect(shown).toEqual(['new A']);gate.begin();expect(gate.isCurrent(current)).toBe(false);
});
