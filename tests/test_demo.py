import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, Mock
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import demo
import manifests
import run_scaling
from summarize import summarize
from workloads import WORKLOADS
class WorkloadTests(unittest.TestCase):
    def test_each_manifest_prepares_two_separate_e6_pods(self):
        self.assertEqual(set(WORKLOADS), {'rtl'})
        images=set()
        for kind in WORKLOADS:
            m=manifests.manifest(kind);job=m['items'][2];pod=job['spec']['template']['spec'];container=pod['containers'][0]
            self.assertEqual(job['spec']['parallelism'],2)
            self.assertEqual(pod['nodeSelector']['node.kubernetes.io/instance-type'],'VM.Standard.E6.Flex')
            self.assertTrue(pod['affinity']['podAntiAffinity']['requiredDuringSchedulingIgnoredDuringExecution'])
            self.assertEqual(container['resources']['limits']['cpu'],'2')
            self.assertEqual(container['resources']['limits']['memory'],'4Gi')
            images.add(container['image'])
            self.assertEqual(next(e['value'] for e in container['env'] if e['name']=='DEMO_WORKLOAD'),kind)
        self.assertEqual(len(images),1)

    def test_actual_runner_exposes_nonzero_test_failure(self):
        import os
        env={**os.environ,'TOTAL_TESTS':'1','SHARDS':'1','JOB_COMPLETION_INDEX':'0','SIM_COMMAND_JSON':json.dumps([sys.executable,'-c','raise SystemExit(7)'])}
        p=subprocess.run([sys.executable,str(ROOT/'benchmark/runner.py')],env=env,capture_output=True,text=True)
        self.assertEqual(p.returncode,1)
        records=[json.loads(l[len('POC_RESULT '):]) for l in p.stdout.splitlines() if l.startswith('POC_RESULT ')]
        self.assertFalse(summarize(records,1)['success'])

    def test_summary_rejects_timeouts_and_duplicate_coverage(self):
        good={'event':'test','test_id':0,'exit_code':0,'started_unix':1,'elapsed_seconds':1,'timed_out':False}
        self.assertTrue(summarize([good],1)['success'])
        self.assertFalse(summarize([good,good],1)['success'])
        self.assertFalse(summarize([{**good,'timed_out':True}],1)['success'])

    def test_batch_rejects_success_records_without_correctness_marker(self):
        record={'event':'test','test_id':0,'exit_code':0,'started_unix':1,'elapsed_seconds':1,'timed_out':False}
        shard={'pod':'pod-a','returncode':0,'stdout':'POC_RESULT '+json.dumps(record),'stderr':'','records':[record]}
        with tempfile.TemporaryDirectory() as d, patch.object(run_scaling,'run_shard',return_value=shard):
            with self.assertRaisesRegex(RuntimeError,'failed batch'):
                run_scaling.batch('ns',['pod-a'],1,1,'test',3,Path(d)/'batch',['true'])

class ControllerTests(unittest.TestCase):
    def test_each_demo_completes_correct_schedule_and_records_workload(self):
        for kind,cfg in WORKLOADS.items():
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                resources={s:{'cpu':'2','memory':'4Gi'} for s in ('requests','limits')}
                pods={'items':[{'metadata':{'name':f'pod-{i}'},'spec':{'nodeName':f'node-{i}','containers':[{'resources':resources}]},'status':{'conditions':[{'type':'Ready','status':'True'}],'containerStatuses':[{'imageID':'image@sha256:fixed'}]}} for i in range(2)]}
                nodes={'items':[{'metadata':{'name':f'node-{i}','labels':{'node.kubernetes.io/instance-type':'VM.Standard.E6.Flex'}}} for i in range(2)]}
                def checked(argv,payload=None):
                    if 'get' in argv and 'pods' in argv:return json.dumps(pods)
                    if 'get' in argv and 'nodes' in argv:return json.dumps(nodes)
                    if 'sha256sum' in argv:return 'aaa /config/runner.py\nbbb /config/second-file\nccc /config/third-file\nddd /work/binary\n'
                    if 'logs' in argv:return 'setup complete'
                    return 'consistent packages'
                scheduled=[]
                def batch(namespace,pod_names,tests,cycles,run_id,timeout,path,command):
                    scheduled.append((len(pod_names),tests,cycles,command))
                    path.mkdir()
                    return {'run_id':run_id,'workers':len(pod_names),'success':True,'simulation_window_seconds':20/len(pod_names)}
                with patch.object(run_scaling,'checked',side_effect=checked),patch.object(run_scaling,'batch',side_effect=batch),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(run_scaling.main(['--workload',kind,'--output',directory]),0)
                result=json.loads(next(Path(directory).glob('*/comparison.json')).read_text())
                self.assertEqual(result['workload_id'],kind)
                self.assertEqual(result['two_worker_speedup'],2)
                self.assertEqual(result['work_units_per_test'],cfg['cycles'])
                self.assertEqual(len(scheduled),7)
                self.assertEqual(scheduled[0][2],cfg['warmup'])
                self.assertEqual([x[0] for x in scheduled[1:]],[1,2,2,1,1,2])
                self.assertTrue(all(x[3]==cfg['command'] for x in scheduled))

