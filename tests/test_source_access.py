"""Network-free tests for the recurring, read-only source-access workflow."""
import json
import socket
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import check_source_access as access


class SourceAccessTests(unittest.TestCase):
    source = dict(id='board', url='https://board.gov.in/jobs', name='Board', department='Board',
                  type='central', noticeTypes=['recruitment'], proxyFallback=True)
    options = dict(directAttempts=2, timeoutSeconds=1, browser=True, browserTimeoutSeconds=2,
                   browserWaitMs=10, maxMirrors=2, maxAlternatives=2, workers=1, budgetSeconds=10)

    def payload(self, body='<a href="/clerk.pdf">Recruitment of Clerk Posts 2026</a>', status=200, url=None):
        return access.Payload(url or self.source['url'], status, 'text/html', body.encode())

    def probe(self, direct=None, browser=None, mirror=None, source=None):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(access, 'http_fetch', side_effect=direct or OSError('TLS failure')) as direct_mock, \
             patch.object(access, 'browser_fetch', side_effect=browser or OSError('browser failure')) as browser_mock, \
             patch.object(access, 'mirror_payload', side_effect=mirror or OSError('mirror failure')) as mirror_mock, \
             patch.object(access.time, 'sleep'):
            result = access.probe(source or self.source, self.options, Path(tmp), time.monotonic() + 60)
            return result, direct_mock, browser_mock, mirror_mock

    def test_direct_success_skips_browser_and_mirrors(self):
        result, direct, browser, mirror = self.probe(direct=[self.payload()])
        self.assertEqual(result['method'], 'direct-1')
        self.assertEqual(result['status'], 'reachable-notices')
        browser.assert_not_called(); mirror.assert_not_called()

    def test_direct_retries_are_bounded(self):
        result, direct, _, _ = self.probe()
        self.assertEqual(direct.call_count, 2)
        self.assertEqual(result['status'], 'unavailable')

    def test_browser_recovers_tls_failure_before_mirror(self):
        result, direct, browser, mirror = self.probe(browser=[self.payload()])
        self.assertEqual(result['method'], 'browser')
        self.assertEqual(direct.call_count, 2)
        browser.assert_called_once(); mirror.assert_not_called()

    def test_navigation_shell_triggers_browser(self):
        result, direct, _, _ = self.probe(direct=[self.payload('<a href="/about">About us</a>')], browser=[self.payload()])
        self.assertEqual(result['method'], 'browser')
        self.assertEqual(direct.call_count, 1)

    def test_mirror_is_opt_in_and_after_browser(self):
        events = []
        def fail_browser(*args): events.append('browser'); raise OSError('blocked')
        def mirror(*args): events.append('mirror'); return self.payload()
        result, _, _, _ = self.probe(browser=fail_browser, mirror=mirror)
        self.assertEqual(events, ['browser', 'mirror'])
        self.assertEqual(result['method'], 'mirror-1')
        _, _, _, mirror_mock = self.probe(source=dict(self.source, proxyFallback=False))
        mirror_mock.assert_not_called()

    def test_404_never_uses_browser_or_mirror(self):
        result, direct, browser, mirror = self.probe(direct=[self.payload('Not found', 404)])
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(direct.call_count, 1)
        browser.assert_not_called(); mirror.assert_not_called()

    def test_browser_failure_still_allows_mirror(self):
        result, _, _, _ = self.probe(browser=ImportError('No playwright installed'), mirror=[self.payload()])
        self.assertEqual(result['method'], 'mirror-1')
        self.assertIn('playwright', result['attempts'][2]['reason'])

    def test_block_pages_never_count_as_notices(self):
        for body in ('403 Forbidden', 'Verify you are human', 'There is no row at position 0.'):
            payload = self.payload(body + '<a href="/jobs.pdf">Recruitment of Clerk Posts</a>')
            self.assertEqual(access.assess(payload, self.source)['status'], 'blocked')

    def test_http_500_with_job_links_is_failure(self):
        self.assertEqual(access.assess(self.payload(status=500), self.source)['status'], 'unavailable')

    def test_empty_body_not_success(self):
        self.assertEqual(access.assess(self.payload(''), self.source)['status'], 'unavailable')

    def test_pdf_requires_magic_bytes_not_content_type(self):
        payload = access.Payload(self.source['url'], 200, 'application/pdf', b'%PDF-1.7 document')
        self.assertEqual(access.assess(payload, self.source)['status'], 'reachable-pdf')
        payload.data = b'Access denied'
        self.assertEqual(access.assess(payload, self.source)['status'], 'blocked')

    def test_raw_page_source_embedded_notice_is_checked(self):
        payload=self.payload('<noscript><a href="/clerk.pdf">Recruitment of Clerk Posts 2026</a></noscript>')
        with patch.object(access.monitor, 'page_source_candidates', wraps=access.monitor.page_source_candidates) as fallback:
            self.assertEqual(access.assess(payload,self.source)['status'],'reachable-notices')
            fallback.assert_called_once()

    def test_discovery_content_stays_a_lead(self):
        payload = self.payload('<a href="/clerk.html">Board Clerk Recruitment 2026</a>', url='https://www.indgovtjobs.in/')
        result = access.assess(payload, dict(self.source, discovery=True))
        self.assertEqual(result['status'], 'reachable-feed')
        self.assertIn('not a verified', result['reason'])

    def test_alternatives_are_observed_same_host_links_only(self):
        payload=self.payload('''<a href="/careers">Careers</a><a href="https://other.gov.in/jobs">Recruitment</a>
        <a href="/about">About</a><a href="http://board.gov.in/old">Vacancies</a>
        <a href="/careers">Recruitment</a><a href="/notices">Notices</a>''')
        self.assertEqual(access.alternative_links(payload,self.source,2),
                         ['https://board.gov.in/careers','https://board.gov.in/notices'])
        self.assertEqual(access.alternative_links(payload,dict(self.source,discovery=True),2),[])

    def test_working_alternative_is_reported_not_registered(self):
        shell=self.payload('<a href="/careers">Careers</a>')
        with patch.object(access.monitor,'looks_like_notice',return_value=False):
            # Preserve the actual assessor for the alternative payload.
            with patch.object(access,'assess',side_effect=lambda p,s:
                              {'status':'reachable-notices'} if 'clerk.pdf' in p.data.decode() else {'status':'reachable-no-notices'}):
                result, direct, _, _=self.probe(direct=[shell,self.payload()], source=dict(self.source,proxyFallback=False))
        self.assertEqual(result['status'],'alternative-found')
        self.assertEqual(direct.call_args.args[0],'https://board.gov.in/careers')
        self.assertIn('registry unchanged',result['reason'])

    def test_private_local_and_credentialed_urls_rejected(self):
        for url in ('http://localhost/', 'http://127.0.0.1/', 'http://169.254.169.254/',
                    'http://10.0.0.1/', 'http://[::1]/', 'file:///etc/passwd',
                    'https://user:secret@board.gov.in/', 'https://server.internal/',
                    'https://board.gov.in:22/', 'javascript:alert(1)'):
            with self.subTest(url=url): self.assertFalse(access.public_url(url))
        self.assertTrue(access.public_url('https://board.gov.in/jobs'))

    def test_dns_private_answers_rejected(self):
        access.public_dns.cache_clear()
        with patch.object(socket,'getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',80))]):
            self.assertFalse(access.public_dns('board.gov.in'))
        access.public_dns.cache_clear()

    def test_browser_blocks_post_and_cross_host_navigation(self):
        with patch.object(access,'public_dns',return_value=True):
            self.assertFalse(access.browser_request_allowed(self.source['url'],'POST',navigation=False,origin=self.source['url']))
            self.assertFalse(access.browser_request_allowed('https://other.gov.in/','GET',navigation=True,origin=self.source['url']))
            self.assertTrue(access.browser_request_allowed('https://board.gov.in/api/notices','GET',navigation=False,origin=self.source['url']))
            self.assertFalse(access.browser_request_allowed('http://127.0.0.1/api','GET',navigation=False,origin=self.source['url']))

    def test_http_redirects_do_not_escape_host_or_downgrade(self):
        import urllib.request
        request=urllib.request.Request(self.source['url'])
        handler=access.PublicRedirects('board.gov.in')
        with patch.object(access,'require_public'):
            for url in ('https://other.gov.in/','http://board.gov.in/'):
                with self.assertRaises(ValueError):handler.redirect_request(request,None,302,'',{},url)

    def test_mirror_does_not_forward_private_target(self):
        with patch.object(access,'http_fetch') as fetch:
            with self.assertRaises(ValueError):access.mirror_payload('http://127.0.0.1/','https://mirror.example/{url}',1)
            fetch.assert_not_called()

    def test_mirror_unwraps_json_but_preserves_official_base(self):
        payload=access.Payload('https://mirror.example/',200,'application/json',json.dumps({'contents':'<a href="/clerk.pdf">Recruitment of Clerk Posts</a>'}).encode())
        with patch.object(access,'http_fetch',return_value=payload), patch.object(access,'require_public'):
            result=access.mirror_payload(self.source['url'],'https://mirror.example/?url={quoted}',1)
        self.assertEqual(result.url,self.source['url'])
        self.assertEqual(access.assess(result,self.source)['examples'][0]['url'],'https://board.gov.in/clerk.pdf')

    def test_artifact_redacts_secrets_and_form_values(self):
        text='''<script>secretScript</script><input name="token" value="secretInput"><input value=secretBare>
        <textarea>secretText</textarea><meta name="csrf-token" content="secretMeta">
        <a href="/jobs?token=secretQuery">Link</a>'''
        sanitized=access.sanitized_html(text.encode())
        for token in ('secretScript','secretInput','secretBare','secretText','secretMeta','secretQuery'):
            self.assertNotIn(token,sanitized)
        self.assertNotIn('secret',access.redact_url('https://user:secret@board.gov.in/api?token=secret#secret'))

    def test_unresolved_attempts_preserve_html_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(access,'http_fetch',return_value=self.payload('403 Forbidden',403)), \
             patch.object(access,'browser_fetch',side_effect=ImportError('playwright missing')), \
             patch.object(access,'mirror_payload',side_effect=OSError('network')):
            result=access.probe(self.source,self.options,Path(tmp),time.monotonic()+60)
            self.assertEqual(result['status'],'blocked')
            self.assertTrue(list(Path(tmp).glob('*/direct-1.html.txt')))
            self.assertTrue(any('playwright' in a.get('reason','') for a in result['attempts']))

    def test_budget_deferred_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(access,'probe') as probe:
            report=access.run_checks([self.source],dict(self.options,budgetSeconds=0),Path(tmp))
            self.assertEqual(report['sources'][0]['status'],'deferred')
            probe.assert_not_called()
            self.assertTrue((Path(tmp)/'report.json').exists())

    def test_rotation_and_read_only_results(self):
        sources=[dict(self.source,id=str(i)) for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(access,'probe',side_effect=lambda s,*args: {'id':s['id'],'status':'unavailable'}), \
             patch.object(access.monitor,'write_json') as publish:
            report=access.run_checks(sources,self.options,Path(tmp),rotation=2)
            self.assertEqual([s['id'] for s in report['sources']],['2','3','0','1'])
            publish.assert_not_called()
            self.assertIn('no alerts',(Path(tmp)/'report.md').read_text())

    def test_all_registries_loaded_without_duplicate_urls(self):
        sources=access.load_sources()
        self.assertEqual(len(sources),len({s['url'] for s in sources}))
        ids={alias for s in sources for alias in s['aliases']}
        for sid in ('ssc','ibps','ntpc','cpri','indgovtjobs'):
            self.assertIn(sid,ids)
        self.assertTrue(next(s for s in sources if s['id']=='indgovtjobs')['discovery'])

    def test_browser_records_only_same_origin_api_metadata(self):
        page=MagicMock()
        page.url=self.source['url']
        page.content.return_value='<a href="/clerk.pdf">Recruitment of Clerk Posts</a>'
        page.goto.return_value.status=200
        def on(event,callback):
            if event!='response':return
            for url in ('https://board.gov.in/api?token=secret','https://tracking.example/events'):
                response=MagicMock();response.url=url;response.status=200
                response.request.resource_type='xhr';response.request.method='GET'
                callback(response)
        page.on.side_effect=on
        playwright=MagicMock()
        browser=playwright.chromium.launch.return_value
        browser.new_context.return_value.new_page.return_value=page
        module=types.ModuleType('playwright.sync_api')
        module.sync_playwright=MagicMock()
        module.sync_playwright.return_value.__enter__.return_value=playwright
        with tempfile.TemporaryDirectory() as tmp, patch.dict('sys.modules',{'playwright':types.ModuleType('playwright'),'playwright.sync_api':module}), \
             patch.object(access,'require_public'):
            payload=access.browser_fetch(self.source['url'],2,10,Path(tmp))
            api=json.loads((Path(tmp)/'api-requests.json').read_text())
        self.assertEqual(len(api),1)
        self.assertNotIn('secret',api[0]['url'])
        self.assertEqual(set(api[0]),{'url','status','method','type'})
        self.assertEqual(payload.status,200)
        browser.close.assert_called_once()
        self.assertFalse(browser.new_context.call_args.kwargs['accept_downloads'])

    def test_workflow_is_scheduled_via_caller_and_read_only(self):
        root=access.ROOT
        caller=(root/'.github/workflows/update-job-alerts.yml').read_text()
        workflow=(root/'.github/workflows/source-access.yml').read_text()
        self.assertIn('uses: ./.github/workflows/source-access.yml',caller)
        self.assertIn('workflow_call:',workflow)
        self.assertIn('workflow_dispatch:',workflow)
        self.assertIn('contents: read',workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('SOURCE_CHECK_RUNNER_LABELS',workflow)
        self.assertIn('if: always()',workflow)
        self.assertIn('actions/upload-artifact@v4',workflow)
        self.assertIn('retention-days: 7',workflow)
        for forbidden in ('git push','git commit','scripts/update_jobs.py','contents: write','secrets: inherit'):
            self.assertNotIn(forbidden,workflow)

    def test_protected_output_directory_rejected(self):
        with patch('sys.argv',['check','--output',str(access.ROOT/'data')]):
            with self.assertRaises(SystemExit) as exc:access.main()
        self.assertEqual(exc.exception.code,2)

    def test_unknown_source_id_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp, patch('sys.argv',['check','--output',tmp,'--source-ids','not-a-board']):
            with self.assertRaises(SystemExit) as exc:access.main()
        self.assertEqual(exc.exception.code,2)

    def test_partial_report_is_not_an_all_clear(self):
        report={'checkedAt':'2026-09-22T00:00:00Z','runner':'local','targetCount':10,
                'complete':False,'sources':[{'id':'board','status':'unavailable'}]}
        text=access.markdown_report(report)
        self.assertIn('1/10 targets',text)
        self.assertIn('partial / still running or interrupted',text)

    def test_snapshot_size_is_bounded(self):
        data=b'<html>'+b'x'*(access.HTML_ARTIFACT_BYTES*2)+b'</html>'
        self.assertLessEqual(len(access.sanitized_html(data).encode()),access.HTML_ARTIFACT_BYTES)

    def test_finished_run_marks_completion_without_claiming_verified_jobs(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(access,'probe',return_value={'id':'board','status':'reachable-notices','method':'browser'}):
            report=access.run_checks([self.source],self.options,Path(tmp))
        self.assertTrue(report['complete'])
        self.assertIn('not verified vacancies',access.markdown_report(report))
