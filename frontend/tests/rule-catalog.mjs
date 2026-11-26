import assert from 'node:assert/strict';
import {size,inspect} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const ids=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')].map(e=>e.value)';
export async function checkRuleCatalog(ctx) {
  const {root,call,evaluate,wait}=ctx, policy=await (await fetch(root+'/api/controls')).json();
  const initial=root+'/app#rules?rule=H02&source=receipt';
  const getSource=q('.catalog-sources select'), search=q('.catalog-search input'), current=q('.catalog-detail');
  const option=q('.catalog-compact'), active=q('.catalog-row[aria-selected=true]');
  const input=(control,value)=>evaluate(control+'.value='+JSON.stringify(value)+';'+control+'.dispatchEvent(new Event("input"))');
  const change=(control,value)=>evaluate(control+'.value='+JSON.stringify(value)+';'+control+'.dispatchEvent(new Event("change"))');
  await call('Page.navigate',{url:initial});
  await wait(current+'?.dataset.record==="H02"','catalog H02');
  assert.equal(await evaluate(q('.catalog-release')+'.textContent'),'当前规则 '+policy.version);
  assert.deepEqual(await evaluate(ids('.catalog-sources option')),policy.rule_sources.H02);
  for (const width of [1440,1024,820,768,390,320]) {
    await size(ctx,width);
    await change(getSource,'receipt');
    assert.equal(await evaluate(q('.catalog-locator')+'.textContent'),policy.sources.receipt.locator+' · '+policy.sources.receipt.edition);
    assert.equal(await evaluate(q('.catalog-official')+'.href'),policy.sources.receipt.url);
    await evaluate(q('.catalog-step[aria-label="下一条制度出处"]')+'.click()');
    assert.equal(await evaluate(getSource+'.value'),policy.rule_sources.H02[policy.rule_sources.H02.indexOf('receipt')+1]);
    await evaluate(q('.catalog-step[aria-label="上一条制度出处"]')+'.click()');
    assert.equal(await evaluate(getSource+'.value'),'receipt');
    assert.equal(await evaluate(q('.catalog-scope p')+'.textContent'),policy.sources.receipt.scope);
    assert.equal(await evaluate('document.querySelectorAll(".catalog-source-detail").length'),1);
    await inspect(ctx,width,'#catalog','rule-directory');
    await change(getSource,'acceptance-roles');
    assert.equal(await evaluate(q('.catalog-official')+'.href'),policy.sources['acceptance-roles'].url);
    if (width<=740) {
      await change(option,'H03');
      assert.equal(await evaluate(current+'.dataset.record'),'H03');
      await change(option,'H02');
    } else {
      await evaluate(active+'.focus()');
      await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown'});
      await call('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowDown',code:'ArrowDown'});
      assert.equal(await evaluate(current+'.dataset.record'),'H03');
      await evaluate(q('.catalog-row:nth-child(2)')+'.click()');
    }
  }
  await input(search,'H02 验收');
  assert.equal(await evaluate(option+'.options.length'),1);
  assert.equal(await evaluate(current+'.dataset.record'),'H02');
  await call('Page.reload',{});
  await wait(search+'?.value==="H02 验收"','saved filter');
  await input(search,'无此审计程序987');
  assert.equal(await evaluate(option+'.options.length'),0);
  assert.equal(await evaluate(q('.catalog-empty')+'.textContent'),'没有匹配的项目。');
  await evaluate(q('.catalog-detail .text-button')+'.click()');
  assert.equal(await evaluate(option+'.options.length'),policy.rules.length);
  await evaluate(q('.catalog-modes [data-mode=source]')+'.click()');
  assert.equal(await evaluate(option+'.options.length'),Object.keys(policy.sources).length);
  await change(option,'receipt');
  assert.equal(await evaluate(q('.catalog-official')+'.href'),policy.sources.receipt.url);
  await change(q('.catalog-detail > select'),'H02');
  assert.equal(await evaluate(getSource+'.value'),'receipt');
  assert.equal(await evaluate('Team.route().params.get("rule")'),'H02');
  assert.equal(await evaluate('Team.route().params.get("source")'),'receipt');
  await call('Page.navigate',{url:root+'/app#rules?rule=H02&source=unregistered-source'});
  await wait(q('.catalog-source-body .catalog-empty')+'?.getClientRects().length','unmapped source');
  assert.equal(await evaluate('Boolean('+q('.catalog-official')+')'),false);
  await change(getSource,'receipt');
  assert.equal(await evaluate(q('.catalog-official')+'.href'),policy.sources.receipt.url);
  console.log('PASS · '+policy.rules.length+' procedures, '+Object.keys(policy.sources).length+' sources, search, saved selection, reverse lookup and six viewports');
}
