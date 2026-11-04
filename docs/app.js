'use strict';
const reference = {
  success: true, compute_family: 'e6', shape: 'VM.Standard.E6.Flex',
  tests_per_batch: 8, cycles_per_test: 100000000, repeats_per_level: 3,
  median_seconds_by_workers: {'1':240.72565913200378,'2':120.87799763679504}
};
let selectedDemo = 'rtl';
const demos = {
  rtl: {title:'Digital RTL simulation.', description:'Simulate a self-checking SystemVerilog multiply-and-accumulate circuit with Verilator: 100 million clock cycles per test.', limit:'One worker executes all eight tests. Two workers split four each on distinct nodes. Setup, compilation and warm-up are excluded. This small synthetic circuit is not a full chip, analog SPICE or full-node benchmark.', estimate:'The RTL reference run took about 18 minutes, excluding preparation.'},

};
const byId = id => document.getElementById(id);
function validateResult(value) {
  if (!value || value.success !== true || value.compute_family !== 'e6' || value.shape !== 'VM.Standard.E6.Flex') {
    throw new Error('Choose a successful E6 comparison.json produced by this benchmark.');
  }
  for (const key of ['tests_per_batch','cycles_per_test','repeats_per_level']) {
    if (!Number.isSafeInteger(value[key]) || value[key] < 1 || value[key] > 10000000000) throw new Error('Invalid workload settings in the JSON.');
  }
  const m = value.median_seconds_by_workers;
  if (!m || !['1','2'].every(k => typeof m[k] === 'number' && Number.isFinite(m[k]) && m[k] > 0 && m[k] < 10000000)) {
    throw new Error('The file must contain positive median times for one and two workers.');
  }
  const kind=value.workload_id || 'rtl';
  if (kind!==selectedDemo) throw new Error(`This JSON is for ${kind}. Select that demo before loading it.`);
  return value;
}
function metric(id, value, unit) {
  const el = byId(id); el.replaceChildren(document.createTextNode(value));
  const span = document.createElement('span'); span.textContent = unit; el.append(span);
}
function render(value, own) {
  validateResult(value);
  const one = value.median_seconds_by_workers['1']; const two = value.median_seconds_by_workers['2'];
  const speed = one/two; const top = Math.max(one,two);
  metric('metric-one',one.toFixed(2),'s'); metric('metric-two',two.toFixed(2),'s'); metric('metric-speedup',speed.toFixed(2),'×');
  byId('chart-one').textContent = `${one.toFixed(2)} s`; byId('chart-two').textContent = `${two.toFixed(2)} s`;
  byId('bar-one').style.width = `${100*one/top}%`; byId('bar-two').style.width = `${100*two/top}%`;
  byId('efficiency').textContent = `${(speed/2*100).toFixed(2)}% parallel efficiency`;
  const total = value.tests_per_batch*value.repeats_per_level*2;
  byId('pass-count').textContent = `${total} measured executions reported successful`;
  byId('result-badge').textContent = own ? 'YOUR REPORTED RESULT' : 'REFERENCE RUN';
  byId('result-origin').textContent = own ? `${value.tests_per_batch} tests/batch · ${(value.work_units_per_test || value.cycles_per_test).toLocaleString()} ${value.unit_label || 'clock cycles'}/test · ${value.repeats_per_level} repeats` : '3 Nov 2026 · illustrative, not a guarantee';
  byId('runtime-chart').setAttribute('aria-label',`${own?'Your reported':'Reference'} median runtime: one worker ${one.toFixed(2)} seconds, two workers ${two.toFixed(2)} seconds`);
  byId('result-message').textContent = own && selectedDemo==='rtl' && (value.tests_per_batch!==8 || value.cycles_per_test!==100000000 || value.repeats_per_level!==3) ? 'This file uses different workload settings from the reference. Compare scaling within your run.' : '';
}
byId('result-file').addEventListener('change',async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size>1000000) throw new Error('Choose comparison.json (under 1 MB), rather than the raw archive.');
    render(JSON.parse(await file.text()),true);
  } catch (error) { byId('result-message').textContent = error.message; }
});
function emptyResults() {
  ['metric-one','metric-two','metric-speedup'].forEach(id=>byId(id).textContent='—');
  ['chart-one','chart-two'].forEach(id=>byId(id).textContent='Not measured');
  ['bar-one','bar-two'].forEach(id=>byId(id).style.width='0%');
  byId('result-badge').textContent='AWAITING YOUR RUN';byId('result-origin').textContent='No sample timings for this workload';
  byId('efficiency').textContent='Parallel efficiency: pending';byId('pass-count').textContent='Run and export comparison.json';
  byId('runtime-chart').setAttribute('aria-label','No results loaded for this workload');byId('result-message').textContent='';
}
function resetResults() { if(selectedDemo==='rtl') render(reference,false); else emptyResults(); byId('result-file').value=''; }
byId('reset-results').addEventListener('click',resetResults);
for(const card of document.querySelectorAll('[data-demo]')) {
  card.addEventListener('click',()=>{
    selectedDemo=card.dataset.demo;
    for(const c of document.querySelectorAll('[data-demo]')) { c.classList.toggle('selected',c===card);c.setAttribute('aria-pressed',String(c===card)); }
    byId('workload-title').textContent=demos[selectedDemo].title;byId('workload-description').textContent=demos[selectedDemo].description;byId('workload-limit').textContent=demos[selectedDemo].limit;
    byId('run-estimate').textContent=demos[selectedDemo].estimate;
    byId('run-command').textContent=`unzip -o ~/oke-e6-benchmark.zip -d ~/
cd ~/e6-oke-demo
python3 tools/demo.py prepare --demo ${selectedDemo}
python3 tools/demo.py run --demo ${selectedDemo}`;
    byId('cleanup-command').textContent=`cd ~/e6-oke-demo
python3 tools/demo.py cleanup --demo ${selectedDemo}`;
    byId('reset-results').textContent=selectedDemo==='rtl'?'Show reference':'Clear results';resetResults();
  });
}
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(byId(button.dataset.copy).textContent);
      button.textContent='Copied'; setTimeout(()=>button.textContent='Copy',1600);
    } catch (_) { button.textContent='Select text to copy'; }
  });
}
byId('deploy-button').addEventListener('click',event=>{
  if (event.currentTarget.getAttribute('aria-disabled')==='true') {
    event.preventDefault();byId('publishing-note').scrollIntoView({block:'center'});
  }
});
async function configureDeployment() {
  try {
    const response = await fetch('deployment.json'); if (!response.ok) return;
    const config = await response.json();
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(config.repository||'') || !/^[A-Za-z0-9_.-]+$/.test(config.release||'')) return;
    const expected = `https://github.com/${config.repository}/releases/download/${config.release}/oke-e6-stack.zip`;
    if (config.stack_url!==expected) return;
    const url = new URL('https://cloud.oracle.com/resourcemanager/stacks/create');url.searchParams.set('zipUrl',expected);
    byId('deploy-button').href=url.href;byId('deploy-button').setAttribute('aria-disabled','false');
    byId('publishing-note').textContent='Opens OCI Resource Manager with this version’s Terraform package. Review variables and Plan before applying.';
    byId('repo-link').href=`https://github.com/${config.repository}`;byId('repo-link').textContent='Source on GitHub ↗';
  } catch (_) { /* Manual ZIP deployment remains available. */ }
}
render(reference,false);configureDeployment();
