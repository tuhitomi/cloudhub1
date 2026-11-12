"""Local bounded configuration, pricing, ownership and restore regressions."""
import json,sys,unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.catalog import ACTIVE_TEMPLATES,configuration,configuration_profiles,configuration_key,configuration_verified,environment_configuration,catalog,resolve_configuration
from cloudhub.cost import Estimator
from cloudhub.operating_policy import plan
from cloudhub.service import Service,record
from cloudhub.store import MemoryStore
from cloudhub.errors import HubError
from cloudhub.templates import linux_template
from cloudhub.rds_template import rds_template
from cloudhub.ecs_template import ecs_template
from cloudhub.efs_template import efs_template
from cloudhub.data_template import data_template
from cloudhub.s3_files import objects
from cloudhub.s3_driver import S3Driver,canonical
from test_processors import rates,S
from test_s3 import FakeS3,SETTINGS

POLICY={'mode':'AUTO_RENEW','period_minutes':60,'ending_policy':'BACKUP_RETIRE','budget_limit_milliusd':100000,'confirmed':True}
def cfg(tid):return configuration_profiles(tid)[1]['configuration']
def verified_rates():
    value=rates();value['configuration_verifications']={configuration_key(t,cfg(t)):{'passed':True,'provisioning_checks':2,'backup_restore_verified':True} for t in ACTIVE_TEMPLATES};return value
def service(value=None):return Service(MemoryStore(),clock=lambda:1000,estimator=Estimator(value or verified_rates()),verified=ACTIVE_TEMPLATES,validation=ACTIVE_TEMPLATES,budget_milliusd=1000000, require_quotes=False)

