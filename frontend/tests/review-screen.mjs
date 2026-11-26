import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
export function browserInput({call,evaluate}) {
  async function key(name) {
    const codes={Escape:27,Enter:13,Tab:9,Space:32,Home:36,End:35,ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40};
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:name==='Space'?' ':name,
      code:name,windowsVirtualKeyCode:codes[name],...(type==='keyDown' && name==='Enter'?{text:'\r'}:{})});
  }
  async function pointAt(control) {
    return evaluate('(()=>{const el='+control+';el.scrollIntoView({block:"nearest",behavior:"instant"});'+
      'const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()');
  }
  async function tap(control) {
    const point=await pointAt(control);
    await call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
    await call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  }
  return {key,pointAt,tap};
}
export async function size(ctx,width) {
  await ctx.call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:950,deviceScaleFactor:1,mobile:width<600});
  await ctx.evaluate('document.fonts.ready.then(()=>true)');
  assert.ok(await ctx.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'horizontal overflow at '+width);
}
export async function accessibility(ctx,name) {
  await ctx.evaluate('document.fonts.ready.then(()=>Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))).then(()=>true)');
  if (process.env.AUDIT_AXE_FILE) {
    await ctx.evaluate(await readFile(process.env.AUDIT_AXE_FILE,'utf8')+'\n;void 0');
    const violations=await ctx.evaluate('axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21a","wcag21aa"]}}).then(r=>r.violations.map(v=>[v.id,v.nodes.map(n=>[n.target,n.failureSummary])]))');
    assert.deepEqual(violations,[],name);
  }
}
export async function inspect(ctx,width,id,name,block='center') {
  if (![390,1440].includes(width)) return;
  await accessibility(ctx,name+' at '+width);
  if (process.env.AUDIT_UI_SHOTS) {
    await ctx.evaluate(q(id)+'.scrollIntoView({block:'+JSON.stringify(block)+',behavior:"instant"})');
    const image=await ctx.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'-'+width+'.png'),Buffer.from(image.data,'base64'));
  }
}
