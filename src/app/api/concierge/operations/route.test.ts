import { beforeEach, expect, it, vi } from 'vitest';
const f = vi.hoisted(() => ({ role:vi.fn(), operations:vi.fn(), status:vi.fn(), query:{} as Record<string,ReturnType<typeof vi.fn>> }));
vi.mock('@/lib/auth/account',()=>({requireRole:f.role,toErrorResponse:()=>Response.json({error:'unauthorized'},{status:401})}));
vi.mock('@/lib/rate-limit',()=>({checkRateLimit:()=>({success:true}),rateLimitResponse:vi.fn(),RATE_LIMITS:{send:{}}}));
vi.mock('@/lib/concierge/bridge',async original=>({...await original<typeof import('@/lib/concierge/bridge')>(),bridgeOperations:f.operations,bridgeStatus:f.status}));
import {GET,POST} from './route';
const account='11111111-1111-4111-8111-111111111111';
const id='22222222-2222-4222-8222-222222222222';
beforeEach(()=>{
 vi.clearAllMocks();
 f.query=Object.fromEntries(['select','eq'].map(k=>[k,vi.fn(()=>f.query)]));
 f.query.in=vi.fn().mockResolvedValue({data:[{id,name:'Bond',phone:'+27 (82) 000-0002'}],error:null});
 f.query.limit=vi.fn().mockResolvedValue({data:[{id,name:'Bond',phone:'+27820000002'}],error:null});
 f.role.mockResolvedValue({accountId:account,userId:account,supabase:{from:()=>f.query}});
 f.operations.mockResolvedValue({jobs:[],campaigns:[]});
 f.status.mockResolvedValue({pursuits:[{pursuit_id:`wacrm:${id}`}]});
});
function req(body:unknown,origin='http://localhost:8316') {return new Request('http://localhost:8316/api/concierge/operations',{method:'POST',headers:{origin},body:JSON.stringify(body)});}
it('requires account identity for status and filters to started opportunities',async()=>{
 const result=await GET(); expect(result.status).toBe(200);
 expect((await result.json()).contacts).toHaveLength(1);
 expect(f.operations).toHaveBeenCalledWith(account);
 expect(f.query.eq).toHaveBeenCalledWith('account_id',account);
});
it('normalizes owned contact snapshots and never trusts client phone',async()=>{
 expect((await POST(req({command:'enroll',campaign_id:account,contact_ids:[id]}))).status).toBe(200);
 expect(f.operations).toHaveBeenCalledWith(account,{command:'enroll',campaign_id:account,contacts:[{id,name:'Bond',phone:'+27820000002',account_id:account}]});
});
it('refuses foreign/missing contacts without dispatch',async()=>{
 f.query.in.mockResolvedValue({data:[],error:null});
 expect((await POST(req({command:'enroll',campaign_id:account,contact_ids:[id]}))).status).toBe(404);
 expect(f.operations).not.toHaveBeenCalled();
});
it('blocks CSRF and unauthorized writes',async()=>{
 expect((await POST(req({command:'tick'},'https://evil.example'))).status).toBe(403);
 expect(f.role).not.toHaveBeenCalled();
 f.role.mockRejectedValue(new Error('viewer'));
 expect((await POST(req({command:'tick'}))).status).toBe(401);
 expect(f.operations).not.toHaveBeenCalled();
});
it.each([null,[],{command:'send'},{command:'tick',account_id:account},{command:'enroll',contacts:[{id}]},{command:'enroll',contact_ids:[id,id]}])('rejects malformed or authority-bearing body %j',async body=>{
 expect((await POST(req(body))).status).toBe(400);expect(f.operations).not.toHaveBeenCalled();
});
it('bounds body size',async()=>{expect((await POST(req({command:'create_campaign',name:'a'.repeat(33000)}))).status).toBe(413);});
