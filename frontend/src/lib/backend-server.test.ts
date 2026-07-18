import assert from "node:assert/strict";
import test from "node:test";

import { BackendError, backendFetchWithAuthorization } from "./backend.ts";

test("server backend client forwards the bearer token to the configured API",{concurrency:false},async()=>{
  const originalFetch=globalThis.fetch;const originalUrl=process.env.NEXT_PUBLIC_API_BASE_URL;
  let seen:{url?:string;authorization?:string;method?:string}={};
  process.env.NEXT_PUBLIC_API_BASE_URL="https://api.example.test";
  globalThis.fetch=async(input,init)=>{seen={url:String(input),authorization:new Headers(init?.headers).get("Authorization")??undefined,method:init?.method??"GET"};return new Response(JSON.stringify({connections:[]}),{status:200,headers:{"Content-Type":"application/json"}});};
  try {await backendFetchWithAuthorization("/api/broker/connections","Bearer test-token");}
  finally {globalThis.fetch=originalFetch;if(originalUrl===undefined)delete process.env.NEXT_PUBLIC_API_BASE_URL;else process.env.NEXT_PUBLIC_API_BASE_URL=originalUrl;}
  assert.deepEqual(seen,{url:"https://api.example.test/api/broker/connections",authorization:"Bearer test-token",method:"GET"});
});

test("server backend client classifies HTTP failures",{concurrency:false},async()=>{
  const originalFetch=globalThis.fetch;const originalUrl=process.env.NEXT_PUBLIC_API_BASE_URL;
  process.env.NEXT_PUBLIC_API_BASE_URL="https://api.example.test";
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:"missing"}),{status:404,headers:{"Content-Type":"application/json"}});
  try {await assert.rejects(backendFetchWithAuthorization("/api/missing","Bearer token"),(error)=>error instanceof BackendError&&error.category==="not_found");}
  finally {globalThis.fetch=originalFetch;if(originalUrl===undefined)delete process.env.NEXT_PUBLIC_API_BASE_URL;else process.env.NEXT_PUBLIC_API_BASE_URL=originalUrl;}
});
