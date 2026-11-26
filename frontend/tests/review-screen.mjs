import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
export async function size(ctx,width) {
  await ctx.call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:950,deviceScaleFactor:1,mobile:width<600});
  await ctx.evaluate('document.fonts.ready.then(()=>true)');
  assert.ok(await ctx.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'horizontal overflow at '+width);
}
export async function inspect(ctx,width,id,name) {
  if (![390,1440].includes(width)) return;
  await ctx.evaluate('document.fonts.ready.then(()=>Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))).then(()=>true)');
  if (process.env.AUDIT_AXE_FILE) {
    await ctx.evaluate(await readFile(process.env.AUDIT_AXE_FILE,'utf8')+'\n;void 0');
    const violations=await ctx.evaluate('axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21a","wcag21aa"]}}).then(r=>r.violations.map(v=>[v.id,v.nodes.map(n=>[n.target,n.failureSummary])]))');
    assert.deepEqual(violations,[],name+' at '+width);
  }
  if (process.env.AUDIT_UI_SHOTS) {
    await ctx.evaluate(q(id)+'.scrollIntoView({block:"center",behavior:"instant"})');
    const image=await ctx.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'-'+width+'.png'),Buffer.from(image.data,'base64'));
  }
}
