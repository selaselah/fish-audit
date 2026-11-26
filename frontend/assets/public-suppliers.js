const PublicSuppliers = (() => {
  let pending;
  function open() {
    const slot=document.getElementById('inspection-supplier');
    if (pending || slot.querySelector('.supplier-card')) return;
    pending=fetch('/assets/supplier-sample.json').then(response=>{
      if (!response.ok) throw new Error('案例暂不可用');
      return response.json();
    }).then(sample=>{
      const units=sample.units.map(unit=>({...unit,rows:unit.rows.map(row=>({...row,open:unit.source.pdf,
        inspect:opener=>!document.dispatchEvent(new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc:unit.source,ref:row.ref,opener}})),
        excerpt:async()=>{
          const image=new Image(); image.alt=''; image.src=row.crop; await image.decode(); return image;
        }
      }))}));
      const pages=sample.pages.map(p=>{
        const u=sample.units.find(unit=>unit.source.source_sha256===p.original_sha256 && unit.source.page_sha256===p.page_sha256);
        return {...p,thumbnail:u.source.image,open:u.source.pdf,
          inspect:opener=>!document.dispatchEvent(new CustomEvent('inspect-sample-line',{cancelable:true,
            detail:{doc:u.source,ref:u.rows[0].ref,opener,scale:'page'}}))};
      });
      slot.replaceChildren(SupplierCard.render({...sample,id:'public-suppliers',units,pages}));
    }).catch(()=>{}).finally(()=>{pending=null;});
  }
  return {open};
})();
