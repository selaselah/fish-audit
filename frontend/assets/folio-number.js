// Mark the changed substring while preserving the full printed identifier on each side.
function printedNumberDifference(printed, other) {
  const value=Array.from(printed), compare=Array.from(other);
  let start=0,end=0;
  while (start<value.length && start<compare.length && value[start]===compare[start]) start++;
  while (end<value.length-start && end<compare.length-start && value[value.length-end-1]===compare[compare.length-end-1]) end++;
  const number=document.createElement('bdi'), difference=document.createElement('mark');
  number.className='folio-number'; difference.textContent=value.slice(start,value.length-end).join('');
  number.append(value.slice(0,start).join(''),difference,value.slice(value.length-end).join(''));
  return number;
}
