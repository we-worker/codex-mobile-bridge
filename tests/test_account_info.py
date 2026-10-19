import base64
import json
import time
import unittest
from unittest.mock import Mock, call, patch

import test_accounts
from bridge.features.accounts.accounts import private_json


class InfoTests(unittest.TestCase):
    setUp = test_accounts.AccountsTests.setUp
    tearDown = test_accounts.AccountsTests.tearDown

    def official(self):
        claims=base64.urlsafe_b64encode(b'{"sub":"fixture-user","email":"fixture@example.test"}').decode().rstrip('=')
        row={'id':'a'*32,'kind':'chatgpt','name':'Fixture','email':'fixture@example.test','tokenOwner':['org','fixture-user','fixture@example.test']}
        self.manager.index['accounts'].append(row)
        auth={'auth_mode':'chatgpt','tokens':{'account_id':'org','id_token':'e30.'+claims+'.sig','access_token':'access-fixture','refresh_token':'refresh-fixture'}}
        private_json(self.manager.directory(row['id'])/'auth.json',auth)
        return row,auth

    def test_current_detects_imported_api_without_previous_switch_and_tracks_external_changes(self):
        row=self.manager.add_api({'name':'API','baseUrl':'https://fixture.test/v1','apiKey':'private-key','model':'fixture'})['accounts'][0]
        info=self.manager.info
        info.identity={'kind':'api','baseUrl':row['baseUrl'],'key':'private-key','model':'fixture','name':'API · custom'}
        info.stamp=info.source_stamp();info.checked_at=time.time()
        result=self.manager.public()
        self.assertEqual(result['activeId'],row['id']);self.assertEqual(result['current']['name'],'API')
        self.assertNotIn('private-key',json.dumps(result));self.assertIsNone(self.manager.index['activeId'])
        (self.home/'config.toml').write_text('# externally changed')
        self.assertIsNone(self.manager.public()['activeId'])

    def test_current_official_is_matched_by_identity_not_just_email(self):
        row,_=self.official();info=self.manager.info
        info.stamp=info.source_stamp();info.checked_at=time.time()
        info.identity={'kind':'chatgpt','owner':['other-org','fixture-user',row['email']],'name':row['email']}
        self.assertIsNone(self.manager.public()['activeId'])
        info.identity['owner']=row['tokenOwner']
        self.assertEqual(self.manager.public()['activeId'],row['id'])
        with self.assertRaises(ValueError):self.manager.control({'action':'delete','id':row['id']})

    def rpc(self,rate_error=False):
        def request(method,params=None):
            if method=='config/read':return {'config':{}}
            if method=='account/read':return {'requiresOpenaiAuth':True,'account':{'type':'chatgpt','email':'fixture@example.test'}}
            if method=='account/rateLimits/read':
                if rate_error:raise ValueError('raw private upstream body')
                return {'rateLimits':{'primary':{'usedPercent':25,'windowDurationMins':300}},'rateLimitResetCredits':{'availableCount':2}}
            if method=='model/list':return {'data':[{'id':'fixture-model','displayName':'Fixture model'},{'id':'hidden','hidden':True}],'nextCursor':None}
            raise AssertionError(method)
        result=Mock();result.request.side_effect=request;return result

    def test_chatgpt_route_override_uses_native_identity_and_matches_saved_account(self):
        row,auth=self.official();private_json(self.home/'auth.json',auth)
        for config in ({'openai_base_url':'http://127.0.0.1:3425/backend-api/codex'},
                       {'profile':'gateway','profiles':{'gateway':{'openai_base_url':'https://proxy.test/backend-api/codex'}}}):
            with self.subTest(config=config):
                native=self.rpc();request=native.request.side_effect
                native.request.side_effect=lambda method,params: {'config':config} if method=='config/read' else request(method,params)
                with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc:
                    rpc.return_value.__enter__.return_value=native
                    identity=self.manager.info.read_identity()
                self.assertEqual(identity,{'kind':'chatgpt','name':row['email'],'owner':row['tokenOwner'],'login':None})
                self.assertEqual(self.manager.info.match(identity),row)
                native.request.assert_any_call('account/read',{'refreshToken':False})

    def test_openai_route_override_keeps_api_key_or_signed_out_identity(self):
        config={'openai_base_url':'https://proxy.test/v1'}
        private_json(self.home/'auth.json',{'OPENAI_API_KEY':'fixture-key'})
        for account,kind in (({'type':'apiKey'},'api'),(None,'signedOut')):
            native=Mock()
            native.request.side_effect=lambda method,params: {'config':config} if method=='config/read' else {'account':account}
            with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc:
                rpc.return_value.__enter__.return_value=native
                identity=self.manager.info.read_identity()
            self.assertEqual(identity['kind'],kind)
            if kind=='api':
                self.assertEqual(identity['baseUrl'],'https://proxy.test/v1')
                self.assertEqual(identity['key'],'fixture-key')

    def test_explicit_api_definition_does_not_use_leftover_chatgpt_identity(self):
        config={'model_providers':{'openai':{'base_url':'https://api.test/v1','experimental_bearer_token':'fixture-key'}}}
        native=Mock();native.request.return_value={'config':config}
        with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc:
            rpc.return_value.__enter__.return_value=native
            identity=self.manager.info.read_identity()
        self.assertEqual(identity['kind'],'api')
        self.assertEqual(identity['baseUrl'],'https://api.test/v1')
        self.assertEqual(identity['key'],'fixture-key')
        self.assertEqual(native.request.call_args_list, [
            call('config/read',{'includeLayers':False}),
            call('account/read',{'refreshToken':False})])

    def test_inactive_official_usage_models_are_isolated_and_sanitized(self):
        row,_=self.official();before=self.manager.snapshot_files();info=self.manager.info
        info.read_identity=Mock(return_value={'kind':'api','name':'other','key':'unrelated','baseUrl':'https://other.test'})
        with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc, \
             patch('bridge.clients.codex.catalog.Catalog.get_kind', return_value={
                 'models':[{'id':'fixture-model','name':'Fixture model'}],
                 'cache':{'state':'fresh','updatedAt':123}}):
            rpc.return_value.__enter__.return_value=self.rpc()
            info.read(row,'usage');info.read(row,'models')
        result=self.manager.public();data=result['accounts'][0]['details']
        self.assertEqual(data['usage']['limits'][0]['windows'][0]['remainingPercent'],75)
        self.assertEqual(data['usage']['resetCredits']['availableCount'],2)
        self.assertEqual(data['models']['models'],[{'id':'fixture-model','name':'Fixture model'}])
        self.assertEqual(data['models']['cache']['updatedAt'],123)
        self.assertEqual(self.manager.snapshot_files(),before)
        self.assertNotIn('access-fixture',json.dumps(result));self.assertNotIn('refresh-fixture',json.dumps(result))

    def test_saved_official_accounts_use_distinct_native_catalog_homes(self):
        first, _ = self.official()
        second = {**first, 'id':'b'*32, 'email':'second@example.test',
                  'tokenOwner':['other-org','second-user','second@example.test']}
        self.manager.index['accounts'].append(second)
        claims = base64.urlsafe_b64encode(b'{"sub":"second-user","email":"second@example.test"}').decode().rstrip('=')
        private_json(self.manager.directory(second['id'])/'auth.json', {
            'auth_mode':'chatgpt', 'tokens':{'account_id':'other-org', 'id_token':'e30.'+claims+'.sig',
                                            'access_token':'second-access'}})
        info = self.manager.info
        info.read_identity = Mock(return_value={'kind':'api','name':'other'})
        class Native:
            def __init__(self, home): self.home = home
            def __enter__(self): return self
            def __exit__(self, *args): return False
        calls = []
        def catalog(reader, kind, cwd, **kwargs):
            calls.append((reader.home, cwd))
            return {'models':[{'id':reader.home.name}], 'cache':{'state':'fresh','updatedAt':123}}
        with patch('bridge.features.accounts.accounts.ManagedRPC', side_effect=lambda home, runtime: Native(home)), \
             patch('bridge.features.accounts.info.Account.context', side_effect=lambda rpc: {
                 'loginType':'chatgpt', 'email':'second@example.test' if rpc.home.name == second['id'] else first['email']}), \
             patch('bridge.clients.codex.catalog.Catalog.get_kind', new=catalog):
            info.read(first, 'models')
            info.read(second, 'models')
        self.assertEqual(info.entries[first['id']]['models']['models'], [{'id':first['id']}])
        self.assertEqual(info.entries[second['id']]['models']['models'], [{'id':second['id']}])
        self.assertEqual({home for home, _ in calls}, {self.manager.directory(first['id']),
                                                        self.manager.directory(second['id'])})

    def test_active_account_uses_live_credentials_and_syncs_back_to_saved_copy(self):
        row,auth=self.official();auth['tokens']['refresh_token']='new-refresh'
        private_json(self.home/'auth.json',auth);info=self.manager.info
        info.read_identity=Mock(return_value={'kind':'chatgpt','owner':row['tokenOwner'],'name':row['email']})
        with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc:
            rpc.return_value.__enter__.return_value=self.rpc()
            info.read(row,'usage')
            self.assertEqual(rpc.call_args.args[0],self.home)
        saved=json.loads((self.manager.directory(row['id'])/'auth.json').read_text())
        self.assertEqual(saved['tokens']['refresh_token'],'new-refresh')

    def test_errors_do_not_expose_upstream_body_and_api_has_models_without_usage(self):
        row,_=self.official();info=self.manager.info;info.read_identity=Mock(return_value={'kind':'signedOut','name':''})
        with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc:
            rpc.return_value.__enter__.return_value=self.rpc(rate_error=True);info.read(row,'usage')
        self.assertEqual(info.entries[row['id']]['usage']['status'],'error')
        self.assertNotIn('raw private',json.dumps(self.manager.public()))
        api=self.manager.add_api({'name':'API','baseUrl':'https://fixture.test/v1','apiKey':'key','model':'m'})['accounts'][-1]
        with self.assertRaises(ValueError):info.request({'id':api['id'],'section':'usage'})
        with patch('bridge.features.accounts.accounts.model_catalog',return_value=[{'id':'m1'},{'id':'m2'}]):info.read(api,'models')
        self.assertEqual(len(info.entries[api['id']]['models']['models']),2)

    def test_detail_cache_suppresses_duplicate_queries(self):
        row,_=self.official();info=self.manager.info
        info.entries[row['id']]={'usage':{'status':'loading'}}
        with patch('bridge.features.accounts.info.threading.Thread') as worker:
            info.request({'id':row['id'],'section':'usage'});worker.assert_not_called()
        info.entries[row['id']]['usage']={'status':'ready','checkedAt':time.time()}
        with patch('bridge.features.accounts.info.threading.Thread') as worker:
            info.request({'id':row['id'],'section':'usage'});worker.assert_not_called()
            info.request({'id':row['id'],'section':'usage','refresh':True});worker.assert_called_once()

    def test_refresh_retains_last_success_during_loading_and_failure(self):
        row,_=self.official();info=self.manager.info
        previous={'status':'ready','checkedAt':123,'limits':[{'name':'Codex','windows':[]}],
                  'resetCredits':{'availableCount':2},'updatedAt':123}
        info.entries[row['id']]={'usage':previous.copy()}
        with patch('bridge.features.accounts.info.threading.Thread'):
            info.request({'id':row['id'],'section':'usage','refresh':True})
        pending=info.entries[row['id']]['usage']
        self.assertEqual(pending['status'],'loading')
        self.assertEqual(pending['limits'],previous['limits'])
        self.assertEqual(pending['updatedAt'],123)
        info.read_identity=Mock(return_value={'kind':'signedOut','name':''})
        with patch('bridge.features.accounts.accounts.ManagedRPC') as rpc:
            rpc.return_value.__enter__.return_value=self.rpc(rate_error=True)
            info.read(row,'usage',True)
        failed=info.entries[row['id']]['usage']
        self.assertEqual(failed['status'],'error')
        self.assertEqual(failed['limits'],previous['limits'])
        self.assertEqual(failed['updatedAt'],123)
        self.assertNotIn('raw private',json.dumps(failed))

    def test_usage_cache_lasts_five_minutes_but_explicit_read_bypasses_it(self):
        row,_=self.official();info=self.manager.info
        info.entries[row['id']]={'usage':{'status':'ready','checkedAt':time.time()-299}}
        with patch('bridge.features.accounts.info.threading.Thread') as worker:
            info.request({'id':row['id'],'section':'usage'});worker.assert_not_called()
            info.entries[row['id']]['usage']['checkedAt']=time.time()-301
            info.request({'id':row['id'],'section':'usage'});worker.assert_called_once()

    def test_native_identity_and_connection_share_one_account_snapshot(self):
        rpc = self.rpc()
        with patch('bridge.features.accounts.accounts.ManagedRPC') as managed:
            managed.return_value.__enter__.return_value = rpc
            identity = self.manager.info.read_identity()
        self.assertEqual(identity['kind'], 'chatgpt')
        self.assertEqual([call.args[0] for call in rpc.request.call_args_list].count('account/read'), 1)

    def test_transient_current_login_models_use_only_matching_native_chatgpt_catalog(self):
        info = self.manager.info
        account_key = 'a' * 64
        identity = {'kind': 'chatgpt', 'name': 'ChatGPT',
                    'login': {'owner': None, 'context': {'accountKey': account_key, 'email': 'fixture@example.test',
                                                        '_routeCacheKey': 'route-a'}}}
        info.identity = identity
        info.stamp = info.source_stamp()
        info.checked_at = time.time()
        row = info.current_login()
        self.assertTrue(row['transient'])
        with patch('bridge.features.accounts.info.threading.Thread') as worker:
            info.request({'id': row['id'], 'section': 'models'})
            args = worker.call_args.kwargs['args']
        self.assertEqual(info.entries[row['id']]['models']['_routeCacheKey'], 'route-a')
        with patch.object(info, 'read_identity', return_value=identity), patch.object(
                self.bridge.catalog_reader, 'get_kind', return_value={'models': [{'id': 'fixture-model'}]}, create=True) as catalog:
            info.read(*args)
        self.assertEqual(info.entries[row['id']]['models']['models'], [{'id': 'fixture-model'}])
        self.assertEqual(info.entries[row['id']]['models']['_routeCacheKey'], 'route-a')
        self.assertEqual(self.manager.public()['loginAccount']['details']['models']['models'],
                         [{'id': 'fixture-model'}])
        self.assertNotIn('_routeCacheKey', json.dumps(self.manager.public()))
        with patch('bridge.features.accounts.info.threading.Thread') as worker:
            info.request({'id': row['id'], 'section': 'models'})
            worker.assert_not_called()
        catalog.assert_called_once_with('models', str(self.home), refresh=False, provider='openai')
        with patch.object(info, 'read_identity', return_value={**identity, 'kind': 'api'}), patch.object(
                self.bridge.catalog_reader, 'get_kind', create=True) as catalog:
            info.read(row, 'models', refresh=True)
        catalog.assert_not_called()
        self.assertEqual(info.entries[row['id']]['models']['status'], 'error')

    def test_transient_models_discard_changed_login_or_route_and_end_failed_loading(self):
        info = self.manager.info
        original = {'kind': 'chatgpt', 'name': 'ChatGPT', 'login': {'owner': None, 'context': {
            'accountKey': 'a' * 64, '_routeCacheKey': 'route-a'}}}
        info.identity = original
        info.stamp = info.source_stamp()
        info.checked_at = time.time()
        for changed_context in ({'accountKey': 'b' * 64, '_routeCacheKey': 'route-a'},
                                {'accountKey': 'a' * 64, '_routeCacheKey': 'route-b'}):
            with self.subTest(changed_context=changed_context):
                info.identity = original
                info.entries.clear()
                with patch('bridge.features.accounts.info.threading.Thread') as worker:
                    info.request({'id': 'current-login', 'section': 'models'})
                    args = worker.call_args.kwargs['args']
                changed = {**original, 'login': {**original['login'], 'context': changed_context}}
                def change_during_catalog(*args, **kwargs):
                    info.identity = changed
                    return {'models': [{'id': 'stale-model'}]}
                with patch.object(info, 'read_identity', side_effect=[original, changed]), patch.object(
                        self.bridge.catalog_reader, 'get_kind', side_effect=change_during_catalog, create=True):
                    info.read(*args)
                self.assertNotIn('models', info.entries['current-login'])
        info.identity = original
        with patch('bridge.features.accounts.info.threading.Thread') as worker:
            info.request({'id': 'current-login', 'section': 'models'})
            args = worker.call_args.kwargs['args']
        with patch.object(info, 'read_identity', return_value=original), patch.object(
                self.bridge.catalog_reader, 'get_kind', return_value={'modelError': 'upstream unavailable'}, create=True):
            info.read(*args)
        self.assertEqual(info.entries['current-login']['models']['status'], 'error')
        self.assertNotEqual(info.entries['current-login']['models']['status'], 'loading')