class OperatorTests(unittest.TestCase):
    def nodes(self,count=2):
        return {'items':[{'metadata':{'name':f'n{i}'},'status':{'conditions':[{'type':'Ready','status':'True'}]}} for i in range(count)]}

    def test_prepare_fails_on_wrong_cluster_before_apply(self):
        with patch.object(demo,'kubectl',return_value=json.dumps(self.nodes(0))) as call:
            with self.assertRaisesRegex(RuntimeError,'exactly two'):
                demo.prepare()
            self.assertEqual(call.call_count,1)
            self.assertIn('get',call.call_args[0][0])

    def test_run_refuses_existing_lock_without_relaunch(self):
        pods={'items':[{'status':{'conditions':[{'type':'Ready','status':'True'}]}}]*2}
        with tempfile.TemporaryDirectory() as d,patch.object(demo,'HOME_RESULTS',Path(d)),patch.object(demo,'ready_nodes'),patch.object(demo,'kubectl',return_value=json.dumps(pods)),patch.object(demo.subprocess,'Popen') as popen:
            (Path(d)/'.active').mkdir()
            with self.assertRaisesRegex(RuntimeError,'run lock'):
                demo.start(detach=True)
            popen.assert_not_called()

    def test_start_detaches_controller_and_saves_session(self):
        pods={'items':[{'status':{'conditions':[{'type':'Ready','status':'True'}]}}]*2}
        with tempfile.TemporaryDirectory() as d,patch.object(demo,'HOME_RESULTS',Path(d)),patch.object(demo,'ready_nodes'),patch.object(demo,'kubectl',return_value=json.dumps(pods)),patch.object(demo.subprocess,'Popen',return_value=Mock(pid=1234)) as popen,contextlib.redirect_stdout(io.StringIO()):
            demo.start(detach=True)
            kw=popen.call_args.kwargs
            self.assertTrue(kw['start_new_session']);self.assertEqual(kw['stdin'],subprocess.DEVNULL)
            path=Path(json.loads((Path(d)/'latest.json').read_text())['session'])
            self.assertTrue((path/'status.json').exists());self.assertTrue((path/'controller.log').exists())
            self.assertEqual(json.loads((Path(d)/'.active/owner.json').read_text())['pid'],1234)

    def test_watch_streams_new_progress_once_and_exits_on_completion(self):
        import os
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()) as output:
            p=Path(d);demo.write_json(p/'status.json',{'state':'running','pid':os.getpid()})
            (p/'controller.log').write_text('WARMUP_UNIQUE\n')
            def complete(_):
                with (p/'controller.log').open('a') as f:f.write('PASS_UNIQUE\n')
                demo.write_json(p/'status.json',{'state':'complete','exit_code':0})
            with patch.object(demo.time,'sleep',side_effect=complete),patch.object(demo.subprocess,'Popen') as launch:
                self.assertEqual(demo.watch(p),0)
                launch.assert_not_called()
            self.assertEqual(output.getvalue().count('WARMUP_UNIQUE'),1)
            self.assertEqual(output.getvalue().count('PASS_UNIQUE'),1)

    def test_watch_ctrl_c_keeps_run_state_and_does_not_signal_worker(self):
        import os
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()) as output:
            p=Path(d);demo.write_json(p/'status.json',{'state':'running','pid':os.getpid()})
            with patch.object(demo.time,'sleep',side_effect=KeyboardInterrupt),patch.object(demo,'alive',return_value=True),patch.object(demo.os,'kill') as signal:
                self.assertEqual(demo.watch(p),0)
                signal.assert_not_called()
            self.assertEqual(json.loads((p/'status.json').read_text())['state'],'running')
            self.assertIn('background benchmark was not stopped',output.getvalue())

    def test_watch_returns_failure_and_never_remeasures(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            p=Path(d);demo.write_json(p/'status.json',{'state':'failed','exit_code':7})
            with patch.object(demo.subprocess,'Popen') as launch:
                self.assertEqual(demo.watch(p),7);launch.assert_not_called()

    def test_run_attaches_live_view_by_default(self):
        pods={'items':[{'status':{'conditions':[{'type':'Ready','status':'True'}]}}]*2}
        with tempfile.TemporaryDirectory() as d,patch.object(demo,'HOME_RESULTS',Path(d)),patch.object(demo,'ready_nodes'),patch.object(demo,'kubectl',return_value=json.dumps(pods)),patch.object(demo.subprocess,'Popen',return_value=Mock(pid=1234)) as launch,patch.object(demo,'watch',return_value=0) as monitor,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(demo.start(),0)
            monitor.assert_called_once()
            self.assertEqual(monitor.call_args.kwargs['process'],launch.return_value)
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertIn('-u',launch.call_args.args[0])

    def test_worker_failure_retains_evidence_without_retry(self):
        with tempfile.TemporaryDirectory() as d,patch.object(demo,'HOME_RESULTS',Path(d)),patch.object(demo.subprocess,'call',return_value=7) as call,contextlib.redirect_stdout(io.StringIO()):
            p=Path(d)/'session';p.mkdir();(p/'evidence.log').write_text('preserve')
            self.assertEqual(demo.worker(p),7)
            self.assertEqual(json.loads((p/'status.json').read_text())['state'],'failed')
            self.assertEqual((p/'evidence.log').read_text(),'preserve');self.assertEqual(call.call_count,1)

    def test_success_export_retains_raw_evidence_and_summary(self):
        with tempfile.TemporaryDirectory() as d,patch.object(demo,'HOME_RESULTS',Path(d)),contextlib.redirect_stdout(io.StringIO()):
            p=Path(d)/'session';p.mkdir();raw=p/'run';raw.mkdir();(raw/'comparison.json').write_text('{"success":true}');(raw/'test.log').write_text('PASS')
            with patch.object(demo.subprocess,'call',return_value=0):self.assertEqual(demo.worker(p),0)
            self.assertEqual(json.loads((p/'status.json').read_text())['state'],'complete')
            demo.export(p)
            with tarfile.open(p.with_suffix('.tar.gz')) as t:
                self.assertIn('session/run/test.log',t.getnames());self.assertIn('session/comparison.json',t.getnames())

    def test_cleanup_targets_selected_job_not_shared_namespace(self):
        with tempfile.TemporaryDirectory() as d,patch.object(demo,'HOME_RESULTS',Path(d)),patch.object(demo,'JOB',WORKLOADS['rtl']['job']),patch.object(demo,'kubectl',return_value='') as call,contextlib.redirect_stdout(io.StringIO()):
            demo.cleanup()
            self.assertEqual(call.call_count,2)
            for args in call.call_args_list:
                argv=args[0][0];self.assertIn('eda-e6-rtl-workers',argv[4]);self.assertNotIn('namespace',argv)

class DistributionTests(unittest.TestCase):
    def test_packages_have_sources_and_no_tenancy_state(self):
        downloads=ROOT/'docs/downloads'
        with ZipFile(downloads/'oke-e6-stack.zip') as z:
            self.assertIsNone(z.testzip());self.assertIn('schema.yaml',z.namelist())
            tf='\n'.join(z.read(n).decode() for n in z.namelist() if n.endswith('.tf'))
            self.assertNotIn('ocid1.',tf);self.assertNotIn('E5',tf);self.assertNotIn('Ax.Flex',tf)
            self.assertEqual(tf.count('resource "oci_containerengine_node_pool"'),1)
            self.assertFalse(any('tfstate' in n or '.terraform/' in n for n in z.namelist()))
        with ZipFile(downloads/'oke-e6-benchmark.zip') as z:
            for kind in WORKLOADS:self.assertIn(f'e6-oke-demo/benchmark/{kind}-workers.json',z.namelist())
            for f in ('rtl/mac.sv','rtl/tb.sv','runner.py'):self.assertIn('e6-oke-demo/benchmark/'+f,z.namelist())
            self.assertIn('e6-oke-demo/tools/demo.py',z.namelist())
            self.assertNotIn('e6-oke-demo/tools/build.py',z.namelist())
            self.assertEqual([n for n in z.namelist() if n.endswith('-workers.json')], ['e6-oke-demo/benchmark/rtl-workers.json'])

if __name__=='__main__':unittest.main()
