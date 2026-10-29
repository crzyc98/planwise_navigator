import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getNDTAvailableYears, runACPTest, runADPTest, run401a4Test, run415Test } from './api';
beforeEach(()=>vi.stubGlobal('window',{dispatchEvent:vi.fn()}));
afterEach(()=>vi.unstubAllGlobals());
it('forwards selected design for discovery, each test and employee details',async()=>{
 const fetchMock=vi.fn().mockImplementation(()=>Promise.resolve(new Response('{}')));vi.stubGlobal('fetch',fetchMock);
 const design="A & B'";
 await getNDTAvailableYears('w','s',design);await runACPTest('w',['s','t'],2025,true,design);
 await runADPTest('w',['s'],2025,true,false,'prior',design);await run401a4Test('w',['s'],2025,true,false,design);
 await run415Test('w',['s'],2025,true,.95,design);
 for(const [url] of fetchMock.mock.calls) expect(new URL(url,'http://localhost').searchParams.get('plan_design_id')).toBe(design);
 for(const [url] of fetchMock.mock.calls.slice(1)) expect(new URL(url,'http://localhost').searchParams.get('include_employees')).toBe('true');
 expect(new URL(fetchMock.mock.calls[2][0],'http://localhost').searchParams.get('testing_method')).toBe('prior');
});
it('omits a selector for legacy unselected calls',async()=>{
 const fetchMock=vi.fn().mockResolvedValue(new Response('{}'));vi.stubGlobal('fetch',fetchMock);
 await runACPTest('w',['s'],2025);expect(new URL(fetchMock.mock.calls[0][0],'http://localhost').searchParams.has('plan_design_id')).toBe(false);
});