class ConfigurationChoicesTests(unittest.TestCase):
    def test_all_nine_offer_bounded_choices_with_new_files_gate_closed(self):
        rows=catalog(ACTIVE_TEMPLATES)
        self.assertEqual({r['template_id'] for r in rows},ACTIVE_TEMPLATES)
        for row in rows:
            # files (T02/T07), small (T01/T05) and ha (T03/T04) are a third, separately gated profile.
            self.assertEqual(len(row['configuration_options']),3 if row['template_id'] in {'T01','T02','T03','T04','T05','T07'} else 2)
            self.assertTrue(row['configuration_options'][0]['create_enabled'])
            for extra in row['configuration_options'][1:]:self.assertFalse(extra['create_enabled'])
            self.assertEqual(row['configuration_options'][0]['configuration'],configuration(row['template_id']))
    def test_verification_requires_both_construction_paths_and_verified_backup_restore(self):
        key=configuration_key('T01',cfg('T01'))
        for proof in ({'passed':False,'provisioning_checks':2,'backup_restore_verified':True},{'passed':True,'provisioning_checks':1,'backup_restore_verified':True},{'passed':True,'provisioning_checks':True,'backup_restore_verified':True},{'passed':True,'provisioning_checks':2,'backup_restore_verified':False}):
            self.assertFalse(configuration_verified('T01',cfg('T01'),ACTIVE_TEMPLATES,{key:proof}))
        self.assertTrue(configuration_verified('T01',cfg('T01'),ACTIVE_TEMPLATES,{key:{'passed':True,'provisioning_checks':2,'backup_restore_verified':True}}))
        self.assertFalse(configuration_verified('T05',cfg('T05'),ACTIVE_TEMPLATES,{key:{'passed':True,'provisioning_checks':2,'backup_restore_verified':True}}))
    def test_partial_mixed_unknown_types_roles_and_images_rejected(self):
        invalid=[{'data_gib':16},{**cfg('T01'),'data_gib':True},{**cfg('T01'),'root_gib':16.0},
            {**cfg('T01'),'instance_type':'t3.large'},{**cfg('T01'),'role':'admin'},{**cfg('T06'),'image':'arbitrary'},
            {**cfg('T06'),'cpu':512,'memory_mib':512},{**cfg('T07'),'max_files':64,'max_total_bytes':262144}]
        for value in invalid:
            tid='T06' if 'cpu' in value else 'T07' if 'max_files' in value else 'T01'
            with self.assertRaises(HubError):resolve_configuration(tid,value)
    def test_dynamo_decimal_and_legacy_rows_preserve_configuration(self):
        self.assertEqual(environment_configuration({'template_id':'T01'}),configuration('T01'))
        self.assertEqual(resolve_configuration('T01',{k:Decimal(v) if type(v) is int else v for k,v in cfg('T01').items()}),cfg('T01'))
    def test_unverified_configuration_is_rejected_even_when_template_verified(self):
        s=service(rates());body={'template_id':'T01','duration_hours':1,'configuration':cfg('T01')}
        for admin in (False,True):
            with self.assertRaises(HubError) as error:s.create('alice','new-config-denied',body,is_admin=admin)
            self.assertEqual(error.exception.code,'CONFIGURATION_UNVERIFIED')
        with self.assertRaises(HubError):s.create('alice','normal-cannot-validate',{**body,'validation_run':True})
        self.assertEqual(s.create('alice','admin-validation',{**body,'validation_run':True},is_admin=True)['status'],'QUEUED')
    def test_quotes_use_selected_sizes_for_first_renewal_and_retained_storage(self):
        estimator=Estimator(verified_rates())
        for t,line in [('T01','backup'),('T05','backup'),('T02','storage'),('T07','s3_storage'),('T03','db_storage'),('T04','db_storage'),('T06','container'),('T08','root_storage'),('T09','lambda_compute')]:
            old=estimator.estimate(t,1);new=estimator.estimate(t,1,configuration=cfg(t))
            self.assertGreater(Decimal(new['lines'][line]),Decimal(old['lines'][line]))
            self.assertEqual(new['assumptions']['configuration'],cfg(t))
            p=plan(estimator,t,8,POLICY,cfg(t));self.assertEqual(p['configuration'],cfg(t));self.assertEqual(p['renewal_period']['assumptions']['configuration'],cfg(t))
        self.assertEqual(Estimator(verified_rates()).holding('T01','PAUSE',cfg('T01'))['storage_gib']['ebs_gib_month'],'32')
        self.assertEqual(Estimator(verified_rates()).holding('T03','BACKUP_RETIRE',cfg('T03'))['storage_gib']['rds_snapshot_gib_month'],'40')
    def test_create_configuration_persisted_idempotent_and_renewal_does_not_reset_to_default(self):
        s=service();body={'template_id':'T01','estimate_hours':8,'operating_policy':POLICY,'configuration':cfg('T01')}
        op=s.create('alice','configured-create',body);self.assertEqual(s.create('alice','configured-create',body)['operation_id'],op['operation_id'])
        env=s.store.get('E#'+op['environment_id']);self.assertEqual(env['configuration'],cfg('T01'))
        env.update(status='READY',lock=None,deadline=2000,schedule_pending=False);s.save(env)
        expected=s.estimator.estimate('T01',1,renewal=True,backup=False,configuration=cfg('T01'))
        s.renew('alice',env['environment_id'],'configured-renew',{'minutes':60,'confirmed':True})
        env=s.store.get(env['pk']);self.assertEqual(env['last_period_estimate']['total_milliusd'],expected['total_milliusd']);self.assertEqual(env['configuration'],cfg('T01'))
        with self.assertRaises(HubError):s.create('alice','configured-create',{**body,'configuration':configuration('T01')})
    def test_restore_inherits_source_and_rejects_different_or_foreign_configuration(self):
        s=service();rp=record('recovery','rp-config','alice',recovery_point='rp-config',region='ap-southeast-1',template_id='T01',configuration=cfg('T01'),status='AVAILABLE',retain_until=5000)
        s.save(rp)
        body={'template_id':'T01','duration_hours':1,'recovery_point':'rp-config'}
        with self.assertRaises(HubError):s.create('bob','foreign-restore',body)
        with self.assertRaises(HubError) as error:s.create('alice','wrong-restore',{**body,'configuration':configuration('T01')})
        self.assertEqual(error.exception.code,'RECOVERY_CONFIGURATION_MISMATCH')
        op=s.create('alice','inherit-restore',body);self.assertEqual(s.store.get('E#'+op['environment_id'])['configuration'],cfg('T01'))
    def test_generated_resources_use_the_selected_values_and_keep_security(self):
        def env(t):return {'template_id':t,'configuration':cfg(t),'environment_id':'env-'+'a'*24,'owner_id':'alice'}
        settings={**S,'ssh_cidr':'127.0.0.1/32','availability_zone':'ap-southeast-1a'}
        r=linux_template(env('T01'),settings)['Resources'];self.assertEqual(r['DataVolume']['Properties']['Size'],16);self.assertTrue(r['DataVolume']['Properties']['Encrypted'])
        r=linux_template(env('T05'),settings,'snap-owned')['Resources'];self.assertEqual(r['DataVolume']['Properties']['SnapshotId'],'snap-owned');self.assertEqual(r['DataVolume']['Properties']['Size'],16)
        for t in ('T03','T04'):
            r=rds_template(env(t),S)['Resources'];self.assertEqual(r['Database']['Properties']['AllocatedStorage'],'40');self.assertFalse(r['Database']['Properties']['PubliclyAccessible'])
            restored=rds_template(env(t),S,{'db_snapshot_id':'snap-db'})['Resources'];self.assertEqual(restored['Database']['Properties']['DBSnapshotIdentifier'],'snap-db');self.assertNotIn('AllocatedStorage',restored['Database']['Properties'])
        r=ecs_template(env('T06'),S)['Resources'];self.assertEqual((r['Task']['Properties']['Cpu'],r['Task']['Properties']['Memory']),('512','1024'))
        r=efs_template(env('T08'),S)['Resources'];self.assertEqual(r['Node1']['Properties']['BlockDeviceMappings'][0]['Ebs']['VolumeSize'],32)
        r=data_template(env('T09'),S)['Resources'];self.assertEqual(r['ReadFunction']['Properties']['MemorySize'],256)

    def test_backup_retry_preserves_selected_configuration_and_its_estimate(self):
        s=service();created=s.create('alice','retry-config-create',{'template_id':'T01','duration_hours':1,'configuration':cfg('T01')})
        env=s.store.get('E#'+created['environment_id']);env.update(status='READY',lock=None);s.save(env)
        backup=s.command('alice',env['environment_id'],'backup','retry-config-backup')
        env=s.store.get(env['pk']);op=s.store.get('O#'+backup['operation_id'])
        before=env['estimated_committed_milliusd'];env.update(status='ERROR_RETAINED',lock=None)
        op.update(status='FAILED',phase='BACKUP',failed_phase='BACKUP');s.save(env,op)
        retried=s.control_operation('alice',op['operation_id'],'retry','retry-config-action',{})
        fresh=s.store.get('R#'+retried['recovery_point'])
        self.assertEqual(fresh['configuration'],cfg('T01'));self.assertEqual(fresh['configuration_schema'],1)
        expected=s.estimator.estimate('T01',1,configuration=cfg('T01'))['total_milliusd']
        self.assertEqual(s.store.get(env['pk'])['estimated_committed_milliusd']-before,expected)
    def test_expanded_s3_quota_and_restore_manifest_accept_more_than_32_files(self):
        fake=FakeS3();bucket='source';fake.buckets[bucket]={f'f{i}.txt':b'x' for i in range(40)}
        # Fake paginator is not the full provider; exercise the quota through a small page stub.
        class Pages:
            def get_paginator(self,name):return self
            def paginate(self,**kwargs):return [{'Contents':[{'Key':k,'Size':len(v)} for k,v in fake.buckets[bucket].items()]}]
        with self.assertRaises(HubError):objects(Pages(),bucket,SETTINGS)
        self.assertEqual(len(objects(Pages(),bucket,SETTINGS,cfg('T07'))),40)
        driver=S3Driver(SETTINGS,clients={name:object() for name in ('s3','cloudformation','cloudfront','scheduler')})
        rp={'owner_id':'alice','template_id':'T07','configuration':cfg('T07'),'recovery_point':'rp-'+'b'*24,'environment_id':'env-'+'a'*24}
        manifest=canonical({**{k:rp[k] for k in ('owner_id','recovery_point','environment_id')},'files':[{'key':k,'size':1,'sha256':'a'*64} for k in fake.buckets[bucket]]})
        import hashlib;rp['manifest_sha256']=hashlib.sha256(manifest).hexdigest();driver._bytes=lambda *a:(manifest,{})
        self.assertEqual(len(driver._manifest(rp,'alice')),40)

if __name__=='__main__':unittest.main()
