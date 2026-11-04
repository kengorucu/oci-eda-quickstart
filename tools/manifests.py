#!/usr/bin/env python3
"""Generate native E6 workload manifests from the distributed source files."""
import json
from pathlib import Path
from workloads import WORKLOADS
ROOT=Path(__file__).resolve().parents[1]
IMAGE='container-registry.oracle.com/os/oraclelinux@sha256:5bee349a258651feacff106744630539156568ff173788563d3727f0338a1941'

def manifest(kind):
    cfg=WORKLOADS[kind];name=cfg['job'];namespace='eda-native-poc'
    labels={'app.kubernetes.io/name':'e6-compute-lab','poc-run':name,'demo-workload':kind}
    data={'runner.py':(ROOT/'benchmark/runner.py').read_text()}
    data.update({'bootstrap.sh':(ROOT/'benchmark/native-bootstrap.sh').read_text(),'mac.sv':(ROOT/'benchmark/rtl/mac.sv').read_text(),'tb.sv':(ROOT/'benchmark/rtl/tb.sv').read_text()})
    env=[{'name':'POC_PREPARE_ONLY','value':'1'},{'name':'DEMO_WORKLOAD','value':kind}]
    container={'name':'simulator','image':IMAGE,'imagePullPolicy':'Always','command':['/bin/bash','/config/bootstrap.sh'],'env':env,'workingDir':'/work','resources':{'requests':{'cpu':'2','memory':'4Gi','ephemeral-storage':'4Gi'},'limits':{'cpu':'2','memory':'4Gi','ephemeral-storage':'12Gi'}},'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['NET_RAW']}},'volumeMounts':[{'name':'config','mountPath':'/config','readOnly':True},{'name':'work','mountPath':'/work'}],'readinessProbe':{'exec':{'command':['/bin/bash','-c','test -f /work/prepared']},'periodSeconds':5,'timeoutSeconds':2}}
    spec={'restartPolicy':'Never','automountServiceAccountToken':False,'nodeSelector':{'compute-family':'e6','workload':'eda-regression','node.kubernetes.io/instance-type':'VM.Standard.E6.Flex','kubernetes.io/arch':'amd64'},'affinity':{'podAntiAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':[{'labelSelector':{'matchLabels':{'poc-run':name}},'topologyKey':'kubernetes.io/hostname'}]}},'securityContext':{'runAsUser':0,'runAsGroup':0,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[container],'volumes':[{'name':'config','configMap':{'name':name+'-files'}},{'name':'work','emptyDir':{'sizeLimit':'4Gi'}}]}
    return {'apiVersion':'v1','kind':'List','items':[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace}},{'apiVersion':'v1','kind':'ConfigMap','immutable':True,'metadata':{'name':name+'-files','namespace':namespace,'labels':labels},'data':data},{'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':namespace,'labels':labels},'spec':{'completionMode':'Indexed','completions':2,'parallelism':2,'backoffLimit':0,'activeDeadlineSeconds':14400,'template':{'metadata':{'labels':labels},'spec':spec}}}]}

def build():
    for kind in WORKLOADS:(ROOT/'benchmark'/f'{kind}-workers.json').write_text(json.dumps(manifest(kind),indent=2)+'\n')
if __name__=='__main__':build()
