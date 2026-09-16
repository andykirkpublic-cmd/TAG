const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const server = spawn(process.env.PYTHON || 'python3',['-m','tests.demo_server'],{env:process.env,stdio:['ignore','pipe','pipe']});
let browser;
const errors=[];
const base='http://localhost:8765';
async function waitFor(fn, label){
  for(let i=0;i<100;i++){if(await fn())return;await new Promise(r=>setTimeout(r,100));}
  throw new Error('Timed out: '+label);
}
async function login(page, role, password){
  await page.goto(base);
  await page.getByLabel('Email address').fill(role+'@example.test');
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in'}).click();
  await page.locator('#compose').waitFor();
}
(async()=>{
  let buffer='';
  const credentials=await new Promise((resolve,reject)=>{
    server.stdout.on('data',part=>{buffer+=part.toString();const line=buffer.split('\n')[0];if(line.endsWith('}'))resolve(JSON.parse(line));});
    server.on('exit',code=>reject(new Error('Demo server exited '+code)));
  });
  await waitFor(async()=>{try{return (await fetch(base+'/healthz')).ok;}catch{return false;}},'server');
  browser=await chromium.launch({headless:true});
  const schoolContext=await browser.newContext({viewport:{width:1440,height:1000}});
  const familyContext=await browser.newContext({viewport:{width:390,height:844}});
  const deviceContext=await browser.newContext({viewport:{width:420,height:940}});
  const school=await schoolContext.newPage(), parent=await familyContext.newPage(), device=await deviceContext.newPage();
  for(const page of [school,parent,device])page.on('pageerror',e=>errors.push(e.message));
  await login(school,'staff',credentials.staff);
  await login(parent,'parent',credentials.parent);
  await school.getByRole('button',{name:'People & devices'}).click();
  await school.getByRole('button',{name:'Generate pairing code'}).click();
  await school.locator('#pair-result code').waitFor();
  const code=await school.locator('#pair-result code').textContent();
  await device.goto(base+'/device');
  await device.getByLabel('8-digit pairing code').fill(code);
  await device.getByRole('button',{name:'Connect this TAG'}).click();
  await device.getByText('You’re all caught up.').waitFor();
  await parent.getByLabel('Message',{exact:true}).fill('Grandad is collecting you at 3:15.');
  await parent.getByRole('button',{name:'Send to TAG'}).click();
  await device.getByText('Grandad is collecting you at 3:15.').waitFor();
  await device.locator('#left').click();
  await parent.getByText('Acknowledged',{exact:true}).waitFor();
  await parent.locator('input[value="QUESTION"]').check();
  await parent.getByLabel('Message',{exact:true}).fill('Would you like to go to the park?');
  await parent.getByRole('button',{name:'Send to TAG'}).click();
  await device.getByText('Would you like to go to the park?').waitFor();
  await device.screenshot({path:'/tmp/tag-device.png',fullPage:true});
  await device.locator('#right').click();
  await parent.getByText('Answered no',{exact:true}).waitFor();
  const left=await device.locator('#left').boundingBox();
  await device.mouse.move(left.x+left.width/2,left.y+left.height/2);
  await device.mouse.down();
  await new Promise(r=>setTimeout(r,3300));
  await device.mouse.up();
  await parent.getByRole('heading',{name:'Sam Taylor needs help.'}).waitFor();
  await school.getByRole('heading',{name:'Sam Taylor needs help.'}).waitFor();
  await parent.getByRole('button',{name:'Mark as seen'}).click();
  await parent.getByText('You’ve seen this',{exact:true}).waitFor();
  assert.equal(await school.getByRole('button',{name:'Mark as seen'}).count(),1);
  await school.getByRole('button',{name:'Overview',exact:false}).click();
  await school.screenshot({path:'/tmp/tag-school.png',fullPage:true});
  await parent.screenshot({path:'/tmp/tag-parent-mobile.png',fullPage:true});
  for(const page of [school,parent,device])assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal page overflow');
  school.once('dialog',dialog=>dialog.accept());
  await school.getByRole('button',{name:'Resolve after checking'}).click();
  await waitFor(async()=>await parent.getByRole('heading',{name:'Sam Taylor needs help.'}).count()===0,'resolved alert');
  await deviceContext.setOffline(true);
  await waitFor(async()=>await device.locator('#device-online').textContent()==='OFFLINE','offline state');
  assert.equal(await device.locator('#left').isDisabled(),true);
  await deviceContext.setOffline(false);
  await waitFor(async()=>await device.locator('#device-online').textContent()==='CONNECTED','reconnection');
  assert.deepEqual(errors,[]);
  console.log('Browser checks passed: login, pairing, NOTICE, QUESTION, long press, independent receipts, resolution, mobile overflow, offline/reconnect; no JavaScript errors.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
